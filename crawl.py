# -*- coding: utf-8 -*-
"""crawl.py

KRX 일봉 데이터 수집 프레임워크 (병렬 처리 버전)

- 저장: data/krx/bars/date=YYYY-MM-DD/part-0000.parquet
- EOD(장마감 후): 전체 종목 수집 + 시총 500억 유니버스 캐시 생성
- Intraday(장중): 유니버스(시총 500억)만 빠르게 업데이트(merge 권장)
"""

import argparse
import json
import os
import time
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
# from tqdm import tqdm # Original import
# Fallback for tqdm if not installed or to avoid issues in some envs
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs): return iterable

from dotenv import load_dotenv
import requests

load_dotenv()


# -----------------------------
# 네트워크 체크 유틸리티
# -----------------------------
def check_network_connection(timeout: int = 5) -> bool:
    """인터넷 연결 확인 (여러 호스트 시도)"""
    hosts = [
        "https://www.naver.com",
        "https://www.google.com",
        "https://finance.yahoo.com"
    ]
    for host in hosts:
        try:
            requests.get(host, timeout=timeout)
            return True
        except Exception:
            continue
    return False


def wait_for_network(max_wait_seconds: int = 300, check_interval: int = 10) -> bool:
    """네트워크 연결 대기 (최대 max_wait_seconds 동안)"""
    start = time.time()
    while time.time() - start < max_wait_seconds:
        if check_network_connection():
            return True
        print(f"[Network] Waiting for connection... (elapsed: {int(time.time() - start)}s)")
        time.sleep(check_interval)
    return False


def _atomic_to_parquet(df: pd.DataFrame, out_path: str) -> None:
    """Write parquet atomically to avoid partially-written/corrupted files."""
    tmp_path = out_path + ".tmp"
    df.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, out_path)


def _normalize_bars_df(df: pd.DataFrame, df_krx: pd.DataFrame | None = None) -> pd.DataFrame:
    """Normalize and validate bars dataframe schema.

    Ensures required columns exist and `code` is present.
    If `code` is missing but `name` exists, it attempts to recover `code` via KRX listing mapping.
    """
    if df is None or df.empty:
        raise ValueError("bars dataframe is empty")

    out = df.copy()
    # normalize column names
    out.columns = [str(c).lower() for c in out.columns]
    if 'code' not in out.columns:
        # try common alternatives
        if 'Code' in df.columns:
            out = out.rename(columns={'Code': 'code'})
        elif '단축코드' in df.columns:
            out = out.rename(columns={'단축코드': 'code'})

    if 'code' not in out.columns:
        if 'name' in out.columns and df_krx is not None and not df_krx.empty:
            # recover by name mapping (best-effort)
            tmp = df_krx.copy()
            if 'Code' in tmp.columns and 'Name' in tmp.columns:
                tmp['Code'] = tmp['Code'].apply(_zfill_code)
                name_to_code = dict(zip(tmp['Name'].astype(str), tmp['Code'].astype(str)))
                out['code'] = out['name'].astype(str).map(name_to_code)

    required = ['date', 'code', 'open', 'high', 'low', 'close', 'volume']
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"bars dataframe missing required columns: {missing}")

    out['code'] = out['code'].astype(str).str.zfill(6)
    out['date'] = pd.to_datetime(out['date'], errors='coerce')
    out = out.dropna(subset=['date', 'code'])
    # numeric coercions
    for c in ['open', 'high', 'low', 'close', 'volume']:
        out[c] = pd.to_numeric(out[c], errors='coerce')
    # optional fields
    if 'change' in out.columns:
        out['change'] = pd.to_numeric(out['change'], errors='coerce')
    else:
        # keep downstream compatibility
        out['change'] = np.nan
    if 'name' in out.columns:
        out['name'] = out['name'].astype(str)

    # keep a stable column order
    ordered = ['date', 'code', 'open', 'high', 'low', 'close', 'volume', 'change']
    if 'name' in out.columns:
        ordered.append('name')
    # append any extra columns at the end
    extras = [c for c in out.columns if c not in ordered]
    return out[ordered + extras]


