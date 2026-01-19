# -*- coding: utf-8 -*-
"""
Inference - 실시간 예측 및 추천 종목 생성
"""
import os
import glob
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from ml.config import CFG
from ml.data_pipeline import load_all_bars, compute_technical_indicators, get_feature_columns


def load_model(model_path: str = None) -> Tuple[CatBoostClassifier, dict]:
    """
    학습된 모델 로드
    """
    if model_path is None:
        # 가장 최근 모델 로드
        model_files = glob.glob(os.path.join(CFG.model_dir, 'catboost_*.cbm'))
        if not model_files:
            raise FileNotFoundError("No trained model found. Run train.py first.")
        model_path = max(model_files, key=os.path.getctime)
    
    model = CatBoostClassifier()
    model.load_model(model_path)
    
    # 메타데이터 로드
    meta_path = model_path.replace('.cbm', '_meta.json')
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
    model: CatBoostClassifier,
    df: pd.DataFrame,
    top_k: int = 5,
    min_prob_threshold: float = 0.8
) -> pd.DataFrame:
    """
    다음 날 상승 예측 - 최종 필터 조건 적용
    1. 확률 >= 80% (기본값)
    2. 시가총액 >= 500억
    3. 당일 시가 대비 종가 변동률 > -5%
    """
    feature_cols = get_feature_columns()
    
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
        df['market_cap'] = 1e12  # 정보 없으면 패스 (1조 가정)
    
    # 2. 피처 추출 및 예측
    X = df[feature_cols].values
    proba = model.predict_proba(X)
    
    # 2% 이상 상승 확률 (클래스 1 이상의 합)
    positive_proba = proba[:, CFG.min_positive_class:].sum(axis=1)
    
    # 가중치를 적용한 기대 수익률
    class_returns = np.array([0.0, 0.035, 0.065, 0.10, 0.155, 0.24, 0.35])
    expected_return = (proba * class_returns).sum(axis=1)
    
    # 결과 DataFrame 생성
    result = df[['date', 'code', 'close', 'open', 'market_cap']].copy()
    result['positive_proba'] = positive_proba
    result['expected_return'] = expected_return
    
    # 3. 최종 필터 적용
    # 3.1 확률 임계값 (기본 80%)
    mask = (result['positive_proba'] >= min_prob_threshold)
    # 3.2 시가총액 500억 이상
    mask &= (result['market_cap'] >= 50_000_000_000)
    # 3.3 당일 시가 대비 종가 변동률 -5% 이상 (장대음봉 제외)
    day_change = (result['close'] - result['open']) / result['open']
    mask &= (day_change > -0.05)
    
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
    min_prob_threshold: float = 0.8,
    save_result: bool = True
) -> pd.DataFrame:
    """
    전체 추론 파이프라인 실행
    """
    print("=" * 60)
    print("Stock Price Prediction - Inference (Final Strategic Filter)")
    print(f"Condition: Top-{top_k}, Prob >= {min_prob_threshold*100}%, Cap >= 50B, Daily > -5%")
    print("=" * 60)
    
    # 모델 로드
    model, meta = load_model(model_path)
    
    # 최근 데이터 로드
    print("\n[INFO] Loading recent data...")
    recent_data = get_recent_data(lookback_days=300)
    latest_date = recent_data['date'].max().strftime('%Y-%m-%d')
    print(f"[INFO] Latest data date: {latest_date}")
    
    # 피처 준비
    print("[INFO] Preparing features...")
    inference_data = prepare_inference_features(recent_data)
    print(f"[INFO] {len(inference_data)} stocks ready for prediction")
    
    # 예측
    print(f"[INFO] Running Filtered Prediction...")
    predictions = predict_next_day(
        model, 
        inference_data, 
        top_k=top_k,
        min_prob_threshold=min_prob_threshold
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
            print(f"  {i+1}. {row['code']} {row['name'][:8]:<8} | "
                  f"종가: {row['close']:>8,.0f} | "
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


def main():
    """
    메인 실행 함수 (최종 전략 조건 기본값 설정)
    """
    predictions = run_inference(
        top_k=5,            # 최종 전략: 상위 5개
        min_prob_threshold=0.8,  # 최종 전략: 80% 이상
        save_result=True
    )
    
    print("\n[SUCCESS] Strategic inference completed!")
    
    return predictions


if __name__ == "__main__":
    main()
