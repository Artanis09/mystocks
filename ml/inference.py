# -*- coding: utf-8 -*-
"""
Inference - 실시간 예측 및 추천 종목 생성
"""
import argparse
import sys
from pathlib import Path

# Allow running as a script: `python ml/inference.py`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import os
import glob
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Literal, Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
import re

from ml.config import CFG
from ml.data_pipeline import load_all_bars, compute_technical_indicators, get_feature_columns


def get_suspended_codes_recent(lookback_days: int = 3) -> set:
    """
    최근 N 영업일 내 거래정지 이력(volume=0)이 있는 종목 코드 집합 반환.
    - bars 파티션에서 최근 데이터를 확인하여 volume=0인 종목을 찾음
    """
    bars_dir = CFG.bars_dir
    suspended_codes = set()
    
    # 최근 N 영업일 찾기 (주말 제외)
    recent_dates = []
    check_date = datetime.now()
    while len(recent_dates) < lookback_days:
        check_date -= timedelta(days=1)
        if check_date.weekday() < 5:  # 평일만
            recent_dates.append(check_date.strftime("%Y-%m-%d"))
    
    for date_str in recent_dates:
        partition_path = os.path.join(bars_dir, f"date={date_str}", "part-0000.parquet")
        if os.path.exists(partition_path):
            try:
                df = pd.read_parquet(partition_path)
                if "volume" in df.columns and "code" in df.columns:
                    # volume이 0 또는 NaN인 종목 추출
                    zero_vol = df[(df["volume"].isna()) | (df["volume"] == 0)]
                    suspended_codes.update(zero_vol["code"].apply(lambda x: str(x).zfill(6)).tolist())
            except Exception as e:
                print(f"[WARN] Failed to read {partition_path}: {e}")
    
    return suspended_codes


def resolve_model_path(model_name: str, explicit_path: Optional[str] = None) -> str:
    """모델 이름 또는 경로로 실제 모델 경로를 결정."""
    if explicit_path:
        return explicit_path

    pattern = 'catboost_*.cbm'
    if model_name == 'model5':
        pattern = 'lgbm_model5_*.txt'

    model_files = glob.glob(os.path.join(CFG.model_dir, pattern))
    if not model_files:
        raise FileNotFoundError(f"No trained model found for pattern {pattern}. Run training first.")
    return max(model_files, key=os.path.getctime)


def _meta_path_for_model(model_path: str) -> str:
    if model_path.endswith('.cbm'):
        return model_path.replace('.cbm', '_meta.json')
    if model_path.endswith('.txt'):
        return model_path.replace('.txt', '_meta.json')
    return model_path + '_meta.json'


def _infer_positive_return_from_meta(meta: Optional[dict], default: float) -> float:
    """Infer a representative positive return for expected_return scoring.

    This value is only used for ranking; any positive scalar keeps the same order.
    """
    if not meta:
        return default

    definition = str(meta.get('definition') or '')
    # e.g. "... >= 0.02"
    m = re.search(r">=\s*(0\.\d+)", definition)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return default
    return default


def load_model(model_path: str = None, model_name: str = 'model1') -> Tuple[Any, dict]:
    """
    학습된 모델 로드
    """
    if model_path is None:
        model_path = resolve_model_path(model_name, None)

    if model_name == 'model5' or str(model_path).endswith('.txt'):
        try:
            import lightgbm as lgb
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(
                "model5 requires 'lightgbm'. Install with: pip install lightgbm (or pip install -r requirements.txt)"
            ) from e

        model = lgb.Booster(model_file=model_path)
    else:
        model = CatBoostClassifier()
        model.load_model(model_path)
    
    # 메타데이터 로드
    meta_path = _meta_path_for_model(model_path)
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    
    print(f"[INFO] Model loaded: {model_path}")
    return model, meta