def repair_bars_partition(target_date: str) -> str | None:
    """Repair an existing bars partition if it is missing the `code` column.

    This is intended for recovering from a bad write (e.g. scheduled crawl failure).
    """
    save_dir = os.path.join(DATA_DIR, f"date={target_date}")
    save_path = os.path.join(save_dir, "part-0000.parquet")
    if not os.path.exists(save_path):
        print(f"[REPAIR] Partition not found: {save_path}")
        return None

    try:
        df = pd.read_parquet(save_path)
    except Exception as e:
        print(f"[REPAIR] Failed to read parquet: {e}")
        return None

    if 'code' in [str(c).lower() for c in df.columns]:
        print(f"[REPAIR] OK (code exists): {save_path}")
        return save_path

    print(f"[REPAIR] Missing code column; attempting recovery by name mapping: {save_path}")
    try:
        df_krx = _get_krx_listing()
        df_krx['Code'] = df_krx['Code'].apply(_zfill_code)
        fixed = _normalize_bars_df(df, df_krx=df_krx)
        ensure_dir(save_dir)
        _atomic_to_parquet(fixed, save_path)
        print(f"[REPAIR] Rewrote partition: {save_path} (rows={len(fixed)})")
        return save_path
    except Exception as e:
        print(f"[REPAIR] Recovery failed: {e}")
        return None

# -----------------------------
# 설정
# -----------------------------
DATA_DIR = "data/krx/bars"
UNIVERSE_DIR = "data/krx/master/universe_mcap500"
UNIVERSE_JSON_PATH = "data/user/universe_mcap500.json"
MAX_WORKERS = 8  # 병렬 작업 개수 (너무 높으면 차단될 수 있음, 8~16 추천)
START_YEAR = 2020  # 수집 시작 연도 (최초 실행시)
MCAP_THRESHOLD_KRW = 50_000_000_000  # 500억

# -----------------------------
# 유틸리티
# -----------------------------
def get_recent_business_day():
    """오늘이 휴일이면 전 영업일, 아니면 오늘 날짜 반환 (평일 기준 간단 처리)"""
    today = datetime.now()
    if today.weekday() >= 5: # 토, 일
        gap = today.weekday() - 4
        return (today - timedelta(days=gap)).strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d")


