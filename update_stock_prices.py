import pandas as pd
from pykrx import stock
from datetime import datetime, timedelta
import json
import requests
import time
import sys
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
from pathlib import Path

try:
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover
    pq = None

app = Flask(__name__)
CORS(app)  # 모든 도메인에서 접근 허용

# SQLite 데이터베이스 설정
import os
db_path = os.path.join(os.path.dirname(__file__), 'mystock.db')
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
        print("데이터베이스 초기화 완료")

# 한국투자증권 API 설정
APP_KEY = "PSM786MPoVa3UpQ0R51JEqEEGuldiY4JBvbs"
APP_SECRET = "6KPMpHh44nSTfvjYke2cyFz9Fiizmf5ip3Ih9QbYy7n29lpFIOgSai1V2YclrxJWU/RD9EyB24QCaweWQJMPelWrPd15fp399Fpk1ouzDWYDlbTijKMh90ALITQ+VLClrs6gVaGOpJWJ0lDlz/UR0CYc0KsqBPPhd4uoUCFJug1SRydO7KA="
ACCESS_TOKEN = None
TOKEN_FILE = "kis_token.json"

# 한국투자증권 API 설정
APP_KEY = "PSM786MPoVa3UpQ0R51JEqEEGuldiY4JBvbs"
APP_SECRET = "6KPMpHh44nSTfvjYke2cyFz9Fiizmf5ip3Ih9QbYy7n29lpFIOgSai1V2YclrxJWU/RD9EyB24QCaweWQJMPelWrPd15fp399Fpk1ouzDWYDlbTijKMh90ALITQ+VLClrs6gVaGOpJWJ0lDlz/UR0CYc0KsqBPPhd4uoUCFJug1SRydO7KA="
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

