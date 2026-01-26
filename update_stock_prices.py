import pandas as pd
from pykrx import stock
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()
import json
import requests
import time
import sys
import sqlite3
import threading
import subprocess
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
from pathlib import Path
from ml.inference import run_inference, run_inference_both

try:
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover
    pq = None

# Static folder for serving built frontend
static_folder = os.path.join(os.path.dirname(__file__), 'static')
if not os.path.exists(static_folder):
    static_folder = None

app = Flask(__name__, static_folder=static_folder, static_url_path='')
CORS(app)  # 모든 도메인에서 접근 허용

# 글로벌 인메모리 캐시 (KIS API 데이터용)
_kis_api_cache = {}

# =============================
# 스케줄러 상태 관리
# =============================
_scheduler_state = {
    "eod_done_today": False,       # 오늘 9시~10시 EOD 실행 여부
    "intraday_done_today": False,  # 오늘 15시~15시30분 Intraday 실행 여부
    "inference_done_today": False, # 오늘 15시~15시30분 Inference 실행 여부
    "auto_start_done_today": False, # 오늘 자동매매 자동시작 실행 여부
    "last_check_date": None,       # 마지막 체크 날짜
    "crawling_status": None,       # 'eod' | 'intraday' | None
    "crawling_start_time": None,   # 크롤링 시작 시간
    "crawling_error": None,        # 크롤링 에러 메시지
    # 최근 수집 완료 정보
    "last_crawl_completed_at": None,  # 마지막 수집 완료 시간 (ISO 형식)
    "last_crawl_mode": None,          # 마지막 수집 모드 ('eod', 'intraday', 'manual')
    "last_crawl_date_range": None,    # 마지막 수집 날짜 범위
    "last_crawl_duration": None,      # 마지막 수집 소요시간 (초)
}
_scheduler_lock = threading.Lock()

# SQLite 데이터베이스 설정
import os
# Docker 환경에서는 /app/db 볼륨 사용, 로컬에서는 현재 디렉토리 사용
db_dir = os.environ.get('DB_PATH', os.path.dirname(__file__))
if db_dir and db_dir != os.path.dirname(__file__):
    os.makedirs(db_dir, exist_ok=True)