def _parse_ymd(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def iter_dates_inclusive(start_date: str, end_date: str) -> list[str]:
    """Return YYYY-MM-DD list from start..end inclusive."""
    start_dt = _parse_ymd(start_date)
    end_dt = _parse_ymd(end_date)
    if end_dt < start_dt:
        raise ValueError(f"end_date < start_date: {start_date}..{end_date}")

    out: list[str] = []
    cur = start_dt
    while cur <= end_dt:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def is_weekday(date_str: str) -> bool:
    """Fast weekday check (does not know KRX holidays)."""
    return _parse_ymd(date_str).weekday() < 5

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def _zfill_code(code: str) -> str:
    return str(code).zfill(6)


def get_recent_trading_days(n: int = 3) -> list[str]:
    """최근 N 영업일(거래일) 목록 반환 (주말 제외, 공휴일은 정확하지 않음)"""
    days = []
    check_date = datetime.now()
    while len(days) < n:
        check_date -= timedelta(days=1)
        if check_date.weekday() < 5:  # 평일만
            days.append(check_date.strftime("%Y-%m-%d"))
    return days


def get_suspended_codes(lookback_days: int = 3) -> set[str]:
    """
    최근 N 영업일 내 거래정지 이력(volume=0)이 있는 종목 코드 집합 반환.
    - bars 파티션에서 최근 데이터를 확인하여 volume=0인 종목을 찾음
    """
    recent_dates = get_recent_trading_days(lookback_days)
    suspended_codes = set()
    
    for date_str in recent_dates:
        partition_path = os.path.join(DATA_DIR, f"date={date_str}", "part-0000.parquet")
        if os.path.exists(partition_path):
            try:
                df = pd.read_parquet(partition_path)
                if "volume" in df.columns and "code" in df.columns:
                    # volume이 0 또는 NaN인 종목 추출
                    zero_vol = df[(df["volume"].isna()) | (df["volume"] == 0)]
                    suspended_codes.update(zero_vol["code"].apply(_zfill_code).tolist())
            except Exception as e:
                print(f"[WARN] Failed to read {partition_path}: {e}")
    
    return suspended_codes


def load_share_count_mapping() -> dict:
    """public/korea_stocks.csv의 상장주식수 매핑 로드 (code -> shares)."""
    csv_path = "public/korea_stocks.csv"
    if not os.path.exists(csv_path):
        return {}
    try:
        df = pd.read_csv(csv_path)
        if "단축코드" not in df.columns or "상장주식수" not in df.columns:
            return {}
        df["단축코드"] = df["단축코드"].apply(lambda x: str(x).zfill(6))
        return dict(zip(df["단축코드"], df["상장주식수"]))
    except Exception:
        return {}


def build_universe_cache_from_bars(target_date: str, bars_path: str) -> pd.DataFrame:
    """해당 날짜 bars parquet 기준으로 시총 500억 유니버스 캐시 생성."""
    if not os.path.exists(bars_path):
        raise FileNotFoundError(f"bars not found: {bars_path}")

    df = pd.read_parquet(bars_path)
    if df.empty:
        raise ValueError("bars parquet is empty")

    df = df.copy()
    df["code"] = df["code"].apply(_zfill_code)

    shares_map = load_share_count_mapping()
    if not shares_map:
        raise ValueError("share count mapping not available (public/korea_stocks.csv)")

    df["shares"] = df["code"].map(shares_map).fillna(0)
    df["market_cap"] = df["close"].astype(float) * df["shares"].astype(float)

    uni = df.loc[df["market_cap"] >= MCAP_THRESHOLD_KRW, ["code", "market_cap", "close"]].copy()
    uni.insert(0, "date", target_date)
    uni = uni.sort_values(["market_cap", "code"], ascending=[False, True]).reset_index(drop=True)
    return uni


def save_universe_cache(target_date: str, universe_df: pd.DataFrame) -> None:
    """유니버스 캐시를 parquet+json로 저장."""
    ensure_dir(UNIVERSE_DIR)
    dated_dir = os.path.join(UNIVERSE_DIR, f"date={target_date}")
    ensure_dir(dated_dir)
    dated_path = os.path.join(dated_dir, "part-0000.parquet")
    universe_df.to_parquet(dated_path, index=False)

    latest_path = os.path.join(UNIVERSE_DIR, "latest.parquet")
    universe_df.to_parquet(latest_path, index=False)

    # JSON (빠른 로드용)
    ensure_dir(os.path.dirname(UNIVERSE_JSON_PATH))
    payload = {
        "date": target_date,
        "threshold_krw": MCAP_THRESHOLD_KRW,
        "codes": universe_df["code"].astype(str).tolist(),
    }
    with open(UNIVERSE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_universe_codes() -> list:
    """저장된 유니버스 캐시에서 code list 로드 (latest 우선)."""
    latest_path = os.path.join(UNIVERSE_DIR, "latest.parquet")
    if os.path.exists(latest_path):
        df = pd.read_parquet(latest_path)
        if not df.empty and "code" in df.columns:
            return df["code"].astype(str).str.zfill(6).tolist()

    if os.path.exists(UNIVERSE_JSON_PATH):
        try:
            with open(UNIVERSE_JSON_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            codes = payload.get("codes", [])
            return [str(c).zfill(6) for c in codes]
        except Exception:
            return []

    return []

# -----------------------------
# 크롤링 코어 로직
# -----------------------------
def process_single_stock(code, date_start, date_end, max_retries: int = 3):
    """
    한 종목의 기간 데이터를 가져옵니다. (네트워크 오류 시 재시도)
    """
    for attempt in range(max_retries):
        try:
            # FDRDataReader는 symbol, start, end
            # KRX 종목코드는 숫자로만 되어있을 수 있으므로 확인 필요하지만 fdr이 알아서 처리함
            df = fdr.DataReader(code, date_start, date_end)
            if df.empty:
                return None
            
            df = df.reset_index()
            # 컬럼 이름 소문자 통일 (Date -> date, Close -> close 등)
            # fdr returns columns like: Date, Open, High, Low, Close, Volume, Change
            df.columns = [c.lower() for c in df.columns]
            df['code'] = code
            
            # 필요한 컬럼만
            cols = ['date', 'code', 'open', 'high', 'low', 'close', 'volume', 'change']
            
            # 컬럼 존재 여부 확인 후 선택
            available_cols = [c for c in cols if c in df.columns]
            
            # change 컬럼이 없는 경우 계산 (혹시 모를 대비)
            if 'change' not in available_cols and 'close' in df.columns:
                df['change'] = df['close'].pct_change().fillna(0)
                available_cols.append('change')
                
            return df[available_cols]
            
        except Exception as e:
            error_str = str(e).lower()
            # 네트워크 관련 오류인 경우 재시도
            if any(keyword in error_str for keyword in ['connection', 'timeout', 'network', 'unreachable', 'refused']):
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))  # 점진적 대기
                    continue
            # 그 외 오류는 바로 None 반환
            return None
    return None


def _get_krx_listing(max_retries: int = 3) -> pd.DataFrame:
    """KRX 종목 리스트 가져오기 (네트워크 오류 시 재시도)"""
    print(">>> 종목 리스트 가져오는 중...")
    for attempt in range(max_retries):
        try:
            return fdr.StockListing("KRX")
        except Exception as e:
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['connection', 'timeout', 'network', 'unreachable']):
                if attempt < max_retries - 1:
                    print(f"[WARN] KRX listing fetch failed (attempt {attempt + 1}), retrying...")
                    time.sleep(5 * (attempt + 1))
                    continue
            raise  # 재시도 소진 시 예외 전파
    raise RuntimeError("Failed to fetch KRX listing after retries")