@app.route('/api/groups', methods=['GET'])
def get_groups():
    """모든 그룹과 주식 데이터 조회"""
    try:
        groups = Group.query.all()

        # Preload local+json data once per request (fast path)
        business_day = get_recent_business_day()
        fundamentals = load_fundamentals_json()
        tickers = load_local_tickers()

        all_codes = []
        for g in groups:
            for s in g.stocks:
                if s.symbol:
                    all_codes.append(str(s.symbol).zfill(6))

        local_bars_map = get_local_bars_for_codes(business_day, all_codes) if all_codes else {}

        result = []
        
        for group in groups:
            stocks = []
            for stock in group.stocks:
                code = str(stock.symbol).zfill(6)
                merged = merged_stock_info(code, business_day, fundamentals, local_bars_map, tickers)
                
                # KIS 실시간 데이터로 업데이트 (PER, PBR, EPS, 현재가, 외인비율 등)
                kis_realtime = get_kis_realtime_price(code)
                if kis_realtime:
                    # KIS 데이터가 있으면 병합 (KIS가 우선)
                    # Use key presence (not truthiness) so zero values are preserved
                    for key in ['currentPrice', 'per', 'pbr', 'eps', 'volume', 'marketCap', 'foreignOwnership', 'change', 'changePercent', 'high', 'low', 'open']:
                        if key in kis_realtime and kis_realtime.get(key) is not None:
                            merged[key] = kis_realtime[key]
                
                memos = [{'id': m.id, 'content': m.content, 'created_at': m.created_at} for m in stock.memos]

                # UI(StockData) shape: keep values stable across reloads
                current_price = merged.get('currentPrice', stock.price) or 0
                volume = merged.get('volume', stock.volume) or 0
                market_cap = merged.get('marketCap', stock.market_cap) or 0

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

                stocks.append({
                    'id': stock.id,
                    'symbol': code,
                    'name': merged.get('name') or stock.name,
                    'currentPrice': float(current_price),
                    'per': float(merged.get('per', stock.per) or 0),
                    'pbr': float(merged.get('pbr', stock.pbr) or 0),
                    'eps': float(merged.get('eps', stock.eps) or 0),
                    'floatingShares': str(merged.get('floatingShares', '0')),
                    'majorShareholderStake': major_stake,
                    'marketCap': str(market_cap),
                    'tradingVolume': str(volume),
                    'transactionAmount': str(merged.get('transactionAmount', merged.get('value', '0')) or '0'),
                    'foreignOwnership': float(merged.get('foreignOwnership', 0) or 0),
                    'quarterlyMargins': q_margins,
                    'memos': [{'id': m['id'], 'date': m['created_at'], 'content': m['content']} for m in memos],
                    'addedAt': stock.added_at,

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
        
        return jsonify(result)
    except Exception as e:
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
    """그룹 전체의 수익률 계산"""
    try:
        group = Group.query.get(group_id)
        if not group:
            return jsonify({"error": "그룹을 찾을 수 없습니다"}), 404
        
        stocks_returns = []
        total_invested = 0
        total_current_value = 0
        total_realized = 0
        total_unrealized = 0
        
        for stock in group.stocks:
            trades = Trade.query.filter_by(stock_id=stock.id).all()
            
            buy_qty = sum(t.quantity for t in trades if t.trade_type == 'buy')
            buy_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'buy')
            sell_qty = sum(t.quantity for t in trades if t.trade_type == 'sell')
            sell_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'sell')
            
            remaining = buy_qty - sell_qty
            avg_price = buy_amt / buy_qty if buy_qty > 0 else 0
            
            code = str(stock.symbol).zfill(6)
            kis_data = get_kis_realtime_price(code)
            current_price = kis_data.get('currentPrice', stock.price) or 0
            
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
    """포트폴리오 수익률 히스토리 조회 (캐싱 + 신규 날짜만 계산)"""
    try:
        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "그룹을 찾을 수 없습니다"}), 404
        
        # 그룹 생성일 파싱
        group_date = group.date[:10] if group.date else None
        if not group_date:
            return jsonify({"error": "그룹 생성일을 찾을 수 없습니다"}), 400
        
        # 그룹 내 종목들의 심볼 수집
        stock_codes = [str(s.symbol).zfill(6) for s in group.stocks]
        if not stock_codes:
            return jsonify({"history": [], "message": "종목이 없습니다"})
        
        # 기존 캐시된 히스토리 조회
        existing_history = PortfolioHistory.query.filter_by(group_id=group_id).order_by(PortfolioHistory.date).all()
        cached_dates = {h.date for h in existing_history}
        
        # 각 종목별 매수 정보 계산 (그룹 생성일 기준)
        stock_trades = {}
        for stock in group.stocks:
            trades = Trade.query.filter_by(stock_id=stock.id).all()
            buy_qty = sum(t.quantity for t in trades if t.trade_type == 'buy')
            buy_amt = sum(t.quantity * t.price for t in trades if t.trade_type == 'buy')
            sell_qty = sum(t.quantity for t in trades if t.trade_type == 'sell')
            
            remaining = buy_qty - sell_qty
            avg_price = buy_amt / buy_qty if buy_qty > 0 else 0
            
            if remaining > 0:
                code = str(stock.symbol).zfill(6)
                stock_trades[code] = {
                    'remaining': remaining,
                    'avg_price': avg_price,
                    'invested': remaining * avg_price
                }
        
        if not stock_trades:
            return jsonify({"history": [{"date": h.date, "returnRate": h.return_rate, "totalValue": h.total_value, "totalInvested": h.total_invested} for h in existing_history]})
        
        # 사용 가능한 날짜 목록 가져오기 (parquet 디렉토리)
        bars_dir = Path("data/krx/bars")
        available_dates = []
        if bars_dir.exists():
            for d in bars_dir.iterdir():
                if d.is_dir() and d.name.startswith("date="):
                    date_str = d.name.replace("date=", "")
                    if date_str >= group_date:
                        available_dates.append(date_str)
        available_dates.sort()
        
        # 새로 계산해야 할 날짜들
        new_dates = [d for d in available_dates if d not in cached_dates]
        
        # 새 날짜들에 대해 수익률 계산
        for date_str in new_dates:
            date_dir = bars_dir / f"date={date_str}"
            parquet_file = date_dir / "data.parquet"
            
            if not parquet_file.exists():
                continue
            
            try:
                pf = ParquetFile(str(parquet_file))
                df = pf.to_pandas()
                
                # 종목코드 정규화
                if 'code' in df.columns:
                    df['code'] = df['code'].astype(str).str.zfill(6)
                
                total_invested = 0
                total_value = 0
                
                for code, info in stock_trades.items():
                    if 'code' in df.columns:
                        row = df[df['code'] == code]
                        if not row.empty:
                            close_price = row.iloc[0].get('close', 0)
                            total_value += info['remaining'] * close_price
                            total_invested += info['invested']
                
                if total_invested > 0:
                    return_rate = ((total_value - total_invested) / total_invested) * 100
                    
                    # 히스토리 저장
                    history_entry = PortfolioHistory(
                        group_id=group_id,
                        date=date_str,
                        total_invested=total_invested,
                        total_value=total_value,
                        return_rate=return_rate,
                        created_at=datetime.now().isoformat()
                    )
                    db.session.add(history_entry)
                    
            except Exception as e:
                print(f"날짜 {date_str} 처리 오류: {e}")
                continue
        
        db.session.commit()
        
        # 전체 히스토리 반환
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
    
    print("=== Flask 서버 시작 ===")
    app.run(debug=True, port=5000)