def get_recent_data(lookback_days: int = 300) -> pd.DataFrame:
    """
    최근 N일간의 데이터 로드 (피처 계산을 위한 충분한 기간)
    """
    bars_dir = CFG.bars_dir
    partitions = sorted([
        d for d in os.listdir(bars_dir) 
        if d.startswith('date=')
    ], reverse=True)
    
    # 최근 N개 파티션만 로드
    recent_partitions = partitions[:lookback_days]
    
    all_data = []
    for partition in recent_partitions:
        path = os.path.join(bars_dir, partition, 'part-0000.parquet')
        if os.path.exists(path):
            df = pd.read_parquet(path)
            # Some daily snapshots may be malformed (e.g., missing 'code').
            # Skip them so they don't poison latest_date detection.
            if 'code' not in df.columns:
                print(f"[WARN] Missing 'code' column in {path}; skipping this partition")
                continue
            all_data.append(df)
    
    if not all_data:
        raise ValueError("No recent data found")
    
    result = pd.concat(all_data, ignore_index=True)
    result['date'] = pd.to_datetime(result['date'])
    result = result.sort_values(['code', 'date']).reset_index(drop=True)
    
    return result


def prepare_inference_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    추론을 위한 피처 준비 (최신 날짜만)
    """
    # 종목별 기술적 지표 계산
    results = []
    for code, group in df.groupby('code'):
        group = group.sort_values('date').reset_index(drop=True)
        if len(group) < 60:
            continue
        
        processed = compute_technical_indicators(group)
        # 마지막 행만 (가장 최근 날짜)
        # 0.8 확률 전략에 필요한 open 가격 유지를 위해 select 시 포함 확인
        results.append(processed.iloc[-1:])
    
    if not results:
        raise ValueError("No valid data for inference")
    
    return pd.concat(results, ignore_index=True)


def predict_next_day(
    model: Any,
    df: pd.DataFrame,
    top_k: int = 5,
    min_prob_threshold: float = 0.70,
    min_market_cap_krw: float = 50_000_000_000,
    daily_strength_min: float = -0.05,
    return_1d_min: Optional[float] = -0.05,
    upper_lock_cut: Optional[float] = 0.295,
    model_name: str = 'model1',
    meta: Optional[dict] = None,
    filter_suspended_days: int = 3,  # 최근 N영업일 거래정지 이력 필터
) -> pd.DataFrame:
    """
    다음 날 상승 예측 - 최종 필터 조건 적용
    1. 확률 >= min_prob_threshold
    2. 시가총액 >= min_market_cap_krw (기본 500억)
    3. 최근 N영업일 이내 거래정지 이력(volume=0) 없음
    3. 당일 시가 대비 종가 변동률 >= daily_strength_min (기본 -5%)
    4. 전일대비 수익률 return_1d >= return_1d_min (옵션)
    5. 상한가(체결 불가) 근사 제거: return_1d < upper_lock_cut (옵션)
    """
    feature_cols = list(meta.get('features')) if (meta and meta.get('features')) else get_feature_columns()
    
    # 1. 시가총액 필터 준비 (상장주식수 로드)
    try:
        stocks_info = pd.read_csv('public/korea_stocks.csv')
        stocks_info['단축코드'] = stocks_info['단축코드'].apply(lambda x: str(x).zfill(6))
        code_to_shares = dict(zip(stocks_info['단축코드'], stocks_info['상장주식수']))
        
        df = df.copy()
        df['shares'] = df['code'].map(code_to_shares).fillna(0)
        df['market_cap'] = df['close'] * df['shares']
    except Exception as e:
        print(f"[WARN] Failed to load market cap info: {e}")
        df['market_cap'] = 0  # 정보 없으면 0으로 처리하여 필터링되게 함
    
    # 2. 피처 추출 및 예측
    X = df[feature_cols]

    # LightGBM model5 (binary)
    if model_name == 'model5' or model.__class__.__name__.lower().startswith('booster'):
        positive_proba = np.asarray(model.predict(X.values))
        if positive_proba.ndim != 1:
            positive_proba = positive_proba.reshape(-1)
        pos_ret = _infer_positive_return_from_meta(meta, default=0.02)
        expected_return = positive_proba * pos_ret
    else:
        proba = model.predict_proba(X.values)
        
        # 확률/기대수익 계산 (멀티클래스 vs 바이너리)
        if proba.shape[1] == 2:
            positive_proba = proba[:, 1]
            class_returns = np.array([0.0, 0.035])
        else:
            positive_proba = proba[:, CFG.min_positive_class:].sum(axis=1)
            class_returns = np.array([0.0, 0.035, 0.065, 0.10, 0.155, 0.24, 0.35])

        expected_return = (proba * class_returns).sum(axis=1)
    
    # 결과 DataFrame 생성
    base_cols = ['date', 'code', 'close', 'open', 'volume', 'market_cap']
    if 'return_1d' in df.columns:
        base_cols.append('return_1d')
    result = df[base_cols].copy()
    result['positive_proba'] = positive_proba
    result['expected_return'] = expected_return

    # 당일 등락률(시가→종가)
    result['intraday_return'] = (result['close'] - result['open']) / result['open']
    
    # 3. 최종 필터 적용
    # 3.1 확률 임계값
    mask = (result['positive_proba'] >= min_prob_threshold)
    # 3.2 시가총액
    mask &= (result['market_cap'] >= min_market_cap_krw)
    # 3.3 거래정지 제외 (당일 거래량 0 필수 필터)
    mask &= (result['volume'] > 0)
    
    # 3.3.1 최근 N영업일 이내 거래정지 이력 제외
    if filter_suspended_days and filter_suspended_days > 0:
        suspended_codes = get_suspended_codes_recent(lookback_days=filter_suspended_days)
        if suspended_codes:
            result['code_padded'] = result['code'].apply(lambda x: str(x).zfill(6))
            mask &= ~result['code_padded'].isin(suspended_codes)
            print(f"[INFO] Filtering out {len(suspended_codes)} stocks with volume=0 in last {filter_suspended_days} days")
    
    # 3.4 당일 시가 대비 종가 변동률 (장대음봉 제외)
    mask &= (result['intraday_return'] >= daily_strength_min)

    # 3.5 전일 대비 수익률 필터 (너무 센 음봉 제거)
    if 'return_1d' in result.columns and return_1d_min is not None:
        mask &= (result['return_1d'] >= return_1d_min)

    # 3.6 상한가(체결 불가) 근사 제거
    if 'return_1d' in result.columns and upper_lock_cut is not None:
        mask &= (result['return_1d'] < upper_lock_cut)
    
    candidates = result[mask].copy()
    
    # 기대 수익률 순으로 정렬
    candidates = candidates.sort_values('expected_return', ascending=False)
    
    # 상위 K개 선택
    top_candidates = candidates.head(top_k)
    
    return top_candidates


def get_stock_name_mapping() -> Dict[str, str]:
    """
    종목코드-종목명 매핑 로드
    """
    # 1. korea_stocks.csv (최신 상장주식수 포함)
    csv_path = 'public/korea_stocks.csv'
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            df['단축코드'] = df['단축코드'].apply(lambda x: str(x).zfill(6))
            return dict(zip(df['단축코드'], df['한글 종목약명']))
        except:
            pass

    # 2. tickers.parquet (백업)
    tickers_path = os.path.join('data/krx/master/tickers.parquet')
    if os.path.exists(tickers_path):
        df = pd.read_parquet(tickers_path)
        return dict(zip(df['code'], df['name']))
    
    return {}


def run_inference(
    model_path: str = None,
    top_k: int = 5,
    model_name: str = 'model1',
    min_prob_threshold: float = 0.70,
    min_market_cap_krw: float = 50_000_000_000,
    daily_strength_min: float = -0.05,
    return_1d_min: Optional[float] = -0.05,
    upper_lock_cut: Optional[float] = 0.295,
    save_result: bool = True
) -> pd.DataFrame:
    """
    전체 추론 파이프라인 실행
    """
    print("=" * 60)
    print("Stock Price Prediction - Inference (Final Strategic Filter)")
    parts = [
        f"Top-{top_k}",
        f"Prob >= {min_prob_threshold*100:.0f}%",
        f"Cap >= {min_market_cap_krw/1e8:,.0f}억",
        f"Daily >= {daily_strength_min*100:.1f}%",
    ]
    if return_1d_min is not None and upper_lock_cut is not None:
        parts.append(f"return_1d in [{return_1d_min*100:.1f}%, {upper_lock_cut*100:.1f}%)")
    elif return_1d_min is not None:
        parts.append(f"return_1d >= {return_1d_min*100:.1f}%")
    elif upper_lock_cut is not None:
        parts.append(f"return_1d < {upper_lock_cut*100:.1f}%")
    print("Condition: " + ", ".join(parts))
    print("=" * 60)
    
    # 모델 로드
    model, meta = load_model(model_path, model_name=model_name)
    
    # 최근 데이터 로드
    print("\n[INFO] Loading recent data...")
    recent_data = get_recent_data(lookback_days=300)
    latest_date_dt = recent_data['date'].max().normalize()
    latest_date = latest_date_dt.strftime('%Y-%m-%d')
    print(f"[INFO] Latest data date: {latest_date}")
    
    # 피처 준비
    print("[INFO] Preparing features...")
    inference_data = prepare_inference_features(recent_data)
    if 'date' in inference_data.columns:
        inference_data = inference_data[inference_data['date'].dt.normalize() == latest_date_dt].copy()
    print(f"[INFO] {len(inference_data)} stocks ready for prediction")
    
    # 예측
    print(f"[INFO] Running Filtered Prediction...")
    predictions = predict_next_day(
        model, 
        inference_data, 
        top_k=top_k,
        min_prob_threshold=min_prob_threshold,
        min_market_cap_krw=min_market_cap_krw,
        daily_strength_min=daily_strength_min,
        return_1d_min=return_1d_min,
        upper_lock_cut=upper_lock_cut,
        model_name=model_name,
        meta=meta,
    )
    
    # 종목명 추가
    name_mapping = get_stock_name_mapping()
    predictions['name'] = predictions['code'].map(name_mapping).fillna('Unknown')
    
    # 결과 출력
    print("\n" + "=" * 60)
    print(f"🚀 FINAL TOP-{len(predictions)} STRATEGIC PICKS for {latest_date} → Next Day")
    print("=" * 60)
    
    if len(predictions) == 0:
        print("  [WARN] No stocks met the strict filter criteria today.")
    else:
        for i, (idx, row) in enumerate(predictions.iterrows()):
            prob_str = f"{row['positive_proba']*100:.1f}%"
            cap_str = f"{row['market_cap']/1e8:,.0f}억"
            exp_ret = f"{row['expected_return']*100:.2f}%"
            intra = row.get('intraday_return', np.nan)
            intra_str = "-" if (intra is None or (isinstance(intra, float) and np.isnan(intra))) else f"{intra*100:+.2f}%"
            print(f"  {i+1}. {row['code']} {row['name'][:8]:<8} | "
                  f"종가: {row['close']:>8,.0f} | "
                  f"당일: {intra_str:>7} | "
                  f"시총: {cap_str:>7} | "
                  f"상승확률: {prob_str:>6} | "
                  f"기대수익: {exp_ret:>6}")
    
    # 결과 저장
    if save_result:
        os.makedirs('ml/predictions', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f'ml/predictions/final_picks_{timestamp}.csv'
        predictions.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n[INFO] Strategic picks saved to {output_path}")
    
    return predictions


FilterTag = Literal['filter1', 'filter2']


def run_inference_both(
    model_path: str = None,
    top_k: int = 5,
    save_result: bool = True,
    model_name: str = 'model1',
) -> Dict[FilterTag, pd.DataFrame]:
    """Run both Filter1 and Filter2 on the same latest-day inference snapshot."""
    print("=" * 60)
    print("Stock Price Prediction - Inference (Filter1 vs Filter2)")
    print("=" * 60)

    model, meta = load_model(model_path, model_name=model_name)

    print("\n[INFO] Loading recent data...")
    recent_data = get_recent_data(lookback_days=300)
    latest_date_dt = recent_data['date'].max().normalize()
    latest_date = latest_date_dt.strftime('%Y-%m-%d')
    print(f"[INFO] Latest data date: {latest_date}")

    print("[INFO] Preparing features...")
    inference_data = prepare_inference_features(recent_data)
    if 'date' in inference_data.columns:
        inference_data = inference_data[inference_data['date'].dt.normalize() == latest_date_dt].copy()
    print(f"[INFO] {len(inference_data)} stocks ready for prediction")

    # Filter1 (기존 문서 기준)
    f1 = predict_next_day(
        model,
        inference_data,
        top_k=top_k,
        min_prob_threshold=0.80,
        min_market_cap_krw=50_000_000_000,
        daily_strength_min=-0.05,
        return_1d_min=None,
        upper_lock_cut=None,
        model_name=model_name,
        meta=meta,
    )

    # Filter2 (최종 적용)
    f2 = predict_next_day(
        model,
        inference_data,
        top_k=top_k,
        min_prob_threshold=0.70,
        min_market_cap_krw=50_000_000_000,
        daily_strength_min=-0.05,
        return_1d_min=-0.05,
        upper_lock_cut=0.295,
        model_name=model_name,
        meta=meta,
    )

    name_mapping = get_stock_name_mapping()
    for df_, tag in ((f1, 'filter1'), (f2, 'filter2')):
        if not df_.empty:
            df_['name'] = df_['code'].map(name_mapping).fillna('Unknown')
            df_['filter_tag'] = tag

    def _print_block(title: str, df_: pd.DataFrame):
        print("\n" + "=" * 60)
        print(f"{title} for {latest_date} → Next Day")
        print("=" * 60)
        if df_.empty:
            print("  [WARN] No stocks met the strict filter criteria today.")
            return
        for i, (_, row) in enumerate(df_.iterrows()):
            prob_str = f"{row['positive_proba']*100:.1f}%"
            cap_str = f"{row['market_cap']/1e8:,.0f}억"
            exp_ret = f"{row['expected_return']*100:.2f}%"
            intra = row.get('intraday_return', np.nan)
            intra_str = "-" if (intra is None or (isinstance(intra, float) and np.isnan(intra))) else f"{intra*100:+.2f}%"
            print(
                f"  {i+1}. {row['code']} {str(row.get('name',''))[:8]:<8} | "
                f"종가: {row['close']:>8,.0f} | "
                f"당일: {intra_str:>7} | "
                f"시총: {cap_str:>7} | "
                f"상승확률: {prob_str:>6} | "
                f"기대수익: {exp_ret:>6}"
            )

    _print_block("🚀 FILTER1 TOP", f1)
    _print_block("🚀 FILTER2 TOP", f2)

    if save_result:
        os.makedirs('ml/predictions', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if not f1.empty:
            f1.to_csv(f'ml/predictions/final_picks_filter1_{timestamp}.csv', index=False, encoding='utf-8-sig')
        if not f2.empty:
            f2.to_csv(f'ml/predictions/final_picks_filter2_{timestamp}.csv', index=False, encoding='utf-8-sig')
        both = pd.concat([f1, f2], ignore_index=True)
        both.to_csv(f'ml/predictions/final_picks_both_{timestamp}.csv', index=False, encoding='utf-8-sig')
        print(f"\n[INFO] Strategic picks saved to ml/predictions/final_picks_*_{timestamp}.csv")

    return {'filter1': f1, 'filter2': f2}


def main(argv: Optional[List[str]] = None):
    """CLI entrypoint.

    Examples:
      - python -m ml.inference
      - python -m ml.inference --filter filter2
      - python -m ml.inference --filter both --top-k 10 --no-save
    """
    parser = argparse.ArgumentParser(description="Run ML inference for next-day picks")
    parser.add_argument(
        "--filter",
        choices=["both", "filter1", "filter2"],
        default="both",
        help="which filter to run (default: both)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="number of picks per filter (default: 5)",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="path to a model file (.cbm for CatBoost, .txt for LightGBM) (default: latest in ml/models)",
    )
    parser.add_argument(
        "--model-name",
        choices=["model1", "model5"],
        default="model1",
        help="named model shortcut (model1: 7-class, model5: LightGBM 2%+ binary)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="do not write CSV outputs under ml/predictions",
    )

    args = parser.parse_args(argv)

    save_result = not args.no_save
    model_name = args.model_name

    if args.filter == "both":
        results = run_inference_both(
            model_path=args.model_path,
            top_k=args.top_k,
            save_result=save_result,
            model_name=model_name,
        )
    elif args.filter == "filter1":
        results = {
            "filter1": run_inference(
                model_path=args.model_path,
                model_name=model_name,
                top_k=args.top_k,
                min_prob_threshold=0.80,
                min_market_cap_krw=50_000_000_000,
                daily_strength_min=-0.05,
                return_1d_min=None,
                upper_lock_cut=None,
                save_result=save_result,
            )
        }
    else:
        results = {
            "filter2": run_inference(
                model_path=args.model_path,
                model_name=model_name,
                top_k=args.top_k,
                min_prob_threshold=0.70,
                min_market_cap_krw=50_000_000_000,
                daily_strength_min=-0.05,
                return_1d_min=-0.05,
                upper_lock_cut=0.295,
                save_result=save_result,
            )
        }

    print("\n[SUCCESS] Strategic inference completed!")
    return results


if __name__ == "__main__":
    main()