def update_data_parallel(
    target_date: str | None = None,
    codes: list[str] | None = None,
    merge_existing: bool = False,
    lookback_days: int = 5,
) -> str | None:
    """병렬 처리로 일봉(또는 장중 last) 데이터를 수집하여 parquet로 저장.

    - codes=None: 전체 종목
    - merge_existing=True: 기존 date 파티션이 있으면 code 단위로 업데이트

    Returns: 저장된 parquet 경로 (성공), None (실패)
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    try:
        df_krx = _get_krx_listing()
    except Exception as e:
        print(f"Error fetching stock listing: {e}")
        return None

    df_krx["Code"] = df_krx["Code"].apply(_zfill_code)
    if codes:
        codes_set = {str(c).zfill(6) for c in codes}
        df_krx = df_krx[df_krx["Code"].isin(codes_set)].copy()

    tickers = df_krx[["Code", "Name"]].values.tolist()
    print(f">>> 총 {len(tickers)}개 종목 업데이트 시작 (병렬: {MAX_WORKERS}개)")

    save_dir = os.path.join(DATA_DIR, f"date={target_date}")
    save_path = os.path.join(save_dir, "part-0000.parquet")
    ensure_dir(save_dir)

    # 오늘 데이터 수집을 위해 최근 N일치 정도를 넉넉히 가져와서 필터링
    start_date = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = target_date

    today_results: list[pd.DataFrame] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_code = {
            executor.submit(process_single_stock, t[0], start_date, end_date): t for t in tickers
        }

        for future in tqdm(as_completed(future_to_code), total=len(tickers), desc="Fetching"):
            res_df = future.result()
            if res_df is None or res_df.empty:
                continue

            # 오늘 날짜 데이터만 필터링
            res_df["date_str"] = res_df["date"].dt.strftime("%Y-%m-%d")
            today_data = res_df[res_df["date_str"] == target_date].copy()
            if today_data.empty:
                continue

            code = _zfill_code(today_data["code"].iloc[0])
            name_val = future_to_code[future][1] if future in future_to_code else ""
            today_data["code"] = code
            today_data["name"] = name_val
            today_data = today_data.drop(columns=["date_str"])
            today_results.append(today_data)

    if not today_results:
        print(f"[{target_date}] 수집된 데이터가 없습니다. (휴장일이거나 데이터가 아직 업데이트되지 않았습니다.)")
        return None

    print(">>> 데이터 병합 및 저장 중...")
    new_df = pd.concat(today_results, ignore_index=True)
    # Validate schema before writing to parquet (prevents malformed partitions)
    try:
        new_df = _normalize_bars_df(new_df, df_krx=df_krx)
    except Exception as e:
        print(f"[ERROR] Refusing to write malformed bars parquet for {target_date}: {e}")
        return None

    if merge_existing and os.path.exists(save_path):
        try:
            old_df = pd.read_parquet(save_path)
            if not old_df.empty:
                old_df = old_df.copy()
                old_df["code"] = old_df["code"].apply(_zfill_code)
                new_df["code"] = new_df["code"].apply(_zfill_code)

                old_df = old_df.set_index("code")
                new_df = new_df.set_index("code")
                old_df.update(new_df)
                merged = old_df.reset_index()
                merged = _normalize_bars_df(merged, df_krx=df_krx)
                _atomic_to_parquet(merged, save_path)
                print(f"✅ 저장 완료(merge): {save_path} (총 {len(merged)}개 종목)")
                return save_path
        except Exception as e:
            print(f"[WARN] merge failed, fallback to overwrite: {e}")

    # 새로 저장하거나 merge 실패 시 덮어쓰기
    _atomic_to_parquet(new_df, save_path)
    print(f"✅ 저장 완료: {save_path} (총 {len(new_df)}개 종목)")
    return save_path


def main():
    global MAX_WORKERS

    parser = argparse.ArgumentParser(description="KRX daily/intraday crawler")
    parser.add_argument(
        "--mode",
        choices=["eod", "intraday"],
        default="eod",
        help="eod: 전체 수집 후 유니버스 캐시 생성 / intraday: 유니버스만 업데이트",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        help="YYYY-MM-DD (기본: 오늘). 단일 날짜만 업데이트",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="YYYY-MM-DD (지정 시 --end-date와 함께 날짜 범위 업데이트)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="YYYY-MM-DD (지정 시 --start-date와 함께 날짜 범위 업데이트)",
    )
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="날짜 범위 업데이트 시 주말도 시도 (기본: 주말은 skip)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help="병렬 워커 수 (기본: 8)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="기존 date 파티션이 있으면 code 단위로 merge 업데이트",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="(intraday 권장 X) 기존 date 파티션을 덮어쓰기",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=5,
        help="데이터 로드 lookback 일수 (기본: 5)",
    )
    parser.add_argument(
        "--repair-date",
        default=None,
        help="YYYY-MM-DD: 기존 bars parquet가 깨졌을 때(code 누락) 복구 시도",
    )
    args = parser.parse_args()

    MAX_WORKERS = args.workers

    if args.repair_date:
        repair_bars_partition(args.repair_date)
        return

    # Build date list
    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            raise ValueError("Both --start-date and --end-date are required for range updates")
        date_list = iter_dates_inclusive(args.start_date, args.end_date)
        if not args.include_weekends:
            date_list = [d for d in date_list if is_weekday(d)]
        if not date_list:
            print("[WARN] date range produced no dates after filtering")
            return
    else:
        target_date = args.target_date or datetime.now().strftime("%Y-%m-%d")
        date_list = [target_date]

    if args.mode == "intraday":
        # Intraday uses universe cache codes (same list reused across all dates)
        codes = load_universe_codes()
        if not codes:
            print(
                "[WARN] universe cache not found. Run '--mode eod' after close at least once to create it."
            )
            return

        # 최근 3영업일 내 거래정지 이력(volume=0)이 있는 종목 제외
        suspended = get_suspended_codes(lookback_days=3)
        if suspended:
            original_count = len(codes)
            codes = [c for c in codes if c not in suspended]
            filtered_count = original_count - len(codes)
            if filtered_count > 0:
                print(f"[INFO] Filtered out {filtered_count} suspended stocks (volume=0 in last 3 days)")

        for d in date_list:
            print("=" * 70)
            print(f"[INTRADAY] Updating universe for {d} ({len(codes)} codes)")
            print("=" * 70)
            saved_path = update_data_parallel(
                target_date=d,
                codes=codes,
                merge_existing=(False if args.overwrite else True),
                lookback_days=args.lookback_days,
            )
            if saved_path:
                print(f"[INFO] Intraday update done: {saved_path}")
        return

    # EOD: 전체 수집
    last_success_date: str | None = None
    last_success_path: str | None = None
    for d in date_list:
        print("=" * 70)
        print(f"[EOD] Updating all tickers for {d}")
        print("=" * 70)
        saved_path = update_data_parallel(
            target_date=d,
            codes=None,
            merge_existing=(False if args.overwrite else args.merge),
            lookback_days=args.lookback_days,
        )
        if not saved_path:
            continue

        last_success_date = d
        last_success_path = saved_path

        # EOD 종료 후 유니버스 캐시 생성 (해당 날짜 기준)
        try:
            uni = build_universe_cache_from_bars(d, saved_path)
            save_universe_cache(d, uni)
            print(f"✅ 유니버스 캐시 생성 완료: {UNIVERSE_DIR} (총 {len(uni)}개)")
        except Exception as e:
            print(f"[WARN] universe cache build failed ({d}): {e}")

    if last_success_date is None:
        print("[WARN] No successful EOD updates in the requested date list")
        return

    print(f"[INFO] Last successful date: {last_success_date} ({last_success_path})")

if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    print(f"⏱ 소요 시간: {end_time - start_time:.2f}초 ({ (end_time - start_time)/60:.1f}분 )")