db_path = os.path.join(db_dir, 'mystock.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# -----------------------------
# Local ./data (Parquet) helpers
# -----------------------------
DATA_ROOT = os.path.join(os.path.dirname(__file__), "data", "krx")
KRX_TICKERS_PATH = os.path.join(DATA_ROOT, "master", "tickers.parquet")
KRX_BARS_DIR = os.path.join(DATA_ROOT, "bars")

_tickers_cache = None  # type: ignore
_bars_cache = {}  # type: ignore


def _parse_partition_date(partition_name: str):
    """date=YYYY-MM-DD -> datetime.date"""
    if not partition_name.startswith("date="):
        return None
    try:
        return datetime.strptime(partition_name.split("=", 1)[1], "%Y-%m-%d").date()
    except Exception:
        return None


def get_latest_local_bars_date() -> str | None:
    """Return latest available partition date as 'YYYYMMDD' or None."""
    try:
        if not os.path.isdir(KRX_BARS_DIR):
            return None
        dates = []
        for name in os.listdir(KRX_BARS_DIR):
            d = _parse_partition_date(name)
            if d:
                dates.append(d)
        if not dates:
            return None
        latest = max(dates)
        return latest.strftime("%Y%m%d")
    except Exception:
        return None


def load_local_tickers() -> dict:
    """Load tickers.parquet as dict[code] -> {'name':..., 'market':...}."""
    global _tickers_cache
    if _tickers_cache is not None:
        return _tickers_cache

    if pq is None:
        _tickers_cache = {}
        return _tickers_cache

    if not os.path.exists(KRX_TICKERS_PATH):
        _tickers_cache = {}
        return _tickers_cache

    try:
        table = pq.read_table(KRX_TICKERS_PATH)
        df = table.to_pandas()
        if "code" not in df.columns:
            _tickers_cache = {}
            return _tickers_cache
        df["code"] = df["code"].astype(str).str.zfill(6)
        result = {}
        for _, row in df.iterrows():
            code = row.get("code")
            if not code:
                continue
            result[code] = {
                "name": row.get("name", "") if "name" in df.columns else "",
                "market": row.get("market", "") if "market" in df.columns else "",
            }
        _tickers_cache = result
        return _tickers_cache
    except Exception:
        _tickers_cache = {}
        return _tickers_cache


def _read_bars_partition_df(date_yyyymmdd: str) -> pd.DataFrame | None:
    """Read a single partition parquet (part-0000.parquet) into a DataFrame."""
    if pq is None:
        return None
    date_obj = datetime.strptime(date_yyyymmdd, "%Y%m%d").date()
    part_dir = os.path.join(KRX_BARS_DIR, f"date={date_obj.strftime('%Y-%m-%d')}")
    path = os.path.join(part_dir, "part-0000.parquet")
    if not os.path.exists(path):
        return None

    cached = _bars_cache.get(date_yyyymmdd)
    if cached is not None:
        return cached

    try:
        # Use ParquetFile to avoid schema merge issues with read_table
        pf = pq.ParquetFile(path)
        df = pf.read().to_pandas()
        if "code" in df.columns:
            df["code"] = df["code"].astype(str).str.zfill(6)
        _bars_cache[date_yyyymmdd] = df
        return df
    except Exception:
        return None


def get_local_bars_for_codes(date_yyyymmdd: str, codes: list[str]) -> dict:
    """Return dict[code] -> bar fields from local parquet for the given date."""
    df = _read_bars_partition_df(date_yyyymmdd)
    if df is None or df.empty:
        return {}
    if "code" not in df.columns:
        return {}
    wanted = set([str(c).zfill(6) for c in codes])
    sub = df[df["code"].isin(wanted)]
    if sub.empty:
        return {}

    out = {}
    for _, row in sub.iterrows():
        code = str(row.get("code", "")).zfill(6)
        if not code:
            continue
        out[code] = {
            "date": row.get("date"),
            "open": float(row.get("open", 0) or 0),
            "high": float(row.get("high", 0) or 0),
            "low": float(row.get("low", 0) or 0),
            "close": float(row.get("close", 0) or 0),
            "volume": int(row.get("volume", 0) or 0),
            "value": float(row.get("value", 0) or 0),
            "market": row.get("market", "") if "market" in sub.columns else "",
        }
    return out


def get_recent_business_day() -> str:
    """Prefer the latest local bars partition; fallback to a best-effort business day."""
    local = get_latest_local_bars_date()
    if local:
        return local
    # Fallback: weekend adjustment (holidays not handled here)
    today = datetime.now().date()
    if today.weekday() == 5:
        today = today - timedelta(days=1)
    elif today.weekday() == 6:
        today = today - timedelta(days=2)
    return today.strftime("%Y%m%d")

# 데이터베이스 모델 정의
class Group(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    stocks = db.relationship('Stock', backref='group', lazy=True, cascade='all, delete-orphan')

class Stock(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    group_id = db.Column(db.String(50), db.ForeignKey('group.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, default=0)
    change = db.Column(db.Float, default=0)
    change_percent = db.Column(db.Float, default=0)
    volume = db.Column(db.Integer, default=0)
    market_cap = db.Column(db.Integer, default=0)
    per = db.Column(db.Float, default=0)
    pbr = db.Column(db.Float, default=0)
    eps = db.Column(db.Float, default=0)
    sector = db.Column(db.String(100), default='')
    added_at = db.Column(db.String(50), nullable=False)
    memos = db.relationship('Memo', backref='stock', lazy=True, cascade='all, delete-orphan')
    trades = db.relationship('Trade', backref='stock', lazy=True, cascade='all, delete-orphan')

class Memo(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    stock_id = db.Column(db.String(100), db.ForeignKey('stock.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(50), nullable=False)

# 매수/매도 기록 모델
class Trade(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    stock_id = db.Column(db.String(100), db.ForeignKey('stock.id'), nullable=False)
    trade_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    trade_date = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.String(50), nullable=False)
    memo = db.Column(db.Text, default='')

# 분석 일지 모델 (종목 독립적)
class Journal(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='general')  # market, stock, strategy, etc.
    tags = db.Column(db.Text, default='')  # comma-separated
    stock_symbols = db.Column(db.Text, default='')  # comma-separated stock symbols
    created_at = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.String(50), nullable=False)

# AI 추천 이력 모델
class Recommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    filter_tag = db.Column(db.String(20), nullable=False, default='filter2')
    model_name = db.Column(db.String(50), nullable=False, default='model1')
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    base_price = db.Column(db.Float, nullable=False)  # 추천 당시 종가
    probability = db.Column(db.Float, default=0)
    expected_return = db.Column(db.Float, default=0)
    market_cap = db.Column(db.Float, default=0)
    created_at = db.Column(db.String(50), nullable=False)

# 포트폴리오 일간 수익률 히스토리 (캐싱용)
class PortfolioHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(db.String(50), db.ForeignKey('group.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    total_invested = db.Column(db.Float, default=0)
    total_value = db.Column(db.Float, default=0)
    return_rate = db.Column(db.Float, default=0)  # 수익률 (%)
    created_at = db.Column(db.String(50), nullable=False)
    
    __table_args__ = (db.UniqueConstraint('group_id', 'date', name='unique_group_date'),)


# 자동매매 설정 모델 (서버 저장)
class AutoTradingSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.String(50), nullable=False)


def load_fundamentals_json() -> dict:
    """Load public/stock_fundamentals.json as dict; returns {} if missing."""
    try:
        with open("public/stock_fundamentals.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def merged_stock_info(code: str, business_day: str, fundamentals: dict, local_bars_map: dict, tickers: dict) -> dict:
    """Merge stock fundamentals JSON + local parquet bars + local tickers (local bars win)."""
    code = str(code).zfill(6)
    base = fundamentals.get(code, {}) if isinstance(fundamentals, dict) else {}
    if not isinstance(base, dict):
        base = {}

    # Local bars win for OHLCV fields
    b = local_bars_map.get(code)
    if b:
        base = dict(base)
        base["currentPrice"] = b.get("close", base.get("currentPrice", 0))
        base["volume"] = b.get("volume", base.get("volume", 0))
        base["open"] = b.get("open", base.get("open", 0))
        base["high"] = b.get("high", base.get("high", 0))
        base["low"] = b.get("low", base.get("low", 0))
        base["date"] = business_day

    # Local tickers enrichment
    t = tickers.get(code) if isinstance(tickers, dict) else None
    if isinstance(t, dict) and (t.get("name") or t.get("market")):
        base = dict(base)
        if t.get("name"):
            base["name"] = t.get("name")
        if t.get("market"):
            base["market"] = t.get("market")

    return base

# 데이터베이스 초기화
def init_db():
    with app.app_context():
        db.create_all()
        # Lightweight schema migration for existing SQLite DB
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(recommendation)")
            cols = {row[1] for row in cur.fetchall()}
            if 'filter_tag' not in cols:
                cur.execute("ALTER TABLE recommendation ADD COLUMN filter_tag TEXT DEFAULT 'filter2'")
                conn.commit()
            if 'model_name' not in cols:
                cur.execute("ALTER TABLE recommendation ADD COLUMN model_name TEXT DEFAULT 'model1'")
                conn.commit()
        except Exception as e:
            print(f"[WARN] DB migration failed: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        print("데이터베이스 초기화 완료")

# 한국투자증권 API 설정
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
ACCESS_TOKEN = None
TOKEN_FILE = "kis_token.json"


def save_token(token_data):
    """토큰을 파일에 저장"""
    try:
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(token_data, f, ensure_ascii=False)
    except Exception as e:
        print(f"토큰 저장 실패: {e}")

def load_token():
    """파일에서 토큰 로드"""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"토큰 로드 실패: {e}")
    return None

def get_kis_access_token():
    global ACCESS_TOKEN
    
    # 메모리에 토큰이 있으면 사용
    if ACCESS_TOKEN:
        return ACCESS_TOKEN
    
    # 파일에서 토큰 로드 시도
    token_data = load_token()
    if token_data:
        token = token_data.get('access_token')
        expired = token_data.get('expired_time')
        if token and expired:
            # 만료 시간 확인 (여유를 두고 10분提前 만료로 간주)
            current_time = datetime.now().timestamp()
            if current_time < (expired - 600):  # 10분 여유
                ACCESS_TOKEN = token
                print("파일에서 토큰 로드 성공")
                return ACCESS_TOKEN
    
    # 새 토큰 발급
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    
    print("KIS 토큰 발급 요청...")
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        print(f"토큰 발급 응답: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            ACCESS_TOKEN = data.get("access_token")
            expires_in = data.get("expires_in", 86400)  # 기본 24시간
            
            # 만료 시간 계산
            expired_time = datetime.now().timestamp() + expires_in
            
            # 토큰 데이터 저장
            token_data = {
                'access_token': ACCESS_TOKEN,
                'expired_time': expired_time,
                'issued_time': datetime.now().timestamp()
            }
            save_token(token_data)
            
            print(f"토큰 발급 성공 (유효기간: {expires_in}초)")
            return ACCESS_TOKEN
        else:
            print(f"토큰 발급 실패: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"토큰 발급 중 예외 발생: {e}")
        return None

def call_kis_api(endpoint, params=None, tr_id="FHKST01010100"):
    token = get_kis_access_token()
    if not token:
        return {}
    url = f"https://openapi.koreainvestment.com:9443{endpoint}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {}
        return response.json()
    except Exception as e:
        print(f"KIS API 호출 실패: {e}")
        return {}

# KIS 실시간 시세 캐시 (간단한 메모리 캐시)
_kis_price_cache = {}
_kis_cache_time = {}

def get_kis_realtime_price(code: str) -> dict:
    """KIS API에서 실시간 시세 가져오기 (PER, PBR, EPS, 현재가, 거래량 등)"""
    code = str(code).zfill(6)
    
    # 캐시 확인 (30초 이내면 캐시 사용)
    import time as tm
    now = tm.time()
    if code in _kis_price_cache and (now - _kis_cache_time.get(code, 0)) < 30:
        return _kis_price_cache[code]
    
    data = {}
    try:
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        result = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-price", params, "FHKST01010100")
        output = result.get("output", {})
        
        if output:
            data = {
                "currentPrice": int(output.get("stck_prpr", 0) or 0),  # 현재가
                "change": int(output.get("prdy_vrss", 0) or 0),  # 전일대비
                "changePercent": float(output.get("prdy_ctrt", 0) or 0),  # 등락률
                "volume": int(output.get("acml_vol", 0) or 0),  # 누적거래량
                "per": float(output.get("per", 0) or 0),
                "pbr": float(output.get("pbr", 0) or 0),
                "eps": float(output.get("eps", 0) or 0),
                "marketCap": int(output.get("hts_avls", 0) or 0),  # 시가총액(억)
                "foreignOwnership": float(output.get("hts_frgn_ehrt", 0) or 0),  # 외인소진율
                "high": int(output.get("stck_hgpr", 0) or 0),
                "low": int(output.get("stck_lwpr", 0) or 0),
                "open": int(output.get("stck_oprc", 0) or 0),
            }
            # 캐시 저장
            _kis_price_cache[code] = data
            _kis_cache_time[code] = now
    except Exception as e:
        print(f"KIS 실시간 시세 조회 실패 ({code}): {e}")
    
    return data

def get_kis_stock_info(code):
    data = {}
    
    try:
        token = get_kis_access_token()
        if not token:
            print(f"KIS 토큰 발급 실패로 {code} 데이터 조회 건너뜀")
            return data
        # 시세 정보 (PER, PBR, EPS, 시가총액)
        price_params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        price_data = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-price", price_params)
        output = price_data.get("output", {})
        data["per"] = float(output.get("per", 0))
        data["pbr"] = float(output.get("pbr", 0))
        data["eps"] = float(output.get("eps", 0))
        data["marketCap"] = int(output.get("mktc_tot_amt", 0))
        
        # 재무 정보 (영업이익률) - 다른 엔드포인트 시도
        fin_params = {
            "fid_div_cls_code": "0",
            "fid_input_iscd": code
        }
        # KIS 재무제표 API - 다른 엔드포인트 시도
        fin_data = call_kis_api("/uapi/domestic-stock/v1/finance/income-statement", fin_params, "FHKST01010400")  # 손익계산서
        
        # 영업이익률 계산 (최근 분기 데이터)
        operating_margins = []
        operating_margin = 0
        if fin_data.get("output"):
            # 실제 API 응답 구조에 따라 파싱 (예시)
            # output에서 영업이익률 관련 필드 추출
            try:
                # 최근 4분기 영업이익률 (실제 필드명에 따라 조정 필요)
                quarters = fin_data["output"][:4] if len(fin_data["output"]) >= 4 else fin_data["output"]
                for quarter in quarters:
                    if "영업이익률" in quarter:
                        margin = float(quarter["영업이익률"])
                        operating_margins.append(margin)
                if operating_margins:
                    operating_margin = operating_margins[-1]  # 최근 분기
            except:
                pass
        
        data["operating_margins"] = operating_margins
        data["operatingMargin"] = operating_margin
        
        # 투자자별 매매동향
        inv_params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        inv_data = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-investor", inv_params, "FHKST01010900")  # 투자자별 매매동향 tr_id
        output2 = inv_data.get("output", [{}])
        if output2 and len(output2) > 0:
            # 최근 데이터 사용 (첫 번째 항목)
            recent_data = output2[0]
            data["foreign_buy"] = recent_data.get("frgn_ntby_qty", "N/A")  # 외국인 순매수 수량
            data["foreign_sell"] = recent_data.get("frgn_seln_vol", "N/A")  # 외국인 매도 수량 (필드명 확인 필요)
            data["institution_buy"] = recent_data.get("orgn_ntby_qty", "N/A")  # 기관 순매수 수량
            data["institution_sell"] = recent_data.get("orgn_seln_vol", "N/A")  # 기관 매도 수량 (필드명 확인 필요)
        else:
            data["foreign_buy"] = "N/A"
            data["foreign_sell"] = "N/A"
            data["institution_buy"] = "N/A"
            data["institution_sell"] = "N/A"
        
        # 최대주주 지분율 (API 확인 필요하여 일단 N/A)
        data["major_shareholder_stake"] = "N/A"
        
    except Exception as e:
        print(f"KIS API error for {code}: {e}")
    
    return data


@app.route('/api/debug/kis-raw/<code>', methods=['GET'])
def api_debug_kis_raw(code):
    """Debug endpoint: return raw KIS API output and parsed realtime fields for inspection."""
    try:
        code = str(code).zfill(6)
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        raw = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-price", params, "FHKST01010100")
        parsed = get_kis_realtime_price(code)
        return jsonify({"success": True, "code": code, "raw": raw, "parsed": parsed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/update-stock/<code>', methods=['POST'])
def update_single_stock(code):
    try:
        code = str(code).zfill(6)
        business_day = get_recent_business_day()
        
        # pykrx 데이터 가져오기 (가격 + 기본 지표)
        fundamentals = {}
        market_caps = {}
        price_data = {}

        # 1) Local parquet bars first
        local_bars = get_local_bars_for_codes(business_day, [code])
        if code in local_bars:
            b = local_bars[code]
            price_data = {
                code: {
                    '종가': b.get('close', 0),
                    '거래량': b.get('volume', 0),
                    '시가': b.get('open', 0),
                    '고가': b.get('high', 0),
                    '저가': b.get('low', 0),
                }
            }

        # 2) Fallback to pykrx if local missing
        try:
            fund_data = stock.get_market_fundamental(business_day, business_day, [code])
            cap_data = stock.get_market_cap(business_day, business_day, [code])
            ohlcv_data = None
            if not price_data:
                ohlcv_data = stock.get_market_ohlcv(business_day, business_day, [code])
            
            if not fund_data.empty:
                fundamentals = fund_data.to_dict('index')
            if not cap_data.empty:
                market_caps = cap_data.to_dict('index')
            if ohlcv_data is not None and not ohlcv_data.empty:
                price_data = ohlcv_data.to_dict('index')
        except Exception as e:
            print(f"pykrx error for {code}: {e}")
        
        # 기존 데이터 로드
        try:
            with open("public/stock_fundamentals.json", "r", encoding="utf-8") as f:
                stock_data = json.load(f)
        except:
            stock_data = {}
        
        # KIS API 데이터 가져오기 (재무/투자 정보)
        kis_data = get_kis_stock_info(code)

        # Local tickers enrichment
        tickers = load_local_tickers()
        t = tickers.get(code, {})
        
        # 데이터 업데이트 - pykrx + KIS API 통합
        stock_data[code] = stock_data.get(code, {})
        stock_data[code].update({
            # pykrx 가격 데이터
            "currentPrice": price_data.get(code, {}).get('종가', 0),
            "volume": price_data.get(code, {}).get('거래량', 0),
            
            # pykrx 기본 지표
            "per": fundamentals.get(code, {}).get('PER', 0),
            "pbr": fundamentals.get(code, {}).get('PBR', 0),
            "eps": fundamentals.get(code, {}).get('EPS', 0),
            "marketCap": market_caps.get(code, {}).get('시가총액', 0),

            # Local master data
            "name": t.get("name", stock_data.get(code, {}).get("name", "")),
            "market": t.get("market", stock_data.get(code, {}).get("market", "")),
            
            # KIS API 재무/투자 정보
            "foreignOwnership": 0,  # KIS에서 가져올 수 있으면 추가
            "operatingMargin": kis_data.get('operatingMargin', 0),
            "quarterlyMargins": [],  # KIS에서 분기별 데이터 파싱 필요
            "foreign_buy": kis_data.get('foreign_buy', 'N/A'),
            "foreign_sell": kis_data.get('foreign_sell', 'N/A'),
            "institution_buy": kis_data.get('institution_buy', 'N/A'),
            "institution_sell": kis_data.get('institution_sell', 'N/A'),
            "operating_margins": kis_data.get('operating_margins', []),
            "major_shareholder_stake": kis_data.get('major_shareholder_stake', 'N/A'),
        })
        
        # JSON 저장
        with open("public/stock_fundamentals.json", "w", encoding="utf-8") as f:
            json.dump(stock_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True, "code": code})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/update-stocks', methods=['POST'])
def update_multiple_stocks():
    try:
        data = request.get_json()
        codes = [str(c).zfill(6) for c in (data.get('codes', []) or [])]
        
        business_day = get_recent_business_day()

        # Local parquet bars first (price/volume)
        local_bars_map = get_local_bars_for_codes(business_day, codes)
        
        # pykrx 데이터 배치로 가져오기 (가격 + 기본 지표)
        fundamentals = {}
        market_caps = {}
        price_data_all = {}
        for i in range(0, len(codes), 50):
            batch = codes[i:i+50]
            try:
                fund_batch = stock.get_market_fundamental(business_day, business_day, batch)
                cap_batch = stock.get_market_cap(business_day, business_day, batch)
                # Only fetch OHLCV for codes missing local bars
                missing_for_ohlcv = [c for c in batch if c not in local_bars_map]
                ohlcv_batch = stock.get_market_ohlcv(business_day, business_day, missing_for_ohlcv) if missing_for_ohlcv else None
                
                fundamentals.update(fund_batch.to_dict('index'))
                market_caps.update(cap_batch.to_dict('index'))
                if ohlcv_batch is not None and not ohlcv_batch.empty:
                    price_data_all.update(ohlcv_batch.to_dict('index'))
            except:
                pass

        # Overlay local bars into price_data_all (local wins)
        for code, b in local_bars_map.items():
            price_data_all[code] = {
                '종가': b.get('close', 0),
                '거래량': b.get('volume', 0),
                '시가': b.get('open', 0),
                '고가': b.get('high', 0),
                '저가': b.get('low', 0),
            }
        
        # 기존 데이터 로드
        try:
            with open("public/stock_fundamentals.json", "r", encoding="utf-8") as f:
                stock_data = json.load(f)
        except:
            stock_data = {}
        
        # 데이터 업데이트
        tickers = load_local_tickers()
        for code in codes:
            # KIS API 데이터 가져오기 (재무/투자 정보)
            kis_data = get_kis_stock_info(code)
            t = tickers.get(code, {})
            
            stock_data[code] = stock_data.get(code, {})
            stock_data[code].update({
                # pykrx 가격 데이터
                "currentPrice": price_data_all.get(code, {}).get('종가', 0),
                "volume": price_data_all.get(code, {}).get('거래량', 0),
                
                # pykrx 기본 지표
                "per": fundamentals.get(code, {}).get('PER', 0),
                "pbr": fundamentals.get(code, {}).get('PBR', 0),
                "eps": fundamentals.get(code, {}).get('EPS', 0),
                "marketCap": market_caps.get(code, {}).get('시가총액', 0),

                # Local master data
                "name": t.get("name", stock_data.get(code, {}).get("name", "")),
                "market": t.get("market", stock_data.get(code, {}).get("market", "")),
                
                # KIS API 재무/투자 정보
                "foreignOwnership": 0,  # KIS에서 가져올 수 있으면 추가
                "operatingMargin": kis_data.get('operatingMargin', 0),
                "quarterlyMargins": [],  # KIS에서 분기별 데이터 파싱 필요
                "foreign_buy": kis_data.get('foreign_buy', 'N/A'),
                "foreign_sell": kis_data.get('foreign_sell', 'N/A'),
                "institution_buy": kis_data.get('institution_buy', 'N/A'),
                "institution_sell": kis_data.get('institution_sell', 'N/A'),
                "operating_margins": kis_data.get('operating_margins', []),
                "major_shareholder_stake": kis_data.get('major_shareholder_stake', 'N/A'),
            })
        
        # JSON 저장
        with open("public/stock_fundamentals.json", "w", encoding="utf-8") as f:
            json.dump(stock_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({"success": True, "updated_codes": codes})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ===== ETF 검색 API (KIS API 사용) =====
# ETF 캐시 (파일 기반)
ETF_CACHE_FILE = os.path.join(os.path.dirname(__file__), "public", "etf_cache.json")

def load_etf_cache():
    """ETF 캐시 파일 로드"""
    try:
        if os.path.exists(ETF_CACHE_FILE):
            with open(ETF_CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                # Normalize keys: extract numeric code if present (e.g., 'KRX:233160' -> '233160')
                normalized = {}
                for k, v in (raw.items() if isinstance(raw, dict) else []):
                    try:
                        # extract first sequence of digits
                        import re
                        m = re.search(r"(\d{1,6})", str(k))
                        if m:
                            code = m.group(1).zfill(6)
                        else:
                            code = str(k).strip()
                        normalized[code] = v
                    except Exception:
                        continue
                return normalized
    except Exception:
        pass
    return {}

def save_etf_cache(cache):
    """ETF 캐시 파일 저장"""
    try:
        with open(ETF_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"ETF 캐시 저장 실패: {e}")

def is_etf_name(name: str) -> bool:
    """ETF 종목명 패턴 확인"""
    etf_keywords = ['KODEX', 'TIGER', 'PLUS', 'Arirang', 'KBSTAR', 'HANARO', 'KOSEF', 'ACE', 'SOL', 'RISE']
    name_upper = name.upper()
    return any(kw.upper() in name_upper for kw in etf_keywords)

def search_kis_stock_by_name(query: str) -> list:
    """KIS API를 통해 종목명으로 검색 (ETF 포함)"""
    try:
        # KIS 종목명 검색 API
        params = {
            "AUTH": "",
            "EXCD": "KOR",  # 한국
            "SYMB": query,
            "GUBN": "0",  # 0: 종목명검색
            "BYMD": "",
            "MODP": "0",
        }
        # KIS 종목 검색 API 사용 (HTS/MTS 종목 검색과 유사)
        # inquire-search 또는 search-stock-info API
        # 실제 KIS API에서는 직접 종목명 검색이 제한적이므로
        # 대안: KRX에서 ETF 목록을 가져오거나 종목코드로 직접 조회
        return []
    except Exception as e:
        print(f"KIS 종목 검색 실패: {e}")
        return []

@app.route('/api/etf-search', methods=['GET'])
def api_etf_search():
    """ETF 종목 검색 (KIS API 사용, 캐시 활용)"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"success": False, "error": "검색어가 필요합니다", "data": []})
    
    try:
        # ETF 캐시에서 먼저 검색
        cache = load_etf_cache()

        # 캐시가 비어있으면 public/korea_etf.csv에서 로드
        if not cache:
            csv_path = os.path.join(os.path.dirname(__file__), 'public', 'korea_etf.csv')
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
                    for ln in lines:
                        parts = ln.split(',')
                        if len(parts) >= 2:
                            code = parts[0].strip()
                            name = ','.join(parts[1:]).strip()
                            cache[code] = {'name': name, 'market': 'ETF'}
                    save_etf_cache(cache)
                except Exception as e:
                    print(f"korea_etf.csv 읽기 실패: {e}")

        results = []
        # 캐시에서 유사한 종목 검색
        for code, info in cache.items():
            name = info.get('name', '') if isinstance(info, dict) else str(info)
            if query.lower() in name.lower() or query in str(code):
                results.append({
                    "code": code,
                    "name": name,
                    "market": info.get('market', 'ETF') if isinstance(info, dict) else 'ETF',
                    "cached": True
                })

        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": []})

@app.route('/api/etf-lookup/<code>', methods=['GET'])
def api_etf_lookup(code):
    """ETF 종목코드로 직접 KIS API 조회 및 캐싱"""
    try:
        code = str(code).zfill(6)
        
        # 캐시 확인
        cache = load_etf_cache()
        if code in cache:
            # If cached entry lacks pricing info, try to enrich from KIS realtime
            entry = cache.get(code, {}) if isinstance(cache, dict) else {}
            needs_enrich = ('currentPrice' not in entry) or (entry.get('currentPrice') in (None, 0))
            if needs_enrich:
                try:
                    kis_data = get_kis_realtime_price(code)
                    if kis_data:
                        for k in ['currentPrice', 'change', 'changePercent', 'volume', 'marketCap', 'per', 'pbr', 'eps']:
                            if k in kis_data and kis_data.get(k) is not None:
                                entry[k] = kis_data[k]
                        cache[code] = entry
                        save_etf_cache(cache)
                except Exception:
                    pass
            return jsonify({"success": True, "code": code, "data": entry, "cached": True})
        
        # KIS API로 종목 정보 조회
        kis_data = get_kis_realtime_price(code)
        
        # accept zero currentPrice as valid (don't treat 0 as missing)
        if not kis_data or ('currentPrice' not in kis_data):
            return jsonify({"success": False, "error": "종목 정보를 찾을 수 없습니다", "data": None})
        
        # 종목명 조회를 위해 다른 API 시도
        name_params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        name_result = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-price", name_params, "FHKST01010100")
        name_output = name_result.get("output", {})
        stock_name = name_output.get("hts_kor_isnm", f"ETF-{code}")
        
        etf_info = {
            "name": stock_name,
            "code": code,
            "market": "ETF",
            "currentPrice": kis_data.get('currentPrice', 0),
            "change": kis_data.get('change', 0),
            "changePercent": kis_data.get('changePercent', 0),
            "volume": kis_data.get('volume', 0),
            "marketCap": kis_data.get('marketCap', 0),
            "per": kis_data.get('per', 0),
            "pbr": kis_data.get('pbr', 0),
            "eps": kis_data.get('eps', 0),
        }
        
        # 캐시 저장
        cache[code] = etf_info
        save_etf_cache(cache)
        
        return jsonify({"success": True, "code": code, "data": etf_info, "cached": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": None})


@app.route('/api/stock-info/<code>', methods=['GET'])
def api_stock_info(code):
    """Merged stock info. Local parquet bars are preferred for price/volume."""
    try:
        code = str(code).zfill(6)
        business_day = get_recent_business_day()

        # Existing fundamentals JSON
        fundamentals = {}
        try:
            with open("public/stock_fundamentals.json", "r", encoding="utf-8") as f:
                fundamentals = json.load(f)
        except Exception:
            fundamentals = {}

        local_bar = get_local_bars_for_codes(business_day, [code]).get(code)
        tickers = load_local_tickers()
        t = tickers.get(code, {})

        base = fundamentals.get(code, {}) if isinstance(fundamentals, dict) else {}

        # Local wins
        if local_bar:
            base = dict(base)
            base["currentPrice"] = local_bar.get("close", base.get("currentPrice", 0))
            base["volume"] = local_bar.get("volume", base.get("volume", 0))
            base["open"] = local_bar.get("open", base.get("open", 0))
            base["high"] = local_bar.get("high", base.get("high", 0))
            base["low"] = local_bar.get("low", base.get("low", 0))
            base["date"] = business_day

        # Master enrichment
        if t:
            base = dict(base)
            if t.get("name"):
                base["name"] = t.get("name")
            if t.get("market"):
                base["market"] = t.get("market")

        # If no base data found but ETF cache has data, return ETF cache entry
        try:
            cache = load_etf_cache()
            if (not base or (isinstance(base, dict) and len(base) == 0)) and code in cache:
                base = dict(cache.get(code, {}))
        except Exception:
            pass

        return jsonify({"success": True, "code": code, "data": base})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ===== 데이터베이스 API 엔드포인트들 =====

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """추천 종목 조회 - KIS API 실패해도 DB 데이터는 반환"""
    kis_api_available = True  # KIS API 사용 가능 여부 플래그
    kis_error_message = None
    
    try:
        filter_tag = request.args.get('filter')
        model_name = (request.args.get('model') or 'model1').lower()
        skip_realtime = request.args.get('skip_realtime', 'false').lower() == 'true'

        allowed_models = {'model1', 'model5'}
        if model_name not in allowed_models:
            return jsonify({"error": f"Unsupported model: {model_name}. Allowed: {sorted(allowed_models)}"}), 400
        
        # DB에서 전체 히스토리 조회 (최신순 -> 기대수익률순)
        q = Recommendation.query
        if filter_tag in {'filter1', 'filter2'}:
            q = q.filter_by(filter_tag=filter_tag)
        if model_name:
            q = q.filter_by(model_name=model_name)
        recs = q.order_by(Recommendation.date.desc(), Recommendation.expected_return.desc()).all()
        
        results = []
        
        # 현재가 조회를 위한 기초 데이터 로드 (로컬 바) - 항상 시도
        local_bars = {}
        try:
            latest_date = get_recent_business_day()
            local_bars = get_local_bars_for_codes(latest_date, [r.code for r in recs])
        except Exception as e:
            print(f"[WARN] Failed to load local bars: {e}")
        
        # KIS API 사용 가능 여부 사전 체크 (첫 번째 종목으로 테스트)
        if not skip_realtime and recs:
            try:
                test_code = recs[0].code.zfill(6)
                test_result = get_kis_realtime_price(test_code)
                if test_result is None or 'error' in str(test_result).lower():
                    kis_api_available = False
                    kis_error_message = "KIS API 연결 실패 - 실시간 가격 조회 불가"
                    print(f"[WARN] KIS API unavailable: {test_result}")
            except Exception as e:
                kis_api_available = False
                kis_error_message = f"KIS API 오류: {str(e)[:100]}"
                print(f"[WARN] KIS API check failed: {e}")
        
        for rec in recs:
            code = rec.code.zfill(6)
            
            # 기본값: 로컬 바 가격 -> 없으면 base_price
            current_price = 0
            if code in local_bars:
                current_price = local_bars[code].get('close', 0)
            if current_price == 0:
                current_price = rec.base_price
            
            current_change = 0
            price_source = 'base'  # 가격 소스: 'base', 'local', 'realtime'
            
            if code in local_bars and local_bars[code].get('close', 0) > 0:
                price_source = 'local'
            
            # KIS API가 사용 가능하고 skip_realtime이 아닐 때만 실시간 조회
            if kis_api_available and not skip_realtime:
                try:
                    now_ts = time.time()
                    cached = _kis_api_cache.get(f"price_{code}")
                    if cached and (now_ts - cached['ts'] < 60):
                        current_price = cached['price']
                        current_change = cached.get('changePercent', 0)
                        price_source = 'realtime'
                    else:
                        kis_price = get_kis_realtime_price(code)
                        if kis_price and kis_price.get('currentPrice', 0) > 0:
                            current_price = float(kis_price['currentPrice'])
                            current_change = float(kis_price.get('changePercent', 0))
                            _kis_api_cache[f"price_{code}"] = {
                                'price': current_price, 
                                'changePercent': current_change,
                                'ts': now_ts
                            }
                            price_source = 'realtime'
                except Exception:
                    pass  # KIS 실패 시 기존 가격 유지
            
            # 수익률 계산
            profit_rate = 0
            if rec.base_price > 0:
                profit_rate = (current_price - rec.base_price) / rec.base_price * 100
                
            results.append({
                'id': rec.id,
                'date': rec.date,
                'filter_tag': getattr(rec, 'filter_tag', 'filter2'),
                'model_name': getattr(rec, 'model_name', 'model1'),
                'code': code,
                'name': rec.name,
                'base_price': rec.base_price,
                'current_price': current_price,
                'current_change': current_change,
                'probability': rec.probability,
                'expected_return': rec.expected_return,
                'market_cap': rec.market_cap,
                'return_rate': profit_rate,
                'price_source': price_source  # 프론트엔드에서 실시간 여부 표시용
            })
        
        response_data = {
            'recommendations': results,
            'kis_api_available': kis_api_available,
            'kis_error': kis_error_message,
            'count': len(results)
        }
        
        # 하위 호환성: 기존 프론트엔드가 배열을 기대할 수 있으므로
        # X-KIS-Available 헤더로 상태 전달하고 본문은 배열 유지
        response = jsonify(results)
        response.headers['X-KIS-Available'] = 'true' if kis_api_available else 'false'
        if kis_error_message:
            response.headers['X-KIS-Error'] = kis_error_message
        return response
        
    except Exception as e:
        print(f"Error in getting recommendations: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/recommendations', methods=['DELETE'])
def delete_recommendations():
    """날짜별/필터별 추천 목록 삭제"""
    try:
        date_str = request.args.get('date')
        filter_tag = request.args.get('filter')
        model_name = (request.args.get('model') or 'model1').lower()

        allowed_models = {'model1', 'model5'}
        if model_name not in allowed_models:
            return jsonify({"error": f"Unsupported model: {model_name}. Allowed: {sorted(allowed_models)}"}), 400
        
        if not date_str:
            return jsonify({"error": "Date is required"}), 400
            
        q = Recommendation.query.filter_by(date=date_str)
        if filter_tag:
            q = q.filter_by(filter_tag=filter_tag)
        if model_name:
            q = q.filter_by(model_name=model_name)
            
        count = q.delete()
        db.session.commit()
        
        return jsonify({"message": f"Deleted {count} recommendations for {date_str} ({filter_tag or 'all filters'} / {model_name})"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/recommendations/predict', methods=['POST'])
def update_recommendations():
    try:
        req_filter = (request.args.get('filter') or 'both').lower()
        model_name = (request.args.get('model') or 'model1').lower()
        
        send_ntfy_notification(f"수동 AI 예측 시작 (모델: {model_name})")

        allowed_models = {'model1', 'model5'}
        if model_name not in allowed_models:
            return jsonify({"error": f"Unsupported model: {model_name}. Allowed: {sorted(allowed_models)}"}), 400

        if req_filter not in {'2', 'filter2'}:
            return jsonify({"error": "Only filter2 is supported for AI predictions."}), 400

        if model_name == 'model5':
            try:
                import lightgbm  # noqa: F401
            except ModuleNotFoundError:
                import sys
                return (
                    jsonify(
                        {
                            "error": "model5 requires the 'lightgbm' package, but it is not installed in the backend Python environment.",
                            "how_to_fix": [
                                "Use the project venv Python to install: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt",
                                "Or install only LightGBM: .\\.venv\\Scripts\\python.exe -m pip install lightgbm",
                                "Then restart the backend server.",
                            ],
                            "backend_python": sys.executable,
                        }
                    ),
                    500,
                )

        # ML 추론 실행 (Filter2 고정)
        print("Running AI Inference (Filter2)...")
        results_by_filter = {
            'filter2': run_inference(
                model_path=None,
                top_k=5,
                min_prob_threshold=0.70,
                min_market_cap_krw=50_000_000_000,
                daily_strength_min=-0.05,
                return_1d_min=-0.05,
                upper_lock_cut=0.295,
                save_result=True,
                model_name=model_name,
            )
        }

        # 종목명 매핑
        from ml.inference import get_stock_name_mapping
        name_map = get_stock_name_mapping()

        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        summary = {}

        for filter_tag, top_candidates in results_by_filter.items():
            if top_candidates is None or top_candidates.empty:
                summary[filter_tag] = {"count": 0}
                continue

            # Inference 기준일(최근 종가 데이터 날짜)을 추천 날짜로 사용
            base_date_val = top_candidates.iloc[0].get('date')
            if hasattr(base_date_val, 'strftime'):
                base_date_str = base_date_val.strftime('%Y-%m-%d')
            else:
                base_date_str = str(base_date_val)[:10]

            # 중복 생성을 막기 위해 동일 기준일+필터+모델 데이터는 삭제 후 재생성
            Recommendation.query.filter_by(date=base_date_str, filter_tag=filter_tag, model_name=model_name).delete()

            new_recs = []
            for _, row in top_candidates.iterrows():
                code = str(row['code']).zfill(6)
                name = name_map.get(code, code)

                rec = Recommendation(
                    date=base_date_str,
                    filter_tag=filter_tag,
                    model_name=model_name,
                    code=code,
                    name=name,
                    base_price=float(row['close']),
                    probability=float(row['positive_proba']),
                    expected_return=float(row['expected_return']),
                    market_cap=float(row['market_cap']),
                    created_at=now_ts,
                )
                db.session.add(rec)
                new_recs.append(rec)

            summary[filter_tag] = {"count": len(new_recs), "date": base_date_str}
            
        db.session.commit()

        # 알림 전송
        for filter_tag, info in summary.items():
            if info.get("count", 0) > 0:
                stocks_list = [Recommendation.query.filter_by(date=info["date"], filter_tag=filter_tag, model_name=model_name).all()]
                # 위 방식은 세션 관리상 위험하므로 names를 루프 안에서 수집
                pass 
        
        # 다시 작성 (루프 안에서 수집하도록)
        notification_msg = []
        for filter_tag, top_candidates in results_by_filter.items():
            if top_candidates is not None and not top_candidates.empty:
                model_stocks = []
                for _, row in top_candidates.iterrows():
                    code = str(row['code']).zfill(6)
                    model_stocks.append(name_map.get(code, code))
                if model_stocks:
                    notification_msg.append(f"[{model_name}] 수동 예측 완료: {', '.join(model_stocks)}")
        
        if notification_msg:
            send_ntfy_notification("\n".join(notification_msg))

        return jsonify({"message": "Prediction complete", "summary": summary})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in running prediction: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups', methods=['GET'])
def get_groups():
    """모든 그룹과 주식 데이터 조회 (성능 최적화 버전)"""
    try:
        groups = Group.query.all()

        # Preload local+json data once per request (fast path)
        business_day = get_recent_business_day()
        fundamentals = load_fundamentals_json()
        tickers = load_local_tickers()

        all_codes = []
        all_stock_ids = []
        for g in groups:
            for s in g.stocks:
                if s.symbol:
                    all_codes.append(str(s.symbol).zfill(6))
                    all_stock_ids.append(s.id)

        local_bars_map = get_local_bars_for_codes(business_day, all_codes) if all_codes else {}
        

        # 모든 거래 내역 한꺼번에 조회 (성능 최적화)
        all_trades = Trade.query.filter(Trade.stock_id.in_(all_stock_ids)).all() if all_stock_ids else []
        trades_by_stock = {}
        for t in all_trades:
            if t.stock_id not in trades_by_stock:
                trades_by_stock[t.stock_id] = []
            trades_by_stock[t.stock_id].append(t)

        result = []
        
        # 전역 캐시 사용
        global _kis_api_cache
        
        for group in groups:
            stocks = []
            for stock in group.stocks:
                code = str(stock.symbol).zfill(6)
                merged = merged_stock_info(code, business_day, fundamentals, local_bars_map, tickers)
                
                memos = [{'id': m.id, 'content': m.content, 'created_at': m.created_at} for m in stock.memos]

                # UI(StockData) shape: keep values stable across reloads
                current_price = merged.get('currentPrice', stock.price) or 0
                volume = merged.get('volume', stock.volume) or 0
                market_cap = merged.get('marketCap', stock.market_cap) or 0

                # 수익률 계산 (매수/매도 기록 기반)
                trades = trades_by_stock.get(stock.id, [])
                buy_qty = sum(t.quantity for t in trades if t.trade_type == 'buy')
                buy_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'buy')
                sell_qty = sum(t.quantity for t in trades if t.trade_type == 'sell')
                sell_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'sell')
                
                remaining = buy_qty - sell_qty
                avg_price = buy_amt / buy_qty if buy_qty > 0 else 0
                
                return_rate = 0
                total_profit = 0
                if buy_qty > 0:
                    current_val = remaining * current_price
                    invested = remaining * avg_price
                    realized = sell_amt - (sell_qty * avg_price) if sell_qty > 0 else 0
                    unrealized = current_val - invested
                    total_profit = realized + unrealized
                    return_rate = (total_profit / buy_amt * 100) if buy_amt > 0 else 0

                q_margins = merged.get('quarterlyMargins', [])
                if not isinstance(q_margins, list):
                    q_margins = []

                major_stake_raw = merged.get('major_shareholder_stake', merged.get('majorShareholderStake', '0'))
                try:
                    if isinstance(major_stake_raw, str):
                        major_stake = float(major_stake_raw.replace('%', '').strip() or 0)
                    else:
                        major_stake = float(major_stake_raw or 0)
                except Exception:
                    major_stake = 0.0


                # 로컬에 없으면 stock.per 등 DB값 쓰는데 혹시 0이면 merged(stock_fundamentals.json) 확인
                per_val = float(merged.get('per', stock.per) or 0)
                pbr_val = float(merged.get('pbr', stock.pbr) or 0)
                eps_val = float(merged.get('eps', stock.eps) or 0)
                foreign_val = float(merged.get('foreignOwnership', getattr(stock, 'foreign_ownership', 0)) or 0)
                
                # ------ KIS API Fallback & Caching Logic ------
                # DB/Local 값이 모두 0인 경우, KIS API 호출 시도하여 보완
                # 매번 호출하면 느리므로 메모리 캐시(_kis_api_cache) 우선 확인
                # 캐시에도 없으면 호출 후 캐시 및 DB 업데이트
                
                is_missing_data = (per_val == 0 and pbr_val == 0) # 주요 지표 누락 기준
                
                if is_missing_data:
                    # 1. Check Memory Cache
                    cache_key = f"{code}_{business_day}"
                    cached_data = _kis_api_cache.get(cache_key)
                    
                    if cached_data:
                        # 캐시된 데이터 사용 (0이 아닌 값만)
                        per_val = cached_data.get('per', per_val)
                        pbr_val = cached_data.get('pbr', pbr_val)
                        eps_val = cached_data.get('eps', eps_val)
                        foreign_val = cached_data.get('foreignOwnership', foreign_val)
                        if cached_data.get('marketCap'): market_cap = cached_data.get('marketCap')
                    
                    # 2. Still missing? Call API
                    if per_val == 0 and pbr_val == 0:
                        # API 호출 (타임아웃 짧게 설정 권장하나 여기선 기본값)
                        # get_kis_realtime_price 내부적으로 토큰 체크 등을 수행함
                        try:
                            kis_data = get_kis_realtime_price(code)
                            if kis_data:
                                # Update variables
                                if kis_data.get('per'): per_val = float(kis_data['per'])
                                if kis_data.get('pbr'): pbr_val = float(kis_data['pbr'])
                                if kis_data.get('eps'): eps_val = float(kis_data['eps'])
                                if kis_data.get('foreignOwnership'): foreign_val = float(kis_data['foreignOwnership'])
                                if kis_data.get('marketCap'): market_cap = str(kis_data['marketCap'])
                                
                                # Update DB (Persistence)
                                stock.per = per_val
                                stock.pbr = pbr_val
                                stock.eps = eps_val
                                stock.market_cap = int(float(market_cap or 0))
                                # foreignOwnership은 DB 컬럼 없음 -> 캐시에만 의존
                                
                                db.session.add(stock) # mark as dirty
                                
                                # Update Cache
                                _kis_api_cache[cache_key] = {
                                    'per': per_val,
                                    'pbr': pbr_val,
                                    'eps': eps_val,
                                    'foreignOwnership': foreign_val,
                                    'marketCap': market_cap
                                }
                        except Exception as e:
                            print(f"KIS API Fallback failed for {code}: {e}")
                
                # -----------------------------------------------

                stocks.append({
                    'id': stock.id,
                    'symbol': code,
                    'name': merged.get('name') or stock.name,
                    'currentPrice': float(current_price),
                    'per': per_val,
                    'pbr': pbr_val,
                    'eps': eps_val,
                    'floatingShares': str(merged.get('floatingShares', '0')),
                    'majorShareholderStake': major_stake,
                    'marketCap': str(market_cap),
                    'tradingVolume': str(volume),
                    'transactionAmount': str(merged.get('transactionAmount', merged.get('value', '0')) or '0'),
                    'foreignOwnership': foreign_val,
                    'quarterlyMargins': q_margins,
                    'memos': [{'id': m['id'], 'date': m['created_at'], 'content': m['content']} for m in memos],
                    'addedAt': stock.added_at,
                    
                    # 수익률 정보 추가
                    'returnRate': return_rate,
                    'totalProfit': total_profit,
                    'avgBuyPrice': avg_price,
                    'remainingQuantity': remaining,

                    # Backward/compat fields still used by some UI calls
                    'price': float(current_price),
                    'change': float(merged.get('change', stock.change) or 0),
                    'changePercent': float(merged.get('changePercent', stock.change_percent) or 0),
                    'volume': int(volume),
                    'sector': stock.sector,
                })
            
            result.append({
                'id': group.id,
                'name': group.name,
                'date': group.date,
                'stocks': stocks
            })
        
        # 변경된 주식 정보 저장 (PER, PBR 등의 업데이트)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in get_groups: {str(e)}")
        return jsonify({"error": str(e)}), 500
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups', methods=['POST'])
def create_group():
    """새 그룹 생성"""
    try:
        data = request.get_json()
        group_name = data.get('name')
        stocks_data = data.get('stocks', [])
        
        if not group_name:
            return jsonify({"error": "그룹 이름이 필요합니다"}), 400
        
        # 그룹 생성
        group_id = str(int(time.time() * 1000))
        date_str = datetime.now().isoformat()
        
        new_group = Group(id=group_id, name=group_name, date=date_str)
        db.session.add(new_group)
        
        # 주식들 추가
        for stock_data in stocks_data:
            stock_id = f"{stock_data.get('symbol', 'UNKNOWN')}-{int(time.time() * 1000)}-{len(stocks_data)}"
            # Accept both UI naming and legacy naming
            symbol = str(stock_data.get('symbol', '')).zfill(6)
            current_price = stock_data.get('currentPrice', stock_data.get('price', 0))
            market_cap_raw = stock_data.get('marketCap', stock_data.get('market_cap', 0))
            volume_raw = stock_data.get('tradingVolume', stock_data.get('volume', 0))

            try:
                market_cap_val = int(str(market_cap_raw).replace(',', '') or 0)
            except Exception:
                market_cap_val = 0
            try:
                volume_val = int(str(volume_raw).replace(',', '') or 0)
            except Exception:
                volume_val = 0

            new_stock = Stock(
                id=stock_id,
                group_id=group_id,
                symbol=symbol,
                name=stock_data.get('name', ''),
                price=float(current_price or 0),
                change=stock_data.get('change', 0),
                change_percent=stock_data.get('changePercent', 0),
                volume=volume_val,
                market_cap=market_cap_val,
                per=stock_data.get('per', 0),
                pbr=stock_data.get('pbr', 0),
                eps=stock_data.get('eps', 0),
                sector=stock_data.get('sector', ''),
                added_at=date_str
            )
            db.session.add(new_stock)
        
        db.session.commit()
        return jsonify({"success": True, "group_id": group_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups/<group_id>', methods=['PUT'])
def update_group(group_id):
    """그룹 이름 수정"""
    try:
        data = request.get_json()
        new_name = data.get('name')
        
        if not new_name:
            return jsonify({"error": "새 그룹 이름이 필요합니다"}), 400
        
        group = Group.query.get(group_id)
        if not group:
            return jsonify({"error": "그룹을 찾을 수 없습니다"}), 404
        
        group.name = new_name
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    """그룹 삭제 (연관된 주식들도 모두 삭제)"""
    try:
        group = Group.query.get(group_id)
        if not group:
            return jsonify({"error": "그룹을 찾을 수 없습니다"}), 404
        
        db.session.delete(group)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/groups/<group_id>/stocks', methods=['POST'])
def add_stock_to_group(group_id):
    """기존 그룹에 종목 추가"""
    try:
        group = Group.query.get(group_id)
        if not group:
            return jsonify({"error": "그룹을 찾을 수 없습니다"}), 404
        
        data = request.get_json()
        stocks_data = data.get('stocks', [])
        
        if not stocks_data:
            return jsonify({"error": "추가할 종목이 필요합니다"}), 400
        
        added_stocks = []
        for stock_data in stocks_data:
            stock_id = f"{stock_data.get('symbol', 'UNKNOWN')}-{int(time.time() * 1000)}-{len(stocks_data)}"
            symbol = str(stock_data.get('symbol', '')).zfill(6)
            current_price = stock_data.get('currentPrice', stock_data.get('price', 0))
            market_cap_raw = stock_data.get('marketCap', stock_data.get('market_cap', 0))
            volume_raw = stock_data.get('tradingVolume', stock_data.get('volume', 0))

            try:
                market_cap_val = int(str(market_cap_raw).replace(',', '') or 0)
            except Exception:
                market_cap_val = 0
            try:
                volume_val = int(str(volume_raw).replace(',', '') or 0)
            except Exception:
                volume_val = 0

            new_stock = Stock(
                id=stock_id,
                group_id=group_id,
                symbol=symbol,
                name=stock_data.get('name', ''),
                price=float(current_price or 0),
                change=stock_data.get('change', 0),
                change_percent=stock_data.get('changePercent', 0),
                volume=volume_val,
                market_cap=market_cap_val,
                per=stock_data.get('per', 0),
                pbr=stock_data.get('pbr', 0),
                eps=stock_data.get('eps', 0),
                sector=stock_data.get('sector', ''),
                added_at=datetime.now().isoformat()
            )
            db.session.add(new_stock)
            added_stocks.append(stock_id)
        
        db.session.commit()
        return jsonify({"success": True, "added_stocks": added_stocks})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<stock_id>', methods=['PUT'])
def update_stock(stock_id):
    """주식 정보 업데이트"""
    try:
        data = request.get_json()
        
        stock = Stock.query.get(stock_id)
        if not stock:
            return jsonify({"error": "주식을 찾을 수 없습니다"}), 404
        
        # 업데이트할 필드들 (UI: currentPrice, legacy: price)
        if 'currentPrice' in data:
            stock.price = data['currentPrice']
        elif 'price' in data:
            stock.price = data['price']
        if 'change' in data:
            stock.change = data['change']
        if 'changePercent' in data:
            stock.change_percent = data['changePercent']
        if 'tradingVolume' in data:
            try:
                stock.volume = int(str(data['tradingVolume']).replace(',', '') or 0)
            except Exception:
                pass
        elif 'volume' in data:
            stock.volume = data['volume']
        if 'marketCap' in data:
            try:
                stock.market_cap = int(str(data['marketCap']).replace(',', '') or 0)
            except Exception:
                pass
        if 'per' in data:
            stock.per = data['per']
        if 'pbr' in data:
            stock.pbr = data['pbr']
        if 'eps' in data:
            stock.eps = data['eps']
        if 'sector' in data:
            stock.sector = data['sector']
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<stock_id>', methods=['DELETE'])
def delete_stock(stock_id):
    """주식 삭제"""
    try:
        stock = Stock.query.get(stock_id)
        if not stock:
            return jsonify({"error": "주식을 찾을 수 없습니다"}), 404
        
        db.session.delete(stock)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<stock_id>/memos', methods=['POST'])
def add_memo(stock_id):
    """메모 추가"""
    try:
        data = request.get_json()
        content = data.get('content')
        
        if not content:
            return jsonify({"error": "메모 내용이 필요합니다"}), 400
        
        stock = Stock.query.get(stock_id)
        if not stock:
            return jsonify({"error": "주식을 찾을 수 없습니다"}), 404
        
        memo_id = f"{stock_id}-memo-{int(time.time() * 1000)}"
        new_memo = Memo(
            id=memo_id,
            stock_id=stock_id,
            content=content,
            created_at=datetime.now().isoformat()
        )
        
        db.session.add(new_memo)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "memo": {
                "id": memo_id,
                "content": content,
                "created_at": new_memo.created_at
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/memos/<memo_id>', methods=['DELETE'])
def delete_memo(memo_id):
    """메모 삭제"""
    try:
        memo = Memo.query.get(memo_id)
        if not memo:
            return jsonify({"error": "메모를 찾을 수 없습니다"}), 404
        
        db.session.delete(memo)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ===== 캔들차트 데이터 API (./data parquet 우선) =====
@app.route('/api/stock-bars/<code>', methods=['GET'])
def api_stock_bars(code):
    """종목 캔들차트 데이터 조회 (./data/krx/bars 파티션에서 로드)"""
    try:
        code = str(code).zfill(6)
        days = request.args.get('days', 60, type=int)
        
        if pq is None or not os.path.isdir(KRX_BARS_DIR):
            return jsonify({"success": False, "error": "데이터없음", "data": []})
        
        # 파티션 날짜 목록 수집
        partition_dates = []
        for name in os.listdir(KRX_BARS_DIR):
            d = _parse_partition_date(name)
            if d:
                partition_dates.append(d)
        
        if not partition_dates:
            return jsonify({"success": False, "error": "데이터없음", "data": []})
        
        partition_dates.sort(reverse=True)
        recent_dates = partition_dates[:days]
        
        bars = []
        for dt in sorted(recent_dates):
            date_yyyymmdd = dt.strftime("%Y%m%d")
            bar_map = get_local_bars_for_codes(date_yyyymmdd, [code])
            if code in bar_map:
                b = bar_map[code]
                bars.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "time": dt.strftime("%m/%d"),
                    "open": b.get("open", 0),
                    "high": b.get("high", 0),
                    "low": b.get("low", 0),
                    "close": b.get("close", 0),
                    "volume": b.get("volume", 0),
                })
        
        if not bars:
            return jsonify({"success": False, "error": "데이터없음", "data": []})
        
        return jsonify({"success": True, "code": code, "data": bars})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": []})


# ===== 투자자별 수급 동향 크롤링 (네이버 금융) =====
@app.route('/api/investor-trends/<code>', methods=['GET'])
def api_investor_trends(code):
    """외국인/기관/개인 수급 동향 (네이버 금융 크롤링)"""
    try:
        code = str(code).zfill(6)
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({"success": False, "error": "조회안됨", "data": []})
        
        # HTML 파싱
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 테이블 찾기 (외국인/기관 매매동향)
        table = soup.select_one('table.type2')
        if not table:
            return jsonify({"success": False, "error": "조회안됨", "data": []})
        
        rows = table.select('tr')
        trends = []
        
        for row in rows[2:22]:  # 최근 20일
            cols = row.select('td')
            if len(cols) < 9:
                continue
            try:
                date_text = cols[0].get_text(strip=True)
                if not date_text or '.' not in date_text:
                    continue
                
                # 외국인 순매수 (6번째 컬럼), 기관 순매수 (9번째 컬럼)
                foreign_net = cols[5].get_text(strip=True).replace(',', '').replace('+', '')
                institution_net = cols[8].get_text(strip=True).replace(',', '').replace('+', '')
                
                foreign_val = int(foreign_net) if foreign_net.lstrip('-').isdigit() else 0
                institution_val = int(institution_net) if institution_net.lstrip('-').isdigit() else 0
                individual_val = -(foreign_val + institution_val)  # 제로섬
                
                trends.append({
                    "date": date_text,
                    "foreign": foreign_val,
                    "institution": institution_val,
                    "individual": individual_val,
                })
            except Exception:
                continue
        
        if not trends:
            return jsonify({"success": False, "error": "조회안됨", "data": []})
        
        return jsonify({"success": True, "code": code, "data": list(reversed(trends))})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": []})


# ===== 포트폴리오(그룹) 수익률 모니터링 (삭제됨 - 아래 get_group_returns 사용) =====
# 참고: /api/groups/<group_id>/returns 엔드포인트는 Trade 기반 수익률 계산 함수 사용


# ===== 종목 매입가 업데이트 =====
@app.route('/api/stocks/<stock_id>/purchase-price', methods=['PUT'])
def api_update_purchase_price(stock_id):
    """종목 매입가 설정 (수익률 계산용)"""
    try:
        data = request.get_json()
        purchase_price = data.get('purchasePrice', 0)
        
        stock_record = Stock.query.get(stock_id)
        if not stock_record:
            return jsonify({"error": "주식을 찾을 수 없습니다"}), 404
        
        stock_record.price = float(purchase_price or 0)
        db.session.commit()
        
        return jsonify({"success": True, "purchasePrice": stock_record.price})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# -----------------------------
# KIS API: 재무비율 (Financial Ratio)
# -----------------------------
@app.route('/api/financial-ratio/<code>', methods=['GET'])
def get_financial_ratio(code):
    """
    KIS 재무비율 API - ROE, EPS, BPS, 매출/영업이익 증가율 등
    분기별(1) 또는 연도별(0) 데이터 조회
    """
    try:
        code = str(code).zfill(6)
        div_cls = request.args.get('period', '1')  # 1: 분기, 0: 연도

        token = get_kis_access_token()
        if not token:
            return jsonify({"error": "KIS 토큰 발급 실패"}), 500

        params = {
            "fid_div_cls_code": div_cls,
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        
        result = call_kis_api(
            "/uapi/domestic-stock/v1/finance/financial-ratio",
            params,
            "FHKST66430300"
        )

        output = result.get("output", [])
        if not output:
            return jsonify({"data": [], "message": "조회결과없음"})

        # 데이터 정리
        data = []
        for item in output[:12]:  # 최근 12분기(3년) 또는 12년
            data.append({
                "period": item.get("stac_yymm", ""),  # 결산년월
                "salesGrowth": float(item.get("grs", 0) or 0),  # 매출액 증가율
                "operatingProfitGrowth": float(item.get("bsop_prfi_inrt", 0) or 0),  # 영업이익 증가율
                "netIncomeGrowth": float(item.get("ntin_inrt", 0) or 0),  # 순이익 증가율
                "roe": float(item.get("roe_val", 0) or 0),  # ROE
                "eps": float(item.get("eps", "0").replace(",", "") or 0),  # EPS
                "sps": float(item.get("sps", "0").replace(",", "") if item.get("sps") else 0),  # 주당매출액
                "bps": float(item.get("bps", "0").replace(",", "") if item.get("bps") else 0),  # BPS
                "reserveRate": float(item.get("rsrv_rate", 0) or 0),  # 유보비율
                "debtRate": float(item.get("lblt_rate", 0) or 0),  # 부채비율
            })
        
        return jsonify({"data": data, "code": code, "period": "quarterly" if div_cls == "1" else "yearly"})
    except Exception as e:
        print(f"Financial ratio error for {code}: {e}")
        return jsonify({"error": str(e)}), 500


# -----------------------------
# KIS API: 손익계산서 (Income Statement)
# -----------------------------
@app.route('/api/income-statement/<code>', methods=['GET'])
def get_income_statement(code):
    """
    KIS 손익계산서 API - 매출액, 영업이익, 당기순이익 등
    분기별(1) 또는 연도별(0) 데이터 조회
    """
    try:
        code = str(code).zfill(6)
        div_cls = request.args.get('period', '1')  # 1: 분기, 0: 연도

        token = get_kis_access_token()
        if not token:
            return jsonify({"error": "KIS 토큰 발급 실패"}), 500

        params = {
            "fid_div_cls_code": div_cls,
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        
        result = call_kis_api(
            "/uapi/domestic-stock/v1/finance/income-statement",
            params,
            "FHKST66430200"
        )

        output = result.get("output", [])
        if not output:
            return jsonify({"data": [], "message": "조회결과없음"})

        # 데이터 정리 + 영업이익률 계산
        data = []
        for item in output[:12]:  # 최근 12분기
            sales = float(item.get("sale_account", "0").replace(",", "") or 0)
            operating_profit = float(item.get("bsop_prti", "0").replace(",", "") or 0)
            
            # 영업이익률 계산 (매출액 대비 영업이익)
            op_margin = (operating_profit / sales * 100) if sales > 0 else 0
            
            data.append({
                "period": item.get("stac_yymm", ""),  # 결산년월
                "sales": sales,  # 매출액 (억)
                "saleCost": float(item.get("sale_cost", "0").replace(",", "") or 0),  # 매출원가
                "grossProfit": float(item.get("sale_totl_prfi", "0").replace(",", "") or 0),  # 매출총이익
                "operatingProfit": operating_profit,  # 영업이익
                "ordinaryProfit": float(item.get("op_prfi", "0").replace(",", "") or 0),  # 경상이익
                "netIncome": float(item.get("thtr_ntin", "0").replace(",", "") or 0),  # 당기순이익
                "operatingMargin": round(op_margin, 2),  # 영업이익률 (%)
            })
        
        return jsonify({"data": data, "code": code, "period": "quarterly" if div_cls == "1" else "yearly"})
    except Exception as e:
        print(f"Income statement error for {code}: {e}")
        return jsonify({"error": str(e)}), 500


# -----------------------------
# KIS API: 투자자별 매매동향 (Investor Trading)
# -----------------------------
@app.route('/api/kis-investor-trends/<code>', methods=['GET'])
def get_kis_investor_trends(code):
    """
    KIS 투자자별 매매동향 API - 외국인/기관/개인 순매수
    네이버 크롤링보다 더 정확한 데이터
    """
    try:
        code = str(code).zfill(6)

        token = get_kis_access_token()
        if not token:
            return jsonify({"error": "KIS 토큰 발급 실패"}), 500

        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        
        result = call_kis_api(
            "/uapi/domestic-stock/v1/quotations/inquire-investor",
            params,
            "FHKST01010900"
        )

        output = result.get("output", [])
        if not output:
            return jsonify({"data": [], "message": "조회결과없음"})

        # 데이터 정리
        data = []
        for item in output[:30]:  # 최근 30일
            data.append({
                "date": item.get("stck_bsop_date", ""),  # 영업일자
                "closePrice": int(item.get("stck_clpr", 0) or 0),  # 종가
                "priceChange": int(item.get("prdy_vrss", 0) or 0),  # 전일대비
                "changeSign": item.get("prdy_vrss_sign", "3"),  # 부호 (1:상한,2:상승,3:보합,4:하락,5:하한)
                "individualNet": int(item.get("prsn_ntby_qty", 0) or 0),  # 개인 순매수
                "foreignNet": int(item.get("frgn_ntby_qty", 0) or 0),  # 외국인 순매수
                "institutionNet": int(item.get("orgn_ntby_qty", 0) or 0),  # 기관 순매수
                "individualNetAmount": int(item.get("prsn_ntby_tr_pbmn", 0) or 0),  # 개인 순매수금액
                "foreignNetAmount": int(item.get("frgn_ntby_tr_pbmn", 0) or 0),  # 외국인 순매수금액
                "institutionNetAmount": int(item.get("orgn_ntby_tr_pbmn", 0) or 0),  # 기관 순매수금액
            })
        
        return jsonify({"data": data, "code": code})
    except Exception as e:
        print(f"KIS investor trends error for {code}: {e}")
        return jsonify({"error": str(e)}), 500


# ===== Trade (매매) 관리 API =====

@app.route('/api/stocks/<stock_id>/trades', methods=['GET'])
def get_trades(stock_id):
    """특정 주식의 매매 내역 조회"""
    try:
        trades = Trade.query.filter_by(stock_id=stock_id).order_by(Trade.trade_date.desc()).all()
        result = []
        for t in trades:
            result.append({
                'id': t.id,
                'stockId': t.stock_id,
                'tradeType': t.trade_type,
                'quantity': t.quantity,
                'price': t.price,
                'tradeDate': t.trade_date,
                'memo': t.memo
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<stock_id>/trades', methods=['POST'])
def add_trade(stock_id):
    """매매 내역 추가"""
    try:
        data = request.get_json()
        stock = Stock.query.get(stock_id)
        if not stock:
            return jsonify({"error": f"주식을 찾을 수 없습니다: {stock_id}"}), 404
        
        trade_id = f"trade-{int(time.time() * 1000)}"
        new_trade = Trade(
            id=trade_id,
            stock_id=stock_id,
            trade_type=data.get('tradeType', 'buy'),
            quantity=int(data.get('quantity', 0)),
            price=float(data.get('price', 0)),
            trade_date=data.get('tradeDate', datetime.now().strftime('%Y-%m-%d')),
            created_at=datetime.now().isoformat(),
            memo=data.get('memo', '')
        )
        db.session.add(new_trade)
        db.session.commit()
        
        return jsonify({
            'id': new_trade.id,
            'stockId': new_trade.stock_id,
            'tradeType': new_trade.trade_type,
            'quantity': new_trade.quantity,
            'price': new_trade.price,
            'tradeDate': new_trade.trade_date,
            'memo': new_trade.memo
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/trades/<trade_id>', methods=['PUT'])
def update_trade(trade_id):
    """매매 내역 수정"""
    try:
        trade = Trade.query.get(trade_id)
        if not trade:
            return jsonify({"error": "매매 내역을 찾을 수 없습니다"}), 404
        
        data = request.get_json()
        if 'tradeType' in data:
            trade.trade_type = data['tradeType']
        if 'quantity' in data:
            trade.quantity = int(data['quantity'])
        if 'price' in data:
            trade.price = float(data['price'])
        if 'tradeDate' in data:
            trade.trade_date = data['tradeDate']
        if 'memo' in data:
            trade.memo = data['memo']
        
        db.session.commit()
        
        return jsonify({
            'id': trade.id,
            'stockId': trade.stock_id,
            'tradeType': trade.trade_type,
            'quantity': trade.quantity,
            'price': trade.price,
            'tradeDate': trade.trade_date,
            'memo': trade.memo
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/trades/<trade_id>', methods=['DELETE'])
def delete_trade(trade_id):
    """매매 내역 삭제"""
    try:
        trade = Trade.query.get(trade_id)
        if not trade:
            return jsonify({"error": "매매 내역을 찾을 수 없습니다"}), 404
        
        db.session.delete(trade)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/stocks/<stock_id>/returns', methods=['GET'])
def get_stock_returns(stock_id):
    """특정 주식의 수익률 계산"""
    try:
        stock = Stock.query.get(stock_id)
        if not stock:
            return jsonify({"error": "주식을 찾을 수 없습니다"}), 404
        
        trades = Trade.query.filter_by(stock_id=stock_id).order_by(Trade.trade_date).all()
        
        total_buy_quantity = 0
        total_buy_amount = 0
        total_sell_quantity = 0
        total_sell_amount = 0
        
        for t in trades:
            if t.trade_type == 'buy':
                total_buy_quantity += t.quantity
                total_buy_amount += t.quantity * t.price
            else:  # sell
                total_sell_quantity += t.quantity
                total_sell_amount += t.quantity * t.price
        
        remaining_quantity = total_buy_quantity - total_sell_quantity
        avg_buy_price = total_buy_amount / total_buy_quantity if total_buy_quantity > 0 else 0
        
        # 현재가 가져오기
        code = str(stock.symbol).zfill(6)
        kis_data = get_kis_realtime_price(code)
        current_price = kis_data.get('currentPrice', stock.price) or 0
        
        # 현재 평가금액
        current_value = remaining_quantity * current_price
        # 투자 원금 (현재 보유 수량 기준)
        invested_amount = remaining_quantity * avg_buy_price
        # 실현 손익
        realized_profit = total_sell_amount - (total_sell_quantity * avg_buy_price) if total_sell_quantity > 0 else 0
        # 평가 손익
        unrealized_profit = current_value - invested_amount
        # 총 손익
        total_profit = realized_profit + unrealized_profit
        # 수익률
        return_rate = (total_profit / total_buy_amount * 100) if total_buy_amount > 0 else 0
        
        return jsonify({
            'stockId': stock_id,
            'symbol': code,
            'name': stock.name,
            'totalBuyQuantity': total_buy_quantity,
            'totalBuyAmount': total_buy_amount,
            'totalSellQuantity': total_sell_quantity,
            'totalSellAmount': total_sell_amount,
            'remainingQuantity': remaining_quantity,
            'avgBuyPrice': avg_buy_price,
            'currentPrice': current_price,
            'currentValue': current_value,
            'investedAmount': invested_amount,
            'realizedProfit': realized_profit,
            'unrealizedProfit': unrealized_profit,
            'totalProfit': total_profit,
            'returnRate': return_rate
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups/<group_id>/returns', methods=['GET'])
def get_group_returns(group_id):
    """그룹 전체의 수익률 계산 (성능 최적화 버전)"""
    try:
        group = Group.query.get(group_id)
        if not group:
            return jsonify({"error": "그룹을 찾을 수 없습니다"}), 404
        
        # 모든 종목의 심볼 수집
        stock_codes = [str(s.symbol).zfill(6) for s in group.stocks]
        
        # 현재 시장가 정보 한꺼번에 가져오기 (실시간 대신 로컬 데이터 활용하여 성능 향상)
        business_day = get_recent_business_day()
        local_prices = get_local_bars_for_codes(business_day, stock_codes)
        
        stocks_returns = []
        total_invested = 0
        total_current_value = 0
        total_realized = 0
        total_unrealized = 0
        
        # 모든 거래 내역 한꺼번에 조회 (성능 최적화)
        stock_ids = [s.id for s in group.stocks]
        all_trades = Trade.query.filter(Trade.stock_id.in_(stock_ids)).all()
        trades_by_stock = {}
        for t in all_trades:
            if t.stock_id not in trades_by_stock:
                trades_by_stock[t.stock_id] = []
            trades_by_stock[t.stock_id].append(t)
        
        for stock in group.stocks:
            trades = trades_by_stock.get(stock.id, [])
            if not trades:
                continue
                
            buy_qty = sum(t.quantity for t in trades if t.trade_type == 'buy')
            buy_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'buy')
            sell_qty = sum(t.quantity for t in trades if t.trade_type == 'sell')
            sell_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'sell')
            
            remaining = buy_qty - sell_qty
            avg_price = buy_amt / buy_qty if buy_qty > 0 else 0
            
            code = str(stock.symbol).zfill(6)
            
            # 로컬 데이터에 있으면 사용, 없으면 Stock DB의 가격 사용 (KIS 개별 호출 지양)
            if code in local_prices:
                current_price = local_prices[code]['close']
            else:
                current_price = stock.price or 0
            
            current_val = remaining * current_price
            invested = remaining * avg_price
            realized = sell_amt - (sell_qty * avg_price) if sell_qty > 0 else 0
            unrealized = current_val - invested
            
            if buy_qty > 0:
                stocks_returns.append({
                    'stockId': stock.id,
                    'symbol': code,
                    'name': stock.name,
                    'remainingQuantity': remaining,
                    'avgBuyPrice': avg_price,
                    'currentPrice': current_price,
                    'investedAmount': invested,
                    'currentValue': current_val,
                    'realizedProfit': realized,
                    'unrealizedProfit': unrealized,
                    'returnRate': ((realized + unrealized) / buy_amt * 100) if buy_amt > 0 else 0
                })
                
                total_invested += invested
                total_current_value += current_val
                total_realized += realized
                total_unrealized += unrealized
        
        total_profit = total_realized + total_unrealized
        group_return_rate = (total_profit / total_invested * 100) if total_invested > 0 else 0
        
        return jsonify({
            'groupId': group_id,
            'groupName': group.name,
            'stocks': stocks_returns,
            'summary': {
                'totalInvested': total_invested,
                'totalCurrentValue': total_current_value,
                'totalRealizedProfit': total_realized,
                'totalUnrealizedProfit': total_unrealized,
                'totalProfit': total_profit,
                'returnRate': group_return_rate
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/groups/<group_id>/returns/history', methods=['GET'])
def get_group_returns_history(group_id):
    """포트폴리오 수익률 히스토리 조회 (최초 매수일부터 현재까지)"""
    try:
        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"history": []})
        
        # 1. 모든 거래 내역 수집 및 최초 매수일 확인
        stock_ids = [s.id for s in group.stocks]
        all_trades = Trade.query.filter(Trade.stock_id.in_(stock_ids)).order_by(Trade.trade_date).all()
        
        if not all_trades:
            return jsonify({"history": [], "message": "거래 내역이 없습니다"})
            
        first_trade_date = all_trades[0].trade_date[:10]
        
        # 2. 기존 캐시된 히스토리 조회
        existing_history = PortfolioHistory.query.filter_by(group_id=group_id).order_by(PortfolioHistory.date).all()
        cached_dates = {h.date for h in existing_history}
        
        # 3. 계산해야 할 날짜 목록 (데이터가 있는 날짜 중 최초 매수일 이후)
        bars_dir = Path("data/krx/bars")
        available_dates = []
        if bars_dir.exists():
            for d in bars_dir.iterdir():
                if d.is_dir() and d.name.startswith("date="):
                    date_val = d.name.replace("date=", "")
                    if date_val >= first_trade_date:
                        available_dates.append(date_val)
        available_dates.sort()
        
        new_dates = [d for d in available_dates if d not in cached_dates]
        
        if new_dates:
            # 4. 각 날짜별 보유 현황 및 수익률 계산
            # 성능을 위해 반복문 밖에서 로직 최적화
            for date_str in new_dates:
                # 해당 날짜까지의 거래 내역으로 보유량/원금 계산
                current_holdings = {} # code -> {'qty': 0, 'cost': 0}
                for t in all_trades:
                    if t.trade_date[:10] > date_str:
                        break
                    
                    # stock_id에 해당하는 symbol 찾기
                    s_obj = next((s for s in group.stocks if s.id == t.stock_id), None)
                    if not s_obj: continue
                    code = str(s_obj.symbol).zfill(6)
                    
                    if code not in current_holdings:
                        current_holdings[code] = {'qty': 0, 'cost': 0}
                    
                    if t.trade_type == 'buy':
                        current_holdings[code]['qty'] += t.quantity
                        current_holdings[code]['cost'] += t.quantity * t.price

                    else: # sell (선입선출 혹은 단순 평균단가 적용 - 여기서는 단순 비율 차감)
                        if current_holdings[code]['qty'] > 0:
                            avg_p = current_holdings[code]['cost'] / current_holdings[code]['qty']
                            current_holdings[code]['cost'] -= t.quantity * avg_p
                            current_holdings[code]['qty'] -= t.quantity
                
                # 해당 날짜의 종가 데이터 로드
                # _read_bars_partition_df 는 캐싱이 적용되어 있음
                bars_df = _read_bars_partition_df(date_str.replace("-", ""))
                if bars_df is None or bars_df.empty:
                    continue
                
                weighted_return_sum = 0
                total_weight = 0
                total_current_value_sum = 0
                
                for code, info in current_holdings.items():
                    if info['qty'] <= 0: continue
                    
                    invested = info['cost']
                    current_val = invested # 기본값
                    
                    # bars_df에서 종가 찾기
                    if bars_df is not None and not bars_df.empty:
                        row = bars_df[bars_df['code'] == code]
                        if not row.empty:
                            price = float(row.iloc[0]['close'])
                            current_val = info['qty'] * price
                    
                    # 개별 자산 수익률 (Ri = (Current - Invested) / Invested * 100)
                    r_i = ((current_val - invested) / invested * 100) if invested > 0 else 0
                    
                    # 자산 비중 (wi) - 사용자 요청 공식 (w1R1 + ... wnRn)/(w1 + ... wn) 
                    # 여기서 비중 w는 매입 금액(invested)을 사용하여 투자금 대비 수익률 영향도를 측정
                    w_i = invested
                    
                    weighted_return_sum += w_i * r_i
                    total_weight += w_i
                    total_current_value_sum += current_val
                
                if total_weight > 0:
                    # 포트폴리오 가중 평균 수익률
                    final_return_rate = weighted_return_sum / total_weight
                    
                    history_entry = PortfolioHistory(
                        group_id=group_id,
                        date=date_str,
                        total_invested=total_weight,
                        total_value=total_current_value_sum,
                        return_rate=final_return_rate,
                        created_at=datetime.now().isoformat()
                    )
                    db.session.add(history_entry)
            
            db.session.commit()

        # 5. 전체 히스토리 다시 조회하여 반환
        all_history = PortfolioHistory.query.filter_by(group_id=group_id).order_by(PortfolioHistory.date).all()
        result = [
            {
                "date": h.date,
                "returnRate": round(h.return_rate, 2),
                "totalValue": round(h.total_value, 0),
                "totalInvested": round(h.total_invested, 0)
            }
            for h in all_history
        ]
        
        return jsonify({"history": result})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ===== Journal (일지) 관리 API =====

@app.route('/api/journals', methods=['GET'])
def get_journals():
    """일지 목록 조회"""
    try:
        category = request.args.get('category')
        query = Journal.query
        
        if category:
            query = query.filter_by(category=category)
        
        journals = query.order_by(Journal.created_at.desc()).all()
        result = []
        for j in journals:
            result.append({
                'id': j.id,
                'title': j.title,
                'content': j.content,
                'category': j.category,
                'tags': j.tags.split(',') if j.tags else [],
                'stockSymbols': j.stock_symbols.split(',') if j.stock_symbols else [],
                'createdAt': j.created_at,
                'updatedAt': j.updated_at
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/journals', methods=['POST'])
def create_journal():
    """일지 작성"""
    try:
        data = request.get_json()
        journal_id = f"journal-{int(time.time() * 1000)}"
        now = datetime.now().isoformat()
        
        tags = data.get('tags', [])
        if isinstance(tags, list):
            tags = ','.join(tags)
        
        stock_symbols = data.get('stockSymbols', [])
        if isinstance(stock_symbols, list):
            stock_symbols = ','.join(stock_symbols)
        
        new_journal = Journal(
            id=journal_id,
            title=data.get('title', ''),
            content=data.get('content', ''),
            category=data.get('category', '분석'),
            tags=tags,
            stock_symbols=stock_symbols,
            created_at=now,
            updated_at=now
        )
        db.session.add(new_journal)
        db.session.commit()
        
        return jsonify({
            'id': new_journal.id,
            'title': new_journal.title,
            'content': new_journal.content,
            'category': new_journal.category,
            'tags': new_journal.tags.split(',') if new_journal.tags else [],
            'stockSymbols': new_journal.stock_symbols.split(',') if new_journal.stock_symbols else [],
            'createdAt': new_journal.created_at,
            'updatedAt': new_journal.updated_at
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/journals/<journal_id>', methods=['GET'])
def get_journal(journal_id):
    """일지 상세 조회"""
    try:
        journal = Journal.query.get(journal_id)
        if not journal:
            return jsonify({"error": "일지를 찾을 수 없습니다"}), 404
        
        return jsonify({
            'id': journal.id,
            'title': journal.title,
            'content': journal.content,
            'category': journal.category,
            'tags': journal.tags.split(',') if journal.tags else [],
            'stockSymbols': journal.stock_symbols.split(',') if journal.stock_symbols else [],
            'createdAt': journal.created_at,
            'updatedAt': journal.updated_at
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/journals/<journal_id>', methods=['PUT'])
def update_journal(journal_id):
    """일지 수정"""
    try:
        journal = Journal.query.get(journal_id)
        if not journal:
            return jsonify({"error": "일지를 찾을 수 없습니다"}), 404
        
        data = request.get_json()
        if 'title' in data:
            journal.title = data['title']
        if 'content' in data:
            journal.content = data['content']
        if 'category' in data:
            journal.category = data['category']
        if 'tags' in data:
            tags = data['tags']
            if isinstance(tags, list):
                tags = ','.join(tags)
            journal.tags = tags
        if 'stockSymbols' in data:
            stock_symbols = data['stockSymbols']
            if isinstance(stock_symbols, list):
                stock_symbols = ','.join(stock_symbols)
            journal.stock_symbols = stock_symbols
        
        journal.updated_at = datetime.now().isoformat()
        db.session.commit()
        
        return jsonify({
            'id': journal.id,
            'title': journal.title,
            'content': journal.content,
            'category': journal.category,
            'tags': journal.tags.split(',') if journal.tags else [],
            'stockSymbols': journal.stock_symbols.split(',') if journal.stock_symbols else [],
            'createdAt': journal.created_at,
            'updatedAt': journal.updated_at
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/journals/<journal_id>', methods=['DELETE'])
def delete_journal(journal_id):
    """일지 삭제"""
    try:
        journal = Journal.query.get(journal_id)
        if not journal:
            return jsonify({"error": "일지를 찾을 수 없습니다"}), 404
        
        db.session.delete(journal)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ===== 시장 지수 API (KOSPI/KOSDAQ) =====

@app.route('/api/market-indices', methods=['GET'])
def get_market_indices():
    """KOSPI/KOSDAQ 지수 조회"""
    try:
        indices = {}
        
        # KOSPI 지수 (0001)
        kospi_params = {
            "fid_cond_mrkt_div_code": "U",
            "fid_input_iscd": "0001"
        }
        kospi_result = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-index-price", kospi_params, "FHPUP02100000")
        kospi_output = kospi_result.get("output", {})
        
        indices['kospi'] = {
            'name': 'KOSPI',
            'currentValue': float(kospi_output.get("bstp_nmix_prpr", 0) or 0),
            'change': float(kospi_output.get("bstp_nmix_prdy_vrss", 0) or 0),
            'changePercent': float(kospi_output.get("bstp_nmix_prdy_ctrt", 0) or 0),
            'high': float(kospi_output.get("bstp_nmix_hgpr", 0) or 0),
            'low': float(kospi_output.get("bstp_nmix_lwpr", 0) or 0),
            'open': float(kospi_output.get("bstp_nmix_oprc", 0) or 0),
        }
        
        # KOSDAQ 지수 (1001)
        kosdaq_params = {
            "fid_cond_mrkt_div_code": "U",
            "fid_input_iscd": "1001"
        }
        kosdaq_result = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-index-price", kosdaq_params, "FHPUP02100000")
        kosdaq_output = kosdaq_result.get("output", {})
        
        indices['kosdaq'] = {
            'name': 'KOSDAQ',
            'currentValue': float(kosdaq_output.get("bstp_nmix_prpr", 0) or 0),
            'change': float(kosdaq_output.get("bstp_nmix_prdy_vrss", 0) or 0),
            'changePercent': float(kosdaq_output.get("bstp_nmix_prdy_ctrt", 0) or 0),
            'high': float(kosdaq_output.get("bstp_nmix_hgpr", 0) or 0),
            'low': float(kosdaq_output.get("bstp_nmix_lwpr", 0) or 0),
            'open': float(kosdaq_output.get("bstp_nmix_oprc", 0) or 0),
        }
        
        return jsonify(indices)
    except Exception as e:
        print(f"Market indices error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-investor-trends', methods=['GET'])
def get_market_investor_trends():
    """시장 전체 투자자별 매매동향"""
    try:
        # 코스피 투자자별 순매수
        params = {
            "fid_cond_mrkt_div_code": "V",
            "fid_input_iscd": "0001",  # KOSPI
            "fid_input_date_1": "",
            "fid_input_date_2": "",
            "fid_period_div_code": "D"
        }
        result = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-investor", params, "FHPTJ04010000")
        output = result.get("output", [])
        
        data = []
        for item in output[:20]:  # 최근 20일
            data.append({
                "date": item.get("stck_bsop_date", ""),
                "individual": int(item.get("prsn_ntby_qty", 0) or 0),
                "foreign": int(item.get("frgn_ntby_qty", 0) or 0),
                "institution": int(item.get("orgn_ntby_qty", 0) or 0),
            })
        
        return jsonify({"data": data})
    except Exception as e:
        print(f"Market investor trends error: {e}")
        return jsonify({"error": str(e)}), 500


# =============================
# 스케줄러 및 자동 실행 관련
# =============================

def reset_scheduler_state_if_new_day():
    """새로운 날짜라면 스케줄러 상태를 리셋 (최근 수집 정보는 유지)"""
    global _scheduler_state
    today = datetime.now().strftime('%Y-%m-%d')
    with _scheduler_lock:
        if _scheduler_state["last_check_date"] != today:
            _scheduler_state["eod_done_today"] = False
            _scheduler_state["intraday_done_today"] = False
            _scheduler_state["inference_done_today"] = False
            _scheduler_state["auto_start_done_today"] = False
            _scheduler_state["last_check_date"] = today
            _scheduler_state["crawling_status"] = None
            _scheduler_state["crawling_error"] = None
            # 최근 수집 정보는 유지 (last_crawl_* 필드들)
            print(f"[Scheduler] New day detected: {today}, state reset.")


def check_internet_connection(timeout: int = 5) -> bool:
    """인터넷 연결 확인 (여러 호스트 시도)"""
    hosts = [
        "https://www.google.com",
        "https://www.naver.com",
        "https://openapi.koreainvestment.com:9443"
    ]
    for host in hosts:
        try:
            requests.get(host, timeout=timeout)
            return True
        except Exception:
            continue
    return False


def check_network_and_retry(max_retries: int = 3, delay: int = 10) -> bool:
    """네트워크 연결 확인 및 재시도"""
    for attempt in range(max_retries):
        if check_internet_connection():
            return True
        print(f"[Network] Connection failed, retry {attempt + 1}/{max_retries} in {delay}s...")
        time.sleep(delay)
    return False


def send_ntfy_notification(message):
    """ntfy.sh를 통해 알림 전송"""
    print(f"[Ntfy] Attempting to send message: {message[:50]}...")
    try:
        topic_url = "https://ntfy.sh/wayne-akdlrjf0924"
        # 헤더에 한글이 포함되면 latin-1 인코딩 에러가 발생하므로 제거하거나 인코딩 필요
        resp = requests.post(topic_url, 
                      data=message.encode('utf-8'),
                      headers={
                          "Title": "MyStocks Notification", # ASCII 가능하도록 변경
                          "Priority": "default"
                      },
                      timeout=10)
        print(f"[Ntfy] Notification sent! Status: {resp.status_code}")
    except Exception as e:
        print(f"[Ntfy] Notification failed: {e}")


@app.route('/api/test-notification', methods=['GET'])
def test_notification_api():
    """알림 테스트용 API"""
    send_ntfy_notification("테스트 알림입니다 (API 호출)")
    return jsonify({"message": "Test notification sent"}), 200


def run_crawl_eod(max_retries: int = 3):
    """EOD 모드로 크롤링 실행 (유니버스 캐시 생성) - 네트워크 오류 시 재시도"""
    global _scheduler_state
    start_time = datetime.now()
    target_date = datetime.now().strftime('%Y-%m-%d')
    
    with _scheduler_lock:
        _scheduler_state["crawling_status"] = "eod"
        _scheduler_state["crawling_start_time"] = start_time.isoformat()
        _scheduler_state["crawling_error"] = None
    
    print("[Scheduler] Starting EOD crawl (--mode eod --merge)...")
    
    for attempt in range(max_retries):
        # 네트워크 연결 확인
        if not check_network_and_retry(max_retries=2, delay=5):
            print(f"[Scheduler] Network unavailable, attempt {attempt + 1}/{max_retries}")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = "Network connection failed"
            if attempt < max_retries - 1:
                time.sleep(30)  # 30초 후 재시도
                continue
            break
        
        try:
            result = subprocess.run(
                [sys.executable, "crawl.py", "--mode", "eod", "--workers", "8", "--merge"],
                cwd=os.path.dirname(__file__) or ".",
                capture_output=True,
                text=True,
                timeout=3600  # 1시간 타임아웃
            )
            end_time = datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            if result.returncode == 0:
                # 파티션 무결성 검증
                partition_ok = _verify_partition_integrity(target_date)
                if not partition_ok:
                    print(f"[Scheduler] Partition integrity check failed, attempting repair...")
                    _repair_partition_if_needed(target_date)
                
                print("[Scheduler] EOD crawl completed successfully.")
                send_ntfy_notification("데이터수집 완료 (EOD 모드)")
                with _scheduler_lock:
                    _scheduler_state["eod_done_today"] = True
                    _scheduler_state["last_crawl_completed_at"] = end_time.isoformat()
                    _scheduler_state["last_crawl_mode"] = "eod (auto)"
                    _scheduler_state["last_crawl_date_range"] = target_date
                    _scheduler_state["last_crawl_duration"] = duration_seconds
                return True
            else:
                error_msg = result.stderr[:500] if result.stderr else "Unknown error"
                print(f"[Scheduler] EOD crawl failed (attempt {attempt + 1}): {error_msg}")
                
                # 네트워크 관련 에러인지 확인
                if any(keyword in error_msg.lower() for keyword in ['network', 'connection', 'timeout', 'unreachable']):
                    print(f"[Scheduler] Network error detected, will retry...")
                    if attempt < max_retries - 1:
                        time.sleep(30)
                        continue
                
                with _scheduler_lock:
                    _scheduler_state["crawling_error"] = error_msg
                    
        except subprocess.TimeoutExpired:
            print(f"[Scheduler] EOD crawl timeout (attempt {attempt + 1})")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = "Crawl timeout (1 hour)"
            if attempt < max_retries - 1:
                continue
                
        except Exception as e:
            print(f"[Scheduler] EOD crawl exception (attempt {attempt + 1}): {e}")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = str(e)
            if attempt < max_retries - 1:
                time.sleep(30)
                continue
        
        break  # 성공하거나 재시도 불필요한 실패 시 루프 탈출
    
    # 실패 시 파티션 복구 시도
    _repair_partition_if_needed(target_date)
    
    with _scheduler_lock:
        _scheduler_state["crawling_status"] = None
    return False


def _verify_partition_integrity(target_date: str) -> bool:
    """파티션 파일 무결성 검증 (code 컬럼 존재 여부 등)"""
    try:
        import pandas as pd
        partition_path = f"data/krx/bars/date={target_date}/part-0000.parquet"
        if not os.path.exists(partition_path):
            return False
        df = pd.read_parquet(partition_path)
        required_cols = ['date', 'code', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            print(f"[Verify] Missing columns in {target_date}: {missing}")
            return False
        if df.empty:
            print(f"[Verify] Empty dataframe for {target_date}")
            return False
        return True
    except Exception as e:
        print(f"[Verify] Partition integrity check error: {e}")
        return False


def _repair_partition_if_needed(target_date: str) -> bool:
    """파티션 오류 시 복구 시도"""
    try:
        if _verify_partition_integrity(target_date):
            return True
        
        print(f"[Repair] Attempting to repair partition for {target_date}...")
        result = subprocess.run(
            [sys.executable, "crawl.py", "--repair-date", target_date],
            cwd=os.path.dirname(__file__) or ".",
            capture_output=True,
            text=True,
            timeout=300  # 5분 타임아웃
        )
        
        if result.returncode == 0:
            print(f"[Repair] Successfully repaired partition for {target_date}")
            return True
        else:
            print(f"[Repair] Failed to repair: {result.stderr}")
            return False
    except Exception as e:
        print(f"[Repair] Exception during repair: {e}")
        return False


def run_crawl_intraday(max_retries: int = 3):
    """Intraday 모드로 크롤링 실행 (유니버스만 업데이트) - 네트워크 오류 시 재시도"""
    global _scheduler_state
    start_time = datetime.now()
    target_date = datetime.now().strftime('%Y-%m-%d')
    
    with _scheduler_lock:
        _scheduler_state["crawling_status"] = "intraday"
        _scheduler_state["crawling_start_time"] = start_time.isoformat()
        _scheduler_state["crawling_error"] = None
    
    print("[Scheduler] Starting intraday crawl (--mode intraday)...")
    
    for attempt in range(max_retries):
        # 네트워크 연결 확인
        if not check_network_and_retry(max_retries=2, delay=5):
            print(f"[Scheduler] Network unavailable, attempt {attempt + 1}/{max_retries}")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = "Network connection failed"
            if attempt < max_retries - 1:
                time.sleep(15)  # 15초 후 재시도
                continue
            break
        
        try:
            result = subprocess.run(
                [sys.executable, "crawl.py", "--mode", "intraday", "--workers", "8"],
                cwd=os.path.dirname(__file__) or ".",
                capture_output=True,
                text=True,
                timeout=1800  # 30분 타임아웃
            )
            end_time = datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            if result.returncode == 0:
                # 파티션 무결성 검증
                partition_ok = _verify_partition_integrity(target_date)
                if not partition_ok:
                    print(f"[Scheduler] Partition integrity check failed, attempting repair...")
                    _repair_partition_if_needed(target_date)
                
                print("[Scheduler] Intraday crawl completed successfully.")
                send_ntfy_notification("데이터수집 완료 (Intraday 모드)")
                with _scheduler_lock:
                    _scheduler_state["intraday_done_today"] = True
                    _scheduler_state["last_crawl_completed_at"] = end_time.isoformat()
                    _scheduler_state["last_crawl_mode"] = "intraday (auto)"
                    _scheduler_state["last_crawl_date_range"] = target_date
                    _scheduler_state["last_crawl_duration"] = duration_seconds
                with _scheduler_lock:
                    _scheduler_state["crawling_status"] = None
                return True
            else:
                error_msg = result.stderr[:500] if result.stderr else "Unknown error"
                print(f"[Scheduler] Intraday crawl failed (attempt {attempt + 1}): {error_msg}")
                
                # 네트워크 관련 에러인지 확인
                if any(keyword in error_msg.lower() for keyword in ['network', 'connection', 'timeout', 'unreachable']):
                    print(f"[Scheduler] Network error detected, will retry...")
                    if attempt < max_retries - 1:
                        time.sleep(15)
                        continue
                
                with _scheduler_lock:
                    _scheduler_state["crawling_error"] = error_msg
                    
        except subprocess.TimeoutExpired:
            print(f"[Scheduler] Intraday crawl timeout (attempt {attempt + 1})")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = "Crawl timeout (30 min)"
            if attempt < max_retries - 1:
                continue
                
        except Exception as e:
            print(f"[Scheduler] Intraday crawl exception (attempt {attempt + 1}): {e}")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = str(e)
            if attempt < max_retries - 1:
                time.sleep(15)
                continue
        
        break
    
    # 실패 시 파티션 복구 시도
    _repair_partition_if_needed(target_date)
    
    with _scheduler_lock:
        _scheduler_state["crawling_status"] = None
    return False


def run_inference_for_models():
    """model1과 model5로 inference 실행하여 DB에 저장"""
    global _scheduler_state
    print("[Scheduler] Running inference for model1 and model5...")
    
    notification_msg = []
    
    try:
        from ml.inference import get_stock_name_mapping
        name_map = get_stock_name_mapping()
        
        for model_name in ['model1', 'model5']:
            print(f"[Scheduler] Running inference for {model_name}...")
            top_candidates = run_inference(
                model_path=None,
                top_k=5,
                min_prob_threshold=0.70,
                min_market_cap_krw=50_000_000_000,
                daily_strength_min=-0.05,
                return_1d_min=-0.05,
                upper_lock_cut=0.295,
                save_result=True,
                model_name=model_name,
            )
            
            if top_candidates is not None and not top_candidates.empty:
                base_date_val = top_candidates.iloc[0].get('date')
                if hasattr(base_date_val, 'strftime'):
                    base_date_str = base_date_val.strftime('%Y-%m-%d')
                else:
                    base_date_str = str(base_date_val)[:10]
                
                model_stocks = []
                with app.app_context():
                    # 중복 제거
                    Recommendation.query.filter_by(
                        date=base_date_str, 
                        filter_tag='filter2', 
                        model_name=model_name
                    ).delete()
                    
                    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    for _, row in top_candidates.iterrows():
                        code = str(row['code']).zfill(6)
                        name = name_map.get(code, code)
                        model_stocks.append(name)
                        rec = Recommendation(
                            date=base_date_str,
                            filter_tag='filter2',
                            model_name=model_name,
                            code=code,
                            name=name,
                            base_price=float(row['close']),
                            probability=float(row['positive_proba']),
                            expected_return=float(row['expected_return']),
                            market_cap=float(row['market_cap']),
                            created_at=now_ts,
                        )
                        db.session.add(rec)
                    
                    db.session.commit()
                    print(f"[Scheduler] {model_name} inference saved: {len(top_candidates)} stocks for {base_date_str}")
                    
                if model_stocks:
                    notification_msg.append(f"[{model_name}] 추천: {', '.join(model_stocks)}")
        
        with _scheduler_lock:
            _scheduler_state["inference_done_today"] = True
        
        if notification_msg:
            send_ntfy_notification("\n".join(notification_msg))
            
        print("[Scheduler] All inference completed.")
        
    except Exception as e:
        print(f"[Scheduler] Inference failed: {e}")
        import traceback
        traceback.print_exc()


def scheduler_tick():
    """스케줄러 1회 체크"""
    reset_scheduler_state_if_new_day()
    
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    
    # 인터넷 연결 확인
    if not check_internet_connection():
        return
    
    with _scheduler_lock:
        eod_done = _scheduler_state["eod_done_today"]
        intraday_done = _scheduler_state["intraday_done_today"]
        inference_done = _scheduler_state["inference_done_today"]
        auto_start_done = _scheduler_state["auto_start_done_today"]
        crawling = _scheduler_state["crawling_status"]
    
    # 크롤링 중이면 스킵
    if crawling:
        return
    
    # 08:35~08:50: 자동매매 자동 시작 체크
    if hour == 8 and 35 <= minute <= 50 and not auto_start_done:
        try:
            # DB에서 auto_start_mode 설정 확인
            auto_start_setting = AutoTradingSettings.query.filter_by(key='auto_start_mode').first()
            if auto_start_setting and auto_start_setting.value == 'auto':
                # 거래일인지 확인
                trading_day_check = is_trading_day()
                if trading_day_check:
                    # 엔진이 이미 실행중인지 확인
                    if _auto_trading_engine is None or not _auto_trading_engine.is_running():
                        print(f"[Scheduler] Auto-start enabled and it's a trading day. Starting auto-trading engine...")
                        # 자동매매 시작
                        global _auto_trading_thread
                        mode = 'mock'  # 기본값은 모의투자
                        mode_setting = AutoTradingSettings.query.filter_by(key='trading_mode').first()
                        if mode_setting:
                            mode = mode_setting.value
                        
                        engine = AutoTradingEngine(is_mock=(mode == 'mock'))
                        _auto_trading_engine = engine
                        _auto_trading_thread = threading.Thread(target=engine.run, daemon=True)
                        _auto_trading_thread.start()
                        print(f"[Scheduler] Auto-trading engine started in {mode} mode.")
                        send_ntfy_notification(f"🤖 자동매매 자동 시작됨 ({mode} 모드)")
                    else:
                        print(f"[Scheduler] Auto-trading engine already running.")
                else:
                    print(f"[Scheduler] Not a trading day, skipping auto-start.")
            
            with _scheduler_lock:
                _scheduler_state["auto_start_done_today"] = True
        except Exception as e:
            print(f"[Scheduler] Auto-start check failed: {e}")
    
    # 15시~15시30분: Intraday 모드로 유니버스 업데이트 + Inference (1회)
    if hour == 15 and 0 <= minute < 30:
        if not intraday_done:
            print(f"[Scheduler] Time window 15:00-15:30, running intraday crawl...")
            # 동기적으로 실행하여 완료 후 inference 실행
            def intraday_then_inference():
                success = run_crawl_intraday()
                if success and not _scheduler_state["inference_done_today"]:
                    run_inference_for_models()
            threading.Thread(target=intraday_then_inference, daemon=True).start()

    # 16시~17시: EOD 모드로 최종 종가 수집 및 유니버스 캐시 생성 (1회)
    if 16 <= hour < 17 and not eod_done:
        print(f"[Scheduler] Time window 16:00-17:00, running EOD crawl for final prices...")
        threading.Thread(target=run_crawl_eod, daemon=True).start()


def scheduler_loop():
    """스케줄러 메인 루프 (30초마다 체크)"""
    print("[Scheduler] Scheduler thread started.")
    while True:
        try:
            scheduler_tick()
        except Exception as e:
            print(f"[Scheduler] Error in tick: {e}")
        time.sleep(30)


def start_scheduler_thread():
    """스케줄러 백그라운드 스레드 시작"""
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    print("[Scheduler] Background scheduler thread started.")


# =============================
# 스케줄러 상태 및 크롤링 상태 API
# =============================

@app.route('/api/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """스케줄러 및 크롤링 상태 조회"""
    with _scheduler_lock:
        return jsonify({
            "eod_done_today": _scheduler_state["eod_done_today"],
            "intraday_done_today": _scheduler_state["intraday_done_today"],
            "inference_done_today": _scheduler_state["inference_done_today"],
            "last_check_date": _scheduler_state["last_check_date"],
            "crawling_status": _scheduler_state["crawling_status"],  # 'eod' | 'intraday' | None
            "crawling_start_time": _scheduler_state["crawling_start_time"],
            "crawling_error": _scheduler_state["crawling_error"],
            # 최근 수집 완료 정보
            "last_crawl_completed_at": _scheduler_state["last_crawl_completed_at"],
            "last_crawl_mode": _scheduler_state["last_crawl_mode"],
            "last_crawl_date_range": _scheduler_state["last_crawl_date_range"],
            "last_crawl_duration": _scheduler_state["last_crawl_duration"],
        })


@app.route('/api/scheduler/trigger', methods=['POST'])
def trigger_scheduler_task():
    """수동으로 스케줄러 작업 트리거"""
    task = request.args.get('task')  # 'eod' | 'intraday' | 'inference'
    
    with _scheduler_lock:
        if _scheduler_state["crawling_status"]:
            return jsonify({"error": "Another crawling task is already running."}), 400
    
    if task == 'eod':
        send_ntfy_notification("수동 EOD 수집 시작")
        threading.Thread(target=run_crawl_eod, daemon=True).start()
        return jsonify({"message": "EOD crawl started."})
    elif task == 'intraday':
        send_ntfy_notification("수동 Intraday 수집 시작")
        threading.Thread(target=run_crawl_intraday, daemon=True).start()
        return jsonify({"message": "Intraday crawl started."})
    elif task == 'inference':
        send_ntfy_notification("수동 AI 예측 시작")
        threading.Thread(target=run_inference_for_models, daemon=True).start()
        return jsonify({"message": "Inference started."})
    else:
        return jsonify({"error": "Invalid task. Use 'eod', 'intraday', or 'inference'."}), 400


def run_crawl_with_dates(start_date: str, end_date: str, mode: str = 'eod'):
    """날짜 범위로 크롤링 실행"""
    global _scheduler_state
    crawl_start_time = datetime.now()
    
    with _scheduler_lock:
        _scheduler_state["crawling_status"] = mode
        _scheduler_state["crawling_start_time"] = crawl_start_time.isoformat()
        _scheduler_state["crawling_error"] = None
    
    try:
        print(f"[Crawler] Running {mode} crawl from {start_date} to {end_date}...")
        python_exec = sys.executable
        cmd = [
            python_exec, "crawl.py",
            "--mode", mode,
            "--start-date", start_date,
            "--end-date", end_date,
            "--merge"
        ]
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(__file__) or ".",
            capture_output=True,
            text=True,
            timeout=3600  # 1시간 타임아웃
        )
        crawl_end_time = datetime.now()
        duration_seconds = (crawl_end_time - crawl_start_time).total_seconds()
        
        if result.returncode == 0:
            print(f"[Crawler] {mode} crawl ({start_date} ~ {end_date}) completed successfully.")
            send_ntfy_notification(f"수동 데이터수집 완료 ({mode} 모드, {start_date}~{end_date})")
            with _scheduler_lock:
                _scheduler_state["last_crawl_completed_at"] = crawl_end_time.isoformat()
                _scheduler_state["last_crawl_mode"] = f"{mode} (manual)"
                _scheduler_state["last_crawl_date_range"] = f"{start_date} ~ {end_date}" if start_date != end_date else start_date
                _scheduler_state["last_crawl_duration"] = duration_seconds
            return True
        else:
            print(f"[Crawler] {mode} crawl failed: {result.stderr}")
            with _scheduler_lock:
                _scheduler_state["crawling_error"] = result.stderr[:500] if result.stderr else "Unknown error"
            return False
    except Exception as e:
        print(f"[Crawler] {mode} crawl exception: {e}")
        with _scheduler_lock:
            _scheduler_state["crawling_error"] = str(e)
        return False
    finally:
        with _scheduler_lock:
            _scheduler_state["crawling_status"] = None


@app.route('/api/crawl', methods=['POST'])
def manual_crawl():
    """수동 데이터 수집 API"""
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    mode = data.get('mode', 'eod')  # 'eod' or 'intraday'
    
    # 기본값: 오늘 날짜
    today = datetime.now().strftime('%Y-%m-%d')
    if not start_date:
        start_date = today
    if not end_date:
        end_date = start_date
    
    # 날짜 형식 검증
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    
    with _scheduler_lock:
        if _scheduler_state["crawling_status"]:
            return jsonify({"error": "Another crawling task is already running."}), 400
    
    send_ntfy_notification(f"수동 데이터수집 시작 ({mode} 모드, {start_date}~{end_date})")
    
    # 백그라운드에서 실행
    threading.Thread(
        target=run_crawl_with_dates, 
        args=(start_date, end_date, mode),
        daemon=True
    ).start()
    
    return jsonify({
        "message": f"{mode.upper()} crawl started for {start_date} to {end_date}.",
        "start_date": start_date,
        "end_date": end_date,
        "mode": mode
    })


# =============================
# 개별 추천 삭제 API
# =============================

@app.route('/api/recommendations/<int:rec_id>', methods=['DELETE'])
def delete_single_recommendation(rec_id):
    """개별 추천 종목 삭제"""
    try:
        rec = Recommendation.query.get(rec_id)
        if not rec:
            return jsonify({"error": "Recommendation not found"}), 404
        
        db.session.delete(rec)
        db.session.commit()
        return jsonify({"message": f"Deleted recommendation {rec_id}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =============================
# 실시간 가격 조회 API (배치)
# =============================

@app.route('/api/realtime-prices', methods=['POST'])
def get_realtime_prices():
    """여러 종목의 실시간 가격을 한번에 조회 (KIS API)"""
    try:
        data = request.get_json() or {}
        codes = data.get('codes', [])
        
        if not codes or len(codes) > 20:
            return jsonify({"error": "Provide 1-20 stock codes"}), 400
        
        results = {}
        for code in codes:
            code = str(code).zfill(6)
            try:
                # 캐시 확인 (5초)
                now_ts = time.time()
                cached = _kis_api_cache.get(f"price_{code}")
                if cached and (now_ts - cached['ts'] < 5):
                    results[code] = {
                        'current_price': cached['price'],
                        'change_percent': cached.get('changePercent', 0),
                    }
                else:
                    kis_price = get_kis_realtime_price(code)
                    if kis_price and kis_price.get('currentPrice', 0) > 0:
                        current_price = float(kis_price['currentPrice'])
                        change_percent = float(kis_price.get('changePercent', 0))
                        _kis_api_cache[f"price_{code}"] = {
                            'price': current_price,
                            'changePercent': change_percent,
                            'ts': now_ts
                        }
                        results[code] = {
                            'current_price': current_price,
                            'change_percent': change_percent,
                        }
                    else:
                        results[code] = {'current_price': None, 'change_percent': None}
            except Exception as e:
                results[code] = {'current_price': None, 'change_percent': None, 'error': str(e)}
            
            # KIS API rate limit 방지 (0.2초 딜레이)
            time.sleep(0.2)
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================
# KIS 계좌 조회 및 주문 API
# =============================

# 계좌번호 (환경변수에서 로드)
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")  # 예: "12345678-01"
# 자산 히스토리 (간단한 메모리 저장, 실제 서비스에서는 DB 사용)
_asset_history = []

def call_kis_trading_api(endpoint, params=None, tr_id="TTTC8434R", method="GET", body=None, use_mock=True):
    """KIS 트레이딩 API 호출 (계좌 조회, 주문 등)
    
    Args:
        use_mock: True면 모의투자 URL/TR_ID 사용, False면 실전투자
    """
    token = get_kis_access_token()
    if not token:
        return {"error": "토큰 발급 실패"}
    
    # 모의투자/실전투자에 따라 URL과 TR_ID 변경
    if use_mock:
        base_url = "https://openapivts.koreainvestment.com:29443"
        # TR_ID 앞자리를 V로 변경 (모의투자)
        if tr_id.startswith("T"):
            tr_id = "V" + tr_id[1:]
    else:
        base_url = "https://openapi.koreainvestment.com:9443"
    
    url = f"{base_url}{endpoint}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P"
    }
    
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=body, timeout=10)
        else:
            response = requests.get(url, headers=headers, params=params, timeout=10)
        
        print(f"KIS Trading API [{tr_id}] 응답: {response.status_code} (mock={use_mock})")
        if response.status_code != 200:
            return {"error": f"API 오류: {response.status_code}", "detail": response.text}
        
        return response.json()
    except Exception as e:
        print(f"KIS Trading API 호출 실패: {e}")
        return {"error": str(e)}


@app.route('/api/kis/account-balance', methods=['GET'])
def api_kis_account_balance():
    """KIS 계좌 잔고/자산현황 조회"""
    try:
        if not KIS_ACCOUNT_NO:
            return jsonify({
                "success": False,
                "error": "KIS_ACCOUNT_NO 환경변수가 설정되지 않았습니다.",
                "hint": "환경변수에 KIS_ACCOUNT_NO=계좌번호-상품코드 형식으로 설정하세요 (예: 12345678-01)"
            }), 200  # 400 대신 200으로 반환하여 프론트엔드에서 처리 가능
        
        if not APP_KEY or not APP_SECRET:
            return jsonify({
                "success": False,
                "error": "KIS API 인증 정보가 설정되지 않았습니다.",
                "hint": "환경변수에 KIS_APP_KEY, KIS_APP_SECRET을 설정하세요"
            }), 200
        
        account_parts = KIS_ACCOUNT_NO.split("-")
        if len(account_parts) != 2:
            return jsonify({
                "success": False,
                "error": "KIS_ACCOUNT_NO 형식이 잘못되었습니다.",
                "hint": "형식: 계좌번호-상품코드 (예: 12345678-01)"
            }), 200
        
        cano = account_parts[0]  # 계좌번호 앞 8자리
        acnt_prdt_cd = account_parts[1]  # 계좌번호 뒤 2자리
        
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",  # 시간외단일가여부
            "OFL_YN": "",  # 오프라인여부
            "INQR_DVSN": "02",  # 조회구분 (01: 대출일별, 02: 종목별)
            "UNPR_DVSN": "01",  # 단가구분
            "FUND_STTL_ICLD_YN": "N",  # 펀드결제분포함여부
            "FNCG_AMT_AUTO_RDPT_YN": "N",  # 융자금액자동상환여부
            "PRCS_DVSN": "00",  # 처리구분 (00: 전일매매포함, 01: 전일매매미포함)
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        # 잔고조회 API (TTTC8434R: 주식잔고조회) - 모의투자 모드 사용
        result = call_kis_trading_api(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            params=params,
            tr_id="TTTC8434R",
            use_mock=True  # 모의투자 모드
        )
        
        if "error" in result:
            return jsonify(result), 500
        
        output1 = result.get("output1", [])  # 보유종목 리스트
        output2 = result.get("output2", [{}])[0] if result.get("output2") else {}  # 계좌 총계
        
        # 보유종목 정보 파싱
        holdings = []
        for item in output1:
            holding = {
                "code": item.get("pdno", ""),  # 종목코드
                "name": item.get("prdt_name", ""),  # 종목명
                "quantity": int(item.get("hldg_qty", 0) or 0),  # 보유수량
                "avgPrice": float(item.get("pchs_avg_pric", 0) or 0),  # 매입평균가
                "currentPrice": int(item.get("prpr", 0) or 0),  # 현재가
                "evalAmount": int(item.get("evlu_amt", 0) or 0),  # 평가금액
                "profitLoss": int(item.get("evlu_pfls_amt", 0) or 0),  # 평가손익금액
                "profitRate": float(item.get("evlu_pfls_rt", 0) or 0),  # 평가손익률
                "purchaseAmount": int(item.get("pchs_amt", 0) or 0),  # 매입금액
            }
            holdings.append(holding)
        
        # 계좌 총계 정보
        account_summary = {
            "totalEvalAmount": int(output2.get("tot_evlu_amt", 0) or 0),  # 총평가금액
            "totalPurchaseAmount": int(output2.get("pchs_amt_smtl_amt", 0) or 0),  # 매입금액합계
            "totalProfitLoss": int(output2.get("evlu_pfls_smtl_amt", 0) or 0),  # 평가손익합계
            "totalProfitRate": float(output2.get("evlu_pfls_rt", 0) or 0) if output2.get("evlu_pfls_rt") else 0,  # 평가손익률
            "depositBalance": int(output2.get("dnca_tot_amt", 0) or 0),  # 예수금총액
            "availableCash": int(output2.get("nass_amt", 0) or 0),  # 순자산금액
            "d2Deposit": int(output2.get("prvs_rcdl_excc_amt", 0) or 0),  # D+2 예수금
        }
        
        # 자산 히스토리에 추가 (간단한 시계열 데이터)
        global _asset_history
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        _asset_history.append({
            "time": now_str,
            "totalAsset": account_summary["totalEvalAmount"]  # 총평가금액 (예수금 + 주식평가)
        })
        # 최근 100개만 유지
        if len(_asset_history) > 100:
            _asset_history = _asset_history[-100:]
        
        return jsonify({
            "success": True,
            "holdings": holdings,
            "summary": account_summary,
            "assetHistory": _asset_history
        })
    except Exception as e:
        print(f"계좌 잔고 조회 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/kis/order-available', methods=['GET'])
def api_kis_order_available():
    """KIS 매수가능금액 조회"""
    try:
        if not KIS_ACCOUNT_NO:
            return jsonify({"error": "KIS_ACCOUNT_NO 환경변수가 설정되지 않았습니다."}), 400
        
        code = request.args.get('code', '005930')  # 기본: 삼성전자
        price = request.args.get('price', '0')
        
        account_parts = KIS_ACCOUNT_NO.split("-")
        cano = account_parts[0]
        acnt_prdt_cd = account_parts[1]
        
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": str(code).zfill(6),  # 종목코드
            "ORD_UNPR": str(price),  # 주문단가 (시장가=0)
            "ORD_DVSN": "01",  # 주문구분 (01: 시장가)
            "CMA_EVLU_AMT_ICLD_YN": "Y",  # CMA평가금액포함여부
            "OVRS_ICLD_YN": "N"  # 해외포함여부
        }
        
        result = call_kis_trading_api(
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            params=params,
            tr_id="TTTC8908R",
            use_mock=True
        )
        
        if "error" in result:
            return jsonify(result), 500
        
        output = result.get("output", {})
        
        return jsonify({
            "success": True,
            "orderAvailable": {
                "availableCash": int(output.get("ord_psbl_cash", 0) or 0),  # 주문가능현금
                "maxQuantity": int(output.get("max_buy_qty", 0) or 0),  # 최대매수가능수량
                "availableAmount": int(output.get("nrcvb_buy_amt", 0) or 0),  # 미수없는매수금액
            }
        })
    except Exception as e:
        print(f"매수가능금액 조회 오류: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/kis/order', methods=['POST'])
def api_kis_order():
    """KIS 주식 주문 (시장가 매수/매도)"""
    try:
        if not KIS_ACCOUNT_NO:
            return jsonify({"error": "KIS_ACCOUNT_NO 환경변수가 설정되지 않았습니다."}), 400
        
        data = request.get_json() or {}
        code = str(data.get('code', '')).zfill(6)
        quantity = int(data.get('quantity', 0))
        order_type = data.get('orderType', 'buy')  # 'buy' or 'sell'
        
        if not code or quantity <= 0:
            return jsonify({"error": "종목코드와 수량이 필요합니다."}), 400
        
        account_parts = KIS_ACCOUNT_NO.split("-")
        cano = account_parts[0]
        acnt_prdt_cd = account_parts[1]
        
        # 주문 요청 바디
        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": code,  # 종목코드
            "ORD_DVSN": "01",  # 01: 시장가
            "ORD_QTY": str(quantity),  # 주문수량
            "ORD_UNPR": "0",  # 시장가는 0
        }
        
        # TR_ID: TTTC0802U(매수), TTTC0801U(매도)
        tr_id = "TTTC0802U" if order_type == "buy" else "TTTC0801U"
        
        result = call_kis_trading_api(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=tr_id,
            method="POST",
            body=body,
            use_mock=True
        )
        
        if "error" in result:
            return jsonify(result), 500
        
        output = result.get("output", {})
        
        return jsonify({
            "success": True,
            "order": {
                "orderNo": output.get("ODNO", ""),  # 주문번호
                "orderTime": output.get("ORD_TMD", ""),  # 주문시각
                "code": code,
                "quantity": quantity,
                "orderType": order_type
            },
            "message": f"{'매수' if order_type == 'buy' else '매도'} 주문이 접수되었습니다."
        })
    except Exception as e:
        print(f"주문 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/kis/batch-order', methods=['POST'])
def api_kis_batch_order():
    """KIS 일괄 주문 (여러 종목 시장가 매수/매도)"""
    try:
        if not KIS_ACCOUNT_NO:
            return jsonify({"error": "KIS_ACCOUNT_NO 환경변수가 설정되지 않았습니다."}), 400
        
        data = request.get_json() or {}
        orders = data.get('orders', [])  # [{code, quantity, orderType}]
        
        if not orders:
            return jsonify({"error": "주문 목록이 비어있습니다."}), 400
        
        results = []
        for order in orders:
            code = str(order.get('code', '')).zfill(6)
            quantity = int(order.get('quantity', 0))
            order_type = order.get('orderType', 'buy')
            
            if not code or quantity <= 0:
                results.append({
                    "code": code,
                    "success": False,
                    "error": "잘못된 종목코드 또는 수량"
                })
                continue
            
            account_parts = KIS_ACCOUNT_NO.split("-")
            cano = account_parts[0]
            acnt_prdt_cd = account_parts[1]
            
            body = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": "01",
                "ORD_QTY": str(quantity),
                "ORD_UNPR": "0",
            }
            
            tr_id = "TTTC0802U" if order_type == "buy" else "TTTC0801U"
            
            result = call_kis_trading_api(
                "/uapi/domestic-stock/v1/trading/order-cash",
                tr_id=tr_id,
                method="POST",
                body=body,
                use_mock=True
            )
            
            if "error" in result:
                results.append({
                    "code": code,
                    "success": False,
                    "error": result.get("error", "Unknown error")
                })
            else:
                output = result.get("output", {})
                results.append({
                    "code": code,
                    "success": True,
                    "orderNo": output.get("ODNO", ""),
                    "orderType": order_type,
                    "quantity": quantity
                })
            
            # KIS API rate limit 방지
            time.sleep(0.3)
        
        success_count = sum(1 for r in results if r.get("success"))
        
        return jsonify({
            "success": True,
            "results": results,
            "summary": {
                "total": len(orders),
                "success": success_count,
                "failed": len(orders) - success_count
            }
        })
    except Exception as e:
        print(f"일괄 주문 오류: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/kis/calculate-order', methods=['POST'])
def api_kis_calculate_order():
    """매수 수량 계산 (총자산 대비 비율 기반)"""
    try:
        data = request.get_json() or {}
        code = str(data.get('code', '')).zfill(6)
        ratio = float(data.get('ratio', 0))  # 총자산 대비 비율 (%)
        total_asset = float(data.get('totalAsset', 0))  # 총자산
        
        if ratio <= 0 or total_asset <= 0:
            return jsonify({"error": "비율과 총자산이 필요합니다."}), 400
        
        # 현재가 조회
        kis_price = get_kis_realtime_price(code)
        current_price = kis_price.get('currentPrice', 0)
        
        if current_price <= 0:
            return jsonify({"error": "현재가를 조회할 수 없습니다."}), 400
        
        # 매수금액 계산
        buy_amount = total_asset * (ratio / 100)
        # 매수 가능 수량 계산
        quantity = int(buy_amount / current_price)
        
        return jsonify({
            "success": True,
            "code": code,
            "currentPrice": current_price,
            "ratio": ratio,
            "buyAmount": buy_amount,
            "quantity": quantity
        })
    except Exception as e:
        print(f"매수 수량 계산 오류: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/kis/calculate-sell', methods=['POST'])
def api_kis_calculate_sell():
    """매도 수량 계산 (보유수량 대비 비율 기반)"""
    try:
        data = request.get_json() or {}
        code = str(data.get('code', '')).zfill(6)
        ratio = float(data.get('ratio', 0))  # 보유수량 대비 비율 (%)
        holding_quantity = int(data.get('holdingQuantity', 0))  # 보유수량
        
        if ratio <= 0 or holding_quantity <= 0:
            return jsonify({"error": "비율과 보유수량이 필요합니다."}), 400
        
        # 매도 수량 계산
        sell_quantity = int(holding_quantity * (ratio / 100))
        
        if sell_quantity <= 0:
            sell_quantity = 1  # 최소 1주
        
        return jsonify({
            "success": True,
            "code": code,
            "ratio": ratio,
            "holdingQuantity": holding_quantity,
            "sellQuantity": sell_quantity
        })
    except Exception as e:
        print(f"매도 수량 계산 오류: {e}")
        return jsonify({"error": str(e)}), 500


# =============================
# 자동매매 전략 API
# =============================
from auto_trading_strategy1 import get_auto_trading_engine, StrategyConfig, set_auto_trading_mode, get_auto_trading_mode, is_trading_day

@app.route('/api/auto-trading/mode', methods=['GET'])
def api_auto_trading_mode_get():
    """자동매매 모드 조회"""
    try:
        mode_info = get_auto_trading_mode()
        return jsonify({"success": True, **mode_info})
    except Exception as e:
        print(f"자동매매 모드 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/mode', methods=['POST'])
def api_auto_trading_mode_set():
    """자동매매 모드 전환"""
    try:
        data = request.get_json() or {}
        mode = data.get('mode', 'mock')
        result = set_auto_trading_mode(mode)
        return jsonify(result)
    except Exception as e:
        print(f"자동매매 모드 전환 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/is-trading-day', methods=['GET'])
def api_auto_trading_is_trading_day():
    """오늘이 거래일인지 확인"""
    try:
        from datetime import date
        today = date.today()
        is_trading = is_trading_day(today)
        return jsonify({
            "success": True,
            "date": today.strftime('%Y-%m-%d'),
            "is_trading_day": is_trading,
            "weekday": today.strftime('%A')
        })
    except Exception as e:
        print(f"거래일 확인 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/status', methods=['GET'])
def api_auto_trading_status():
    """자동매매 상태 조회"""
    try:
        engine = get_auto_trading_engine()
        status = engine.get_status()
        mode_info = get_auto_trading_mode()
        # 오늘 거래일 여부 추가 (date 객체로 전달)
        today = datetime.now().date()
        trading_day = is_trading_day(today)
        return jsonify({"success": True, "isTradingDay": trading_day, **status, **mode_info})
    except Exception as e:
        print(f"자동매매 상태 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/start', methods=['POST'])
def api_auto_trading_start():
    """자동매매 시작"""
    try:
        engine = get_auto_trading_engine()
        result = engine.start()
        return jsonify(result)
    except Exception as e:
        print(f"자동매매 시작 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/stop', methods=['POST'])
def api_auto_trading_stop():
    """자동매매 중지"""
    try:
        engine = get_auto_trading_engine()
        result = engine.stop()
        return jsonify(result)
    except Exception as e:
        print(f"자동매매 중지 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/manual-buy', methods=['POST'])
def api_auto_trading_manual_buy():
    """수동 매수 (quantity=0 또는 미지정 시 1/N 비율로 자동 계산)"""
    try:
        data = request.get_json() or {}
        code = str(data.get('code', '')).zfill(6)
        quantity = int(data.get('quantity', 0))  # 0이면 자동 계산
        use_auto_quantity = data.get('auto_quantity', False) or quantity == 0
        
        if not code:
            return jsonify({"success": False, "error": "종목코드가 필요합니다."}), 400
        
        engine = get_auto_trading_engine()
        result = engine.manual_buy(code, quantity, auto_quantity=use_auto_quantity)
        
        if 'error' in result:
            return jsonify({"success": False, **result})
        return jsonify({"success": True, **result})
    except Exception as e:
        print(f"수동 매수 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/manual-sell', methods=['POST'])
def api_auto_trading_manual_sell():
    """수동 매도"""
    try:
        data = request.get_json() or {}
        code = str(data.get('code', '')).zfill(6)
        quantity = int(data.get('quantity', 0))  # 0이면 전량
        
        if not code:
            return jsonify({"success": False, "error": "종목코드가 필요합니다."}), 400
        
        engine = get_auto_trading_engine()
        result = engine.manual_sell(code, quantity)
        
        if 'error' in result:
            return jsonify({"success": False, **result})
        return jsonify({"success": True, **result})
    except Exception as e:
        print(f"수동 매도 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/refresh-positions', methods=['POST'])
def api_auto_trading_refresh_positions():
    """포지션 동기화 (계좌 잔고 기준)"""
    try:
        engine = get_auto_trading_engine()
        result = engine.refresh_positions()
        
        if 'error' in result:
            return jsonify({"success": False, **result})
        return jsonify({"success": True, **result})
    except Exception as e:
        print(f"포지션 동기화 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/build-universe', methods=['POST'])
def api_auto_trading_build_universe():
    """유니버스 수동 구축"""
    try:
        engine = get_auto_trading_engine()
        universe = engine.build_universe()
        
        # 상태에 저장
        engine.state.universe = universe
        
        # 포지션 초기화
        for stock in universe:
            if stock.code not in engine.state.positions:
                from auto_trading_strategy1 import Position, PositionState
                engine.state.positions[stock.code] = Position(
                    code=stock.code,
                    name=stock.name,
                    state=PositionState.WATCHING,
                    prev_close=stock.prev_close
                )
        
        engine._save_state()
        
        return jsonify({
            "success": True,
            "count": len(universe),
            "universe": [
                {
                    "code": s.code,
                    "name": s.name,
                    "prev_close": s.prev_close,
                    "change_rate": s.change_rate,
                    "market_cap": s.market_cap
                } for s in universe
            ]
        })
    except Exception as e:
        print(f"유니버스 구축 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/trade-history', methods=['GET'])
def api_auto_trading_trade_history():
    """거래 내역 조회"""
    try:
        days = int(request.args.get('days', 7))
        engine = get_auto_trading_engine()
        history = engine.get_trade_history(days)
        
        return jsonify({
            "success": True,
            "history": history
        })
    except Exception as e:
        print(f"거래 내역 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/config', methods=['GET'])
def api_auto_trading_config():
    """전략 설정 조회"""
    try:
        engine = get_auto_trading_engine()
        config = engine.config
        return jsonify({
            "success": True,
            "config": {
                "upper_limit_rate": config.UPPER_LIMIT_RATE,
                "min_market_cap": config.MIN_MARKET_CAP,
                "gap_threshold": config.GAP_THRESHOLD,
                "gap_confirm_count": config.GAP_CONFIRM_COUNT,
                "entry_start_time": config.ENTRY_START_TIME,
                "entry_end_time": config.ENTRY_END_TIME,
                "take_profit_rate": config.TAKE_PROFIT_RATE,
                "stop_loss_rate": config.STOP_LOSS_RATE,
                "eod_sell_start": config.EOD_SELL_START,
                "eod_sell_end": config.EOD_SELL_END,
                "max_daily_loss_rate": config.MAX_DAILY_LOSS_RATE,
                "max_positions": config.MAX_POSITIONS
            }
        })
    except Exception as e:
        print(f"전략 설정 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/config', methods=['POST'])
def api_auto_trading_update_config():
    """전략 설정 변경"""
    try:
        data = request.get_json() or {}
        engine = get_auto_trading_engine()
        
        # 설정 가능한 파라미터들 업데이트
        if 'max_positions' in data:
            engine.config.MAX_POSITIONS = int(data['max_positions'])
        if 'take_profit_rate' in data:
            engine.config.TAKE_PROFIT_RATE = float(data['take_profit_rate'])
        if 'stop_loss_rate' in data:
            engine.config.STOP_LOSS_RATE = float(data['stop_loss_rate'])
        if 'gap_threshold' in data:
            engine.config.GAP_THRESHOLD = float(data['gap_threshold'])
        if 'min_market_cap' in data:
            engine.config.MIN_MARKET_CAP = float(data['min_market_cap'])
        if 'entry_start_time' in data:
            engine.config.ENTRY_START_TIME = str(data['entry_start_time'])
        if 'entry_end_time' in data:
            engine.config.ENTRY_END_TIME = str(data['entry_end_time'])
            
        return jsonify({
            "success": True,
            "message": "설정이 업데이트되었습니다.",
            "config": {
                "max_positions": engine.config.MAX_POSITIONS,
                "take_profit_rate": engine.config.TAKE_PROFIT_RATE,
                "stop_loss_rate": engine.config.STOP_LOSS_RATE,
                "gap_threshold": engine.config.GAP_THRESHOLD,
                "min_market_cap": engine.config.MIN_MARKET_CAP
            }
        })
    except Exception as e:
        print(f"전략 설정 변경 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/logs', methods=['GET'])
def api_auto_trading_logs():
    """자동매매 로그 조회"""
    try:
        limit = int(request.args.get('limit', 100))
        engine = get_auto_trading_engine()
        
        logs = engine.state.logs[-limit:]
        
        return jsonify({
            "success": True,
            "logs": logs
        })
    except Exception as e:
        print(f"로그 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/settings', methods=['GET'])
def api_auto_trading_settings_get():
    """자동매매 설정 조회 (서버 저장)"""
    try:
        settings = {}
        rows = AutoTradingSettings.query.all()
        for row in rows:
            try:
                settings[row.key] = json.loads(row.value)
            except:
                settings[row.key] = row.value
        
        # 기본값 설정
        defaults = {
            'auto_start_enabled': False,
            'auto_start_mode': 'manual'  # 'auto' | 'manual'
        }
        for key, default_val in defaults.items():
            if key not in settings:
                settings[key] = default_val
        
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        print(f"자동매매 설정 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/settings', methods=['POST'])
def api_auto_trading_settings_set():
    """자동매매 설정 저장 (서버 저장)"""
    try:
        data = request.get_json() or {}
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for key, value in data.items():
            existing = AutoTradingSettings.query.filter_by(key=key).first()
            value_str = json.dumps(value) if not isinstance(value, str) else value
            
            if existing:
                existing.value = value_str
                existing.updated_at = now_ts
            else:
                new_setting = AutoTradingSettings(
                    key=key,
                    value=value_str,
                    updated_at=now_ts
                )
                db.session.add(new_setting)
        
        db.session.commit()
        return jsonify({"success": True, "message": "설정이 저장되었습니다."})
    except Exception as e:
        print(f"자동매매 설정 저장 오류: {e}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auto-trading/heartbeat', methods=['GET'])
def api_auto_trading_heartbeat():
    """엔진 실행 상태를 정확히 확인 (heartbeat 기반)"""
    try:
        engine = get_auto_trading_engine()
        
        # 엔진이 실행 중인지 확인
        is_actually_running = engine._running and engine._thread is not None and engine._thread.is_alive()
        
        # 마지막 업데이트 시간 확인 (10초 이상 지나면 죽은 것으로 간주)
        last_update = engine.state.last_update
        is_responsive = False
        if last_update and is_actually_running:
            try:
                last_dt = datetime.fromisoformat(last_update)
                diff_seconds = (datetime.now() - last_dt).total_seconds()
                is_responsive = diff_seconds < 10
            except:
                pass
        
        return jsonify({
            "success": True,
            "is_running": is_actually_running,
            "is_responsive": is_responsive,
            "last_update": last_update,
            "phase": engine.state.phase.value if engine.state.phase else 'IDLE',
            "thread_alive": engine._thread.is_alive() if engine._thread else False
        })
    except Exception as e:
        print(f"Heartbeat 확인 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# Serve frontend index.html for SPA routing
@app.route('/')
def serve_index():
    if app.static_folder and os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return app.send_static_file('index.html')
    return jsonify({"message": "MyStocks API Server", "status": "running"}), 200


# Catch-all route for SPA
@app.errorhandler(404)
def not_found(e):
    if app.static_folder and os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return app.send_static_file('index.html')
    return jsonify({"error": "Not found"}), 404


if __name__ == '__main__':
    # 데이터베이스 초기화
    init_db()
    
    # KIS API 테스트
    print("=== KIS API 테스트 시작 ===")
    test_code = "005930"  # 삼성전자
    print(f"테스트 종목: {test_code}")
    
    try:
        result = get_kis_stock_info(test_code)
        print(f"결과: {result}")
    except Exception as e:
        print(f"KIS API 테스트 실패: {e}")
    
    # 스케줄러 스레드 시작
    start_scheduler_thread()
    
    print("=== Flask 서버 시작 ===")
    # Get host and port from environment variables for Docker compatibility
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') != 'production'
    app.run(debug=debug, host=host, port=port, use_reloader=False)  # use_reloader=False to prevent double thread start