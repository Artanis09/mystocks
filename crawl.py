# -*- coding: utf-8 -*-
"""
KRX 전 종목 일봉 데이터 수집 프레임워크 (Parquet 날짜 파티션 + tqdm + 3년+버퍼 유지)
- 저장: data/krx/bars/date=YYYY-MM-DD/part-0000.parquet
- 진행바: tqdm (누락 영업일 기준)
- 기간: 최근 3년 + 버퍼(기본 180일) 유지, 그 이전 파티션 자동 삭제
- 재실행: 파티션 존재 여부 확인 후 누락 영업일만 증분 수집
- 마스터: tickers.parquet 저장 (code, name, market)

[안전 패치]
- pykrx의 get_previous_business_days 반환 타입이 환경에 따라 str/datetime/Timestamp 혼재 가능
- business_days()에서 즉시 pd.Timestamp로 정규화하여 downstream에서 타입 오류 방지

Requirements:
  pip install pykrx pandas pyarrow tqdm
"""

from __future__ import annotations

import os
import re
import time
import shutil
import json
import configparser
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Set, Optional, Iterable, Dict, Any

import pandas as pd
from tqdm import tqdm
# pykrx 대신 KIS/fdr 활용 (safe import)
try:
    import FinanceDataReader as fdr
except ImportError:
    fdr = None

# from pykrx import stock  # 더 이상 사용하지 않음


# -----------------------------
# 설정
# -----------------------------
@dataclass(frozen=True)
class Config:
    # 저장 경로
    root_dir: str = "data/krx"
    tickers_path: str = "data/krx/master/tickers.parquet"
    bars_dir: str = "data/krx/bars"
    financials_dir: str = "data/krx/financials"
    config_file: str = "config.ini"

    # 보관 기간(캘린더 기준): 최근 30년 + 버퍼
    years: int = 30
    buffer_days: int = 180

    # 호출 안정성
    sleep_sec: float = 0.05  # KIS API 속도 제한 대응 (20 req/s -> 0.05s)
    max_retries: int = 3
    retry_backoff_sec: float = 0.7

    # KIS API 설정
    kis_app_key: str = "PSM786MPoVa3UpQ0R51JEqEEGuldiY4JBvbs"
    kis_app_secret: str = "6KPMpHh44nSTfvjYke2cyFz9Fiizmf5ip3Ih9QbYy7n29lpFIOgSai1V2YclrxJWU/RD9EyB24QCaweWQJMPelWrPd15fp399Fpk1ouzDWYDlbTijKMh90ALITQ+VLClrs6gVaGOpJWJ0lDlz/UR0CYc0KsqBPPhd4uoUCFJug1SRydO7KA="
    kis_token_file: str = "kis_token.json"
    kis_base_url: str = "https://openapi.koreainvestment.com:9443"

    # 로그/표시
    show_every_n: int = 10
    
    # DART API
    dart_api_url: str = "https://opendart.fss.or.kr/api"


CFG = Config()

# -----------------------------
# KIS API 유틸
# -----------------------------
_KIS_ACCESS_TOKEN = None

def get_kis_access_token() -> Optional[str]:
    global _KIS_ACCESS_TOKEN
    
    if _KIS_ACCESS_TOKEN:
        return _KIS_ACCESS_TOKEN
    
    # 파일에서 로드
    if os.path.exists(CFG.kis_token_file):
        try:
            with open(CFG.kis_token_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                expired = data.get('expired_time', 0)
                if time.time() < (expired - 600):  # 10분 전
                    _KIS_ACCESS_TOKEN = data.get('access_token')
                    return _KIS_ACCESS_TOKEN
        except Exception:
            pass

    # 새 토큰 발급
    url = f"{CFG.kis_base_url}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": CFG.kis_app_key,
        "appsecret": CFG.kis_app_secret
    }
    try:
        res = requests.post(url, json=body, timeout=10)
        if res.status_code == 200:
            data = res.json()
            _KIS_ACCESS_TOKEN = data.get("access_token")
            expires_in = data.get("expires_in", 86400)
            with open(CFG.kis_token_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "access_token": _KIS_ACCESS_TOKEN,
                    "expired_time": time.time() + expires_in,
                    "issued_time": time.time()
                }, f)
            return _KIS_ACCESS_TOKEN
    except Exception as e:
        print(f"[ERROR] KIS 토큰 발급 실패: {e}")
    return None

def call_kis_api(endpoint: str, params: dict, tr_id: str) -> dict:
    token = get_kis_access_token()
    if not token:
        return {}
    
    url = f"{CFG.kis_base_url}{endpoint}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": CFG.kis_app_key,
        "appsecret": CFG.kis_app_secret,
        "tr_id": tr_id,
        "custtype": "P"
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {}


# -----------------------------
# 유틸
# -----------------------------
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def get_latest_business_day() -> str:
    today_dt = datetime.now()
    # Simple business day calculation: if weekend, go to Friday
    weekday = today_dt.weekday()  # 0=Mon, 6=Sun
    if weekday == 5:  # Sat
        latest_dt = today_dt - timedelta(days=1)
    elif weekday == 6:  # Sun
        latest_dt = today_dt - timedelta(days=2)
    else:
        latest_dt = today_dt
    return yyyymmdd(latest_dt)


def compute_window_start(end_yyyymmdd: str, years: int, buffer_days: int) -> str:
    end_dt = datetime.strptime(end_yyyymmdd, "%Y%m%d")
    start_dt = end_dt - timedelta(days=years * 365 + buffer_days)
    return yyyymmdd(start_dt)


def list_existing_partitions_dates(bars_dir: str) -> Set[str]:
    """
    bars_dir 아래 date=YYYY-MM-DD 파티션명을 스캔하여 존재하는 날짜(YYYY-MM-DD) 집합 반환
    """
    if not os.path.exists(bars_dir):
        return set()

    dates: Set[str] = set()
    pat = re.compile(r"^date=(\d{4}-\d{2}-\d{2})$")
    for name in os.listdir(bars_dir):
        m = pat.match(name)
        if m:
            dates.add(m.group(1))
    return dates


def business_days(start_yyyymmdd: str, end_yyyymmdd: str) -> List[pd.Timestamp]:
    """
    start~end 사이 영업일을 pd.Timestamp 리스트로 반환
    KIS 삼성전자 데이터를 활용하여 공휴일이 반영된 영업일 추출
    """
    try:
        # 삼성전자 일자별 시세 활용 (최근 30개 영업일)
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": "005930",
            "fid_org_adj_prc": "1",
            "fid_period_div_code": "D"
        }
        res = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-daily-price", params, "FHKST01010400")
        output = res.get("output", [])
        
        dates = []
        for day in output:
            d_str = day.get("stck_bsop_date")
            if not d_str: continue
            if start_yyyymmdd <= d_str <= end_yyyymmdd:
                dates.append(pd.to_datetime(d_str).normalize())
        
        if dates:
            dates.sort()
            return dates
            
        # 범위가 30일을 벗어나는 경우 FinanceDataReaderFallback
        import FinanceDataReader as fdr
        df = fdr.DataReader('005930', start_yyyymmdd, end_yyyymmdd)
        if not df.empty:
            return [pd.Timestamp(d).normalize() for d in df.index]
            
    except Exception as e:
        print(f"[WARN] 영업일 목록 조회 실패: {e}")
        
    # 최종 fallback: 단순 주말 제외
    start_dt = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end_dt = datetime.strptime(end_yyyymmdd, "%Y%m%d")
    days = []
    current = start_dt
    while current <= end_dt:
        if current.weekday() < 5:
            days.append(pd.Timestamp(current).normalize())
        current += timedelta(days=1)
    return days


def prune_old_partitions(bars_dir: str, keep_days: int) -> int:
    """
    keep_days(캘린더)보다 오래된 date=YYYY-MM-DD 파티션 삭제
    반환: 삭제한 파티션 수
    """
    if not os.path.exists(bars_dir):
        return 0

    cutoff = (datetime.now().date() - timedelta(days=keep_days))
    deleted = 0

    for name in os.listdir(bars_dir):
        if not name.startswith("date="):
            continue
        date_str = name.replace("date=", "")
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        if d < cutoff:
            shutil.rmtree(os.path.join(bars_dir, name), ignore_errors=True)
            deleted += 1

    return deleted


# -----------------------------
# DART API 관련
# -----------------------------
def load_dart_api_key() -> Optional[str]:
    """
    config.ini에서 DART API 키 로드
    """
    if not os.path.exists(CFG.config_file):
        print(f"[WARN] config.ini 파일이 없습니다. DART API 기능을 사용하려면 config.ini를 생성하세요.")
        return None
    
    config = configparser.ConfigParser()
    config.read(CFG.config_file, encoding='utf-8')
    
    if 'DART' not in config or 'api_key' not in config['DART']:
        print(f"[WARN] config.ini에 DART API 키가 설정되지 않았습니다.")
        return None
    
    api_key = config['DART']['api_key'].strip()
    if not api_key:
        print(f"[WARN] DART API 키가 비어있습니다. https://opendart.fss.or.kr/ 에서 발급받으세요.")
        return None
    
    return api_key


def get_corp_code_mapping(api_key: str) -> Dict[str, str]:
    """
    DART 고유번호(corp_code)와 종목코드(stock_code) 매핑 가져오기
    반환: {stock_code: corp_code}
    """
    url = f"{CFG.dart_api_url}/corpCode.xml"
    params = {"crtfc_key": api_key}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            print(f"[ERROR] DART 기업코드 조회 실패: {response.status_code}")
            return {}
        
        # XML 파싱 대신 간단한 방법으로 처리
        import zipfile
        import io
        import xml.etree.ElementTree as ET
        
        # ZIP 파일 압축 해제
        z = zipfile.ZipFile(io.BytesIO(response.content))
        xml_data = z.read('CORPCODE.xml')
        
        # XML 파싱
        root = ET.fromstring(xml_data)
        mapping = {}
        
        for corp in root.findall('list'):
            stock_code = corp.find('stock_code').text
            corp_code = corp.find('corp_code').text
            
            # 상장 기업만 (stock_code가 있는 경우)
            if stock_code and stock_code.strip():
                mapping[stock_code.strip().zfill(6)] = corp_code.strip()
        
        return mapping
    
    except Exception as e:
        print(f"[ERROR] DART 기업코드 매핑 생성 실패: {e}")
        return {}


def fetch_financial_statements(api_key: str, corp_code: str, year: str, quarter: str) -> Optional[Dict[str, Any]]:
    """
    특정 기업의 분기 재무제표 조회
    quarter: '11013' (1분기), '11012' (반기), '11014' (3분기), '11011' (사업보고서)
    """
    url = f"{CFG.dart_api_url}/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": quarter,
        "fs_div": "CFS"  # 연결재무제표 (OFS: 개별재무제표)
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            return None
        
        data = response.json()
        if data.get('status') != '000':
            return None
        
        return data
    
    except Exception:
        return None


def extract_financial_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    재무제표 데이터에서 주요 지표 추출
    - 영업이익률 = (영업이익 / 매출액) * 100
    """
    if not data or 'list' not in data:
        return {}
    
    metrics = {}
    items = data['list']
    
    # 필요한 항목 찾기
    for item in items:
        account_nm = item.get('account_nm', '')
        thstrm_amount = item.get('thstrm_amount', '0')  # 당기
        
        # 숫자가 아닌 경우 처리
        try:
            amount = float(thstrm_amount.replace(',', ''))
        except (ValueError, AttributeError):
            amount = 0.0
        
        # 매출액
        if '매출액' in account_nm and '영업' not in account_nm:
            metrics['revenue'] = amount
        
        # 영업이익
        if account_nm == '영업이익' or account_nm == '영업이익(손실)':
            metrics['operating_profit'] = amount
        
        # 당기순이익
        if '당기순이익' in account_nm and '지배' in account_nm:
            metrics['net_income'] = amount
    
    # 영업이익률 계산
    if 'revenue' in metrics and 'operating_profit' in metrics and metrics['revenue'] != 0:
        metrics['operating_margin'] = (metrics['operating_profit'] / metrics['revenue']) * 100
    
    return metrics


def fetch_major_shareholders(api_key: str, corp_code: str) -> Optional[float]:
    """
    대주주 지분율 조회 (최대주주 지분율)
    """
    url = f"{CFG.dart_api_url}/hyslrInfo.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            return None
        
        data = response.json()
        if data.get('status') != '000' or 'list' not in data:
            return None
        
        # 최대주주 지분율 추출
        items = data['list']
        if items and len(items) > 0:
            # 첫 번째 항목이 최대주주
            hold_stock_co = items[0].get('hold_stock_co', '0')
            total_stock_co = items[0].get('tot_stock_co', '0')
            
            try:
                hold = float(hold_stock_co.replace(',', ''))
                total = float(total_stock_co.replace(',', ''))
                
                if total > 0:
                    return (hold / total) * 100
            except (ValueError, AttributeError, ZeroDivisionError):
                pass
        
        return None
    
    except Exception:
        return None


def collect_financial_data_for_ticker(api_key: str, stock_code: str, corp_code: str, 
                                      years: List[str], quarters: List[str]) -> pd.DataFrame:
    """
    특정 종목의 여러 분기 재무 데이터 수집
    """
    results = []
    
    for year in years:
        for quarter_code, quarter_name in quarters:
            data = fetch_financial_statements(api_key, corp_code, year, quarter_code)
            
            if data:
                metrics = extract_financial_metrics(data)
                
                if metrics:
                    results.append({
                        'stock_code': stock_code,
                        'year': year,
                        'quarter': quarter_name,
                        'revenue': metrics.get('revenue', 0),
                        'operating_profit': metrics.get('operating_profit', 0),
                        'net_income': metrics.get('net_income', 0),
                        'operating_margin': metrics.get('operating_margin', 0)
                    })
            
            if CFG.sleep_sec > 0:
                time.sleep(CFG.sleep_sec)
    
    return pd.DataFrame(results)


def list_existing_financial_files(financials_dir: str) -> Set[str]:
    """
    이미 수집된 재무 데이터 파일 확인
    반환: {stock_code} 집합
    """
    if not os.path.exists(financials_dir):
        return set()
    
    existing = set()
    for filename in os.listdir(financials_dir):
        if filename.endswith('.parquet'):
            # 파일명 형식: {stock_code}_financials.parquet
            stock_code = filename.replace('_financials.parquet', '')
            existing.add(stock_code)
    
    return existing


def get_current_quarter() -> tuple:
    """
    현재 분기 정보 반환 (년도, 분기)
    """
    now = datetime.now()
    quarter = (now.month - 1) // 3 + 1
    return now.year, quarter


def get_last_financial_update() -> Optional[str]:
    """
    마지막 재무 데이터 업데이트 시점 확인
    """
    update_file = os.path.join(CFG.financials_dir, "_last_update.json")
    
    if not os.path.exists(update_file):
        return None
    
    try:
        with open(update_file, 'r') as f:
            data = json.load(f)
            return data.get("last_update_quarter")
    except Exception:
        return None


def save_financial_update_time():
    """
    재무 데이터 업데이트 시점 저장
    """
    ensure_dir(CFG.financials_dir)
    update_file = os.path.join(CFG.financials_dir, "_last_update.json")
    
    year, quarter = get_current_quarter()
    data = {
        "last_update_quarter": f"{year}Q{quarter}",
        "updated_at": datetime.now().isoformat()
    }
    
    with open(update_file, 'w') as f:
        json.dump(data, f)


def should_update_financials() -> bool:
    """
    재무 데이터 업데이트가 필요한지 확인 (분기당 1회)
    """
    last_update = get_last_financial_update()
    
    if last_update is None:
        return True
    
    year, quarter = get_current_quarter()
    current_quarter = f"{year}Q{quarter}"
    
    return last_update != current_quarter


def collect_financials_incremental(tickers_df: pd.DataFrame, financials_dir: str, 
                                   api_key: str, years_back: int = 2, 
                                   force_update: bool = False) -> None:
    """
    재무 데이터 증분 수집 (누락된 종목만)
    force_update: True면 분기 체크 없이 강제 수집
    """
    ensure_dir(financials_dir)
    
    # 기업코드 매핑
    print("[INFO] DART 기업코드 매핑 로드 중...")
    corp_mapping = get_corp_code_mapping(api_key)
    
    if not corp_mapping:
        print("[ERROR] DART 기업코드 매핑 실패")
        return
    
    print(f"[INFO] DART 기업코드 매핑 완료: {len(corp_mapping)} 개")
    
    # 이미 수집된 종목
    existing = list_existing_financial_files(financials_dir)
    
    # 수집 대상 종목 필터링
    tickers_to_fetch = []
    for _, row in tickers_df.iterrows():
        code = row['code']
        if code not in existing and code in corp_mapping:
            tickers_to_fetch.append((code, corp_mapping[code]))
    
    print(f"[INFO] 재무 데이터 수집 대상: {len(tickers_to_fetch)} 종목")
    
    if not tickers_to_fetch:
        print("[INFO] 수집할 재무 데이터가 없습니다.")
        return
    
    # 최근 N년 분기 목록 생성
    current_year = datetime.now().year
    years = [str(current_year - i) for i in range(years_back + 1)]
    quarters = [
        ('11013', 'Q1'),
        ('11012', 'Q2'),
        ('11014', 'Q3'),
        ('11011', 'Q4')
    ]
    
    # 진행바와 함께 수집
    for i, (stock_code, corp_code) in enumerate(tqdm(tickers_to_fetch, 
                                                       desc="Fetching financials", 
                                                       unit="ticker"), 1):
        df = collect_financial_data_for_ticker(api_key, stock_code, corp_code, years, quarters)
        
        if not df.empty:
            # 파일 저장
            out_path = os.path.join(financials_dir, f"{stock_code}_financials.parquet")
            df.to_parquet(out_path, index=False)
        
        # 대주주 지분율 조회
        major_stake = fetch_major_shareholders(api_key, corp_code)
        if major_stake is not None:
            # 별도 파일로 저장 (간단히)
            stake_path = os.path.join(financials_dir, f"{stock_code}_shareholders.json")
            with open(stake_path, 'w', encoding='utf-8') as f:
                json.dump({'stock_code': stock_code, 'major_shareholder_stake': major_stake}, f)
        
        if (i % CFG.show_every_n == 0) or (i == len(tickers_to_fetch)):
            print(f"[INFO] 진행: {i}/{len(tickers_to_fetch)} 종목")
        
        # API 호출 제한 대응
        time.sleep(max(0.1, CFG.sleep_sec))


# -----------------------------
# 마스터(종목 리스트) 생성/갱신
# -----------------------------
def build_and_save_tickers(latest_bday_yyyymmdd: str, out_path: str) -> pd.DataFrame:
    ensure_dir(os.path.dirname(out_path))

    # 1순위: 로컬 korea_stocks.csv 활용 (가장 안정적)
    stock_csv = os.path.join("public", "korea_stocks.csv")
    if os.path.exists(stock_csv):
        print(f"[INFO] {stock_csv} 에서 티커를 로드합니다.")
        try:
            try:
                df_src = pd.read_csv(stock_csv, encoding='utf-8')
            except UnicodeDecodeError:
                df_src = pd.read_csv(stock_csv, encoding='cp949')
            
            df = pd.DataFrame()
            df['code'] = df_src['단축코드'].astype(str).str.zfill(6)
            df['name'] = df_src['한글 종목약명']
            df['market'] = df_src['시장구분']
            
            df.to_parquet(out_path, index=False)
            return df
        except Exception as e:
            print(f"[WARN] CSV 로드 실패: {e}")

    # 2순위: FinanceDataReader
    try:
        import FinanceDataReader as fdr
        print("[INFO] FinanceDataReader로 티커 데이터 수집 중...")
        df_krx = fdr.StockListing('KRX')
        df = pd.DataFrame()
        df['code'] = df_krx['Symbol'].astype(str).str.zfill(6)
        df['name'] = df_krx['Name']
        df['market'] = df_krx['Market']
        df.to_parquet(out_path, index=False)
        return df
    except Exception:
        pass

    # 이미 파일이 있으면 반환
    if os.path.exists(out_path):
        return pd.read_parquet(out_path)
    
    return pd.DataFrame(columns=["code", "name", "market"])


# -----------------------------
# 일봉 수집 (KIS API 활용 - 티커별 일자별 시세)
# -----------------------------
def save_daily_partition(df_day: pd.DataFrame, bars_dir: str) -> Optional[str]:
    """
    날짜 파티션 저장 후 경로 반환
    """
    if df_day.empty:
        return None

    # date 컬럼을 datetime으로 변환 (안전성)
    df_day["date"] = pd.to_datetime(df_day["date"])
    date_str = df_day["date"].iloc[0].strftime("%Y-%m-%d")
    part_dir = os.path.join(bars_dir, f"date={date_str}")
    ensure_dir(part_dir)
    out_path = os.path.join(part_dir, "part-0000.parquet")
    df_day.to_parquet(out_path, index=False)
    return out_path


# -----------------------------
# 증분 수집 파이프라인 (KIS 최적화)
# -----------------------------
def collect_bars_incremental(start_yyyymmdd: str, end_yyyymmdd: str, bars_dir: str, tickers_df: pd.DataFrame) -> None:
    ensure_dir(bars_dir)

    existing = list_existing_partitions_dates(bars_dir)
    days_ts = business_days(start_yyyymmdd, end_yyyymmdd)

    # 누락된 영업일만 대상
    missing_ts: List[pd.Timestamp] = []
    for ts in days_ts:
        ds = ts.strftime("%Y-%m-%d")
        if ds not in existing:
            missing_ts.append(ts)

    print(f"[INFO] Business days in window: {len(days_ts)}")
    print(f"[INFO] Missing days to fetch: {len(missing_ts)}")

    if not missing_ts:
        print("[INFO] Nothing to fetch (already up-to-date).")
        return

    # { 'YYYY-MM-DD': [ {row}, {row}, ... ] } 데이터 구조 준비
    data_by_date = {ts.strftime("%Y-%m-%d"): [] for ts in missing_ts}
    missing_dates_str = set(data_by_date.keys())

    # KIS API를 사용하여 티커별로 최근 30일 데이터를 가져와서 missing_ts에 배분
    # 이렇게 하면 티커당 1번의 API 호출로 여러 날짜를 커버 가능 (최대 30일)
    
    for i, (_, row) in enumerate(tqdm(tickers_df.iterrows(), total=len(tickers_df), desc="KIS fetching"), 1):
        code = row['code']
        market = row['market']
        
        # KIS 일자별 시세 (최근 30일)
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code,
            "fid_org_adj_prc": "1",
            "fid_period_div_code": "D"
        }
        
        # 재시도 로직 포함
        res = {}
        for attempt in range(CFG.max_retries):
            res = call_kis_api("/uapi/domestic-stock/v1/quotations/inquire-daily-price", params, "FHKST01010400")
            if res.get("output"):
                break
            time.sleep(CFG.retry_backoff_sec * (attempt + 1))
            
        output = res.get("output", [])
        if not output:
            continue
            
        for day_data in output:
            d_str = day_data.get("stck_bsop_date") # YYYYMMDD
            if not d_str:
                continue
            
            # YYYY-MM-DD 형식으로 변환
            fmt_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            
            if fmt_date in missing_dates_str:
                # 데이터 정규화 및 수집
                try:
                    data_by_date[fmt_date].append({
                        "date": pd.to_datetime(d_str),
                        "code": code,
                        "market": market,
                        "open": float(day_data.get("stck_oprc", 0) or 0),
                        "high": float(day_data.get("stck_hgpr", 0) or 0),
                        "low": float(day_data.get("stck_lwpr", 0) or 0),
                        "close": float(day_data.get("stck_clpr", 0) or 0),
                        "volume": float(day_data.get("acml_vol", 0) or 0),
                        "value": float(day_data.get("stck_clpr", 0) or 0) * float(day_data.get("acml_vol", 0) or 0)
                    })
                except Exception:
                    continue
        
        # 속도 제한 준수
        time.sleep(CFG.sleep_sec)

        if i % 500 == 0:
            print(f"[INFO] Processed {i}/{len(tickers_df)} tickers...")

    # 수집 완료된 데이터를 날짜별 파티션으로 저장
    print("[INFO] Saving collected data to partitions...")
    for d_str in sorted(data_by_date.keys()):
        rows = data_by_date[d_str]
        if rows:
            df_day = pd.DataFrame(rows)
            saved_path = save_daily_partition(df_day, bars_dir)
            if saved_path:
                print(f"[INFO] Saved {d_str}: {len(rows)} stocks -> {saved_path}")
        else:
            print(f"[WARN] No data found for {d_str}")


def main():
    latest = get_latest_business_day()

    # 기존 데이터의 마지막 날짜를 찾아서 그 다음 날부터 수집 시작
    existing_dates = list_existing_partitions_dates(CFG.bars_dir)
    if existing_dates:
        last_date = max(existing_dates)
        start_dt = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)
        start = yyyymmdd(start_dt)
        print(f"[INFO] Existing data up to {last_date}, starting collection from {start}")
    else:
        start = compute_window_start(latest, CFG.years, CFG.buffer_days)
        print(f"[INFO] No existing data, starting from {start}")

    keep_days = CFG.years * 365 + CFG.buffer_days

    print(f"[INFO] Latest business day : {latest}")
    print(f"[INFO] Window start        : {start}  (keep_days={keep_days})")

    # 1) 마스터(종목명/시장) 생성/갱신
    tickers = build_and_save_tickers(latest, CFG.tickers_path)
    print(f"[INFO] tickers saved: {CFG.tickers_path} (n={len(tickers)})")

    # 2) 증분 수집 (누락 영업일만)
    print(f"[INFO] collecting bars: {start} ~ {latest}")
    collect_bars_incremental(start, latest, CFG.bars_dir, tickers)

    # 3) 오래된 파티션 정리(기간 제한 유지)
    deleted = prune_old_partitions(CFG.bars_dir, keep_days=keep_days)
    if deleted > 0:
        print(f"[INFO] pruned old partitions: {deleted}")
    else:
        print("[INFO] no partitions pruned")

    # 4) DART 재무 데이터 수집 (분기당 1회만)
    print("\n[INFO] DART 재무 데이터 수집 확인...")
    dart_api_key = load_dart_api_key()
    
    if dart_api_key:
        if should_update_financials():
            print("[INFO] 새로운 분기입니다. 재무 데이터 수집을 시작합니다.")
            try:
                collect_financials_incremental(tickers, CFG.financials_dir, dart_api_key, years_back=2)
                save_financial_update_time()
                print("[INFO] DART 재무 데이터 수집 완료")
            except Exception as e:
                print(f"[ERROR] DART 재무 데이터 수집 실패: {e}")
        else:
            year, quarter = get_current_quarter()
            print(f"[INFO] 이번 분기({year}Q{quarter}) 재무 데이터는 이미 수집되었습니다.")
    else:
        print("[INFO] DART API 키가 없어 재무 데이터 수집을 건너뜁니다.")

    print("\n[INFO] done.")

    # 삼성전자 최신일 데이터 예제 출력
    try:
        existing_dates = list_existing_partitions_dates(CFG.bars_dir)
        if existing_dates:
            last_date = max(existing_dates)
            part_dir = os.path.join(CFG.bars_dir, f"date={last_date}")
            parquet_files = [f for f in os.listdir(part_dir) if f.endswith('.parquet')]
            if parquet_files:
                fp = os.path.join(part_dir, parquet_files[0])
                df_sample = pd.read_parquet(fp)
                samsung = df_sample[df_sample['code'] == '005930']
                if not samsung.empty:
                    print(f"\n[INFO] 삼성전자({last_date}) 최신일 데이터 예제:")
                    print(samsung.head(1).to_string(index=False))
                else:
                    print(f"\n[INFO] 삼성전자 데이터가 {last_date}에 없습니다.")
            else:
                print("\n[INFO] 파티션 파일이 없습니다.")
        else:
            print("\n[INFO] 기존 데이터가 없습니다.")
    except Exception as e:
        print(f"\n[ERROR] 삼성전자 데이터 출력 실패: {e}")


if __name__ == "__main__":
    main()
