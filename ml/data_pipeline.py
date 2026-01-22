# -*- coding: utf-8 -*-
"""
Data Pipeline - 데이터 로딩 및 피처 엔지니어링
"""
import os
import warnings
from typing import Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
from tqdm import tqdm

from ml.config import CFG

warnings.filterwarnings('ignore')


def load_all_bars(start_date: str, end_date: str) -> pd.DataFrame:
    """
    지정된 기간의 모든 일봉 데이터를 로드
    """
    bars_dir = CFG.bars_dir
    all_data = []
    
    # 날짜 파티션 목록
    partitions = sorted([
        d for d in os.listdir(bars_dir) 
        if d.startswith('date=')
    ])
    
    # 날짜 필터링
    filtered = []
    for p in partitions:
        date_str = p.replace('date=', '')
        if start_date <= date_str <= end_date:
            filtered.append(p)
    
    print(f"[INFO] Loading {len(filtered)} trading days from {start_date} to {end_date}...")
    
    for partition in tqdm(filtered, desc="Loading data"):
        path = os.path.join(bars_dir, partition, 'part-0000.parquet')
        if os.path.exists(path):
            df = pd.read_parquet(path)
            all_data.append(df)
    
    if not all_data:
        raise ValueError("No data found for the specified period")
    
    result = pd.concat(all_data, ignore_index=True)
    
    # 데이터 타입 최적화
    result['date'] = pd.to_datetime(result['date'])
    for col in ['open', 'high', 'low', 'close', 'volume', 'value']:
        result[col] = result[col].astype('float32')
    
    result = result.sort_values(['code', 'date']).reset_index(drop=True)
    print(f"[INFO] Loaded {len(result):,} rows, {result['code'].nunique():,} unique stocks")
    
    return result


def compute_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    종목별로 기술적 지표 계산
    입력: 단일 종목의 시계열 데이터 (date 정렬됨)
    """
    df = df.copy()
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    # ----- 가격 수익률 -----
    df['return_1d'] = close.pct_change(1)
    df['return_5d'] = close.pct_change(5)
    df['return_20d'] = close.pct_change(20)
    
    # ----- 이동평균선 및 이격도 -----
    for w in CFG.ma_windows:
        ma = close.rolling(window=w, min_periods=1).mean()
        df[f'ma_{w}'] = ma
        df[f'ma_{w}_ratio'] = (close / ma - 1).astype('float32')
    
    # ----- RSI -----
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=CFG.rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=CFG.rsi_period).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = (100 - 100 / (1 + rs)).astype('float32')
    
    # ----- MACD -----
    ema_fast = close.ewm(span=CFG.macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=CFG.macd_slow, adjust=False).mean()
    df['macd'] = (ema_fast - ema_slow).astype('float32')
    df['macd_signal'] = df['macd'].ewm(span=CFG.macd_signal, adjust=False).mean().astype('float32')
    df['macd_hist'] = (df['macd'] - df['macd_signal']).astype('float32')
    
    # ----- Bollinger Bands -----
    bb_ma = close.rolling(window=CFG.bollinger_period).mean()
    bb_std = close.rolling(window=CFG.bollinger_period).std()
    bb_upper = bb_ma + 2 * bb_std
    bb_lower = bb_ma - 2 * bb_std
    df['bb_position'] = ((close - bb_lower) / (bb_upper - bb_lower + 1e-10)).astype('float32')
    df['bb_width'] = ((bb_upper - bb_lower) / bb_ma).astype('float32')
    
    # ----- ATR (Average True Range) -----
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=CFG.atr_period).mean().astype('float32')
    df['atr_ratio'] = (df['atr'] / close).astype('float32')
    
    # ----- 거래량 관련 -----
    vol_ma5 = volume.rolling(window=5).mean()
    vol_ma20 = volume.rolling(window=20).mean()
    df['volume_ratio_5d'] = (volume / (vol_ma5 + 1)).astype('float32')
    df['volume_ratio_20d'] = (volume / (vol_ma20 + 1)).astype('float32')
    
    # OBV (On-Balance Volume)
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    df['obv_change'] = obv.pct_change(5).astype('float32')
    
    # ----- 캔들 패턴 -----
    body = close - df['open']
    candle_range = high - low + 1e-10
    df['body_ratio'] = (body / candle_range).astype('float32')
    df['upper_shadow'] = ((high - pd.concat([close, df['open']], axis=1).max(axis=1)) / candle_range).astype('float32')
    df['lower_shadow'] = ((pd.concat([close, df['open']], axis=1).min(axis=1) - low) / candle_range).astype('float32')
    
    # ----- 가격 위치 -----
    high_52w = high.rolling(window=252, min_periods=60).max()
    low_52w = low.rolling(window=252, min_periods=60).min()
    df['price_position_52w'] = ((close - low_52w) / (high_52w - low_52w + 1e-10)).astype('float32')
    
    # ----- 변동성 -----
    df['volatility_20d'] = close.pct_change().rolling(window=20).std().astype('float32')
    
    return df


def create_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    타겟 변수 생성:
    - target: 다음날 수익률 기반 다중 클래스 (model1)
    - target_5d_15p: 5거래일 내 15% 이상 상승 여부 (model4)
    """
    df = df.copy()
    
    # 다음날 종가 수익률 (model1, 2, 3용)
    df['next_return'] = df.groupby('code')['close'].shift(-1) / df['close'] - 1
    
    # model4: 5거래일 내 15% 이상 상승 (t+1 ~ t+5 종가 기준)
    # shift(-5).rolling(5).max()는 t+1, t+2, t+3, t+4, t+5 중 최댓값을 가져옴
    df['max_ret_5d'] = df.groupby('code')['close'].transform(
        lambda x: x.shift(-5).rolling(window=5).max() / x - 1
    )
    df['target_5d_15p'] = (df['max_ret_5d'] >= 0.15).astype(int)

    # 다중 클래스 레이블 생성 (model1)
    df['target'] = pd.cut(
        df['next_return'],
        bins=CFG.target_bins,
        labels=CFG.target_labels,  # 구간 수와 레이블 수 일치
        include_lowest=True
    ).astype('float32')
    
    return df


def process_single_stock(args) -> Optional[pd.DataFrame]:
    """
    단일 종목 처리 (병렬 처리용)
    """
    code, group = args
    try:
        group = group.sort_values('date').reset_index(drop=True)
        if len(group) < 60:  # 최소 60일 데이터 필요
            return None
        result = compute_technical_indicators(group)
        return result
    except Exception as e:
        return None


def build_features(df: pd.DataFrame, parallel: bool = True) -> pd.DataFrame:
    """
    전체 데이터에 대해 피처 엔지니어링 수행
    """
    print("[INFO] Computing technical indicators...")
    
    groups = list(df.groupby('code'))
    results = []
    
    if parallel:
        # 병렬 처리
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = {executor.submit(process_single_stock, g): g[0] for g in groups}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing stocks"):
                result = future.result()
                if result is not None:
                    results.append(result)
    else:
        # 순차 처리
        for g in tqdm(groups, desc="Processing stocks"):
            result = process_single_stock(g)
            if result is not None:
                results.append(result)
    
    if not results:
        raise ValueError("No valid data after feature engineering")
    
    final_df = pd.concat(results, ignore_index=True)
    
    # 타겟 생성
    print("[INFO] Creating target variable...")
    final_df = create_target(final_df)
    
    # NaN 제거
    feature_cols = get_feature_columns()
    final_df = final_df.dropna(subset=feature_cols + ['target'])
    
    print(f"[INFO] Final dataset: {len(final_df):,} rows")
    return final_df


def get_feature_columns() -> list:
    """
    학습에 사용할 피처 컬럼 목록
    """
    features = [
        'return_1d', 'return_5d', 'return_20d',
        'rsi', 'macd', 'macd_signal', 'macd_hist',
        'bb_position', 'bb_width',
        'atr', 'atr_ratio',
        'volume_ratio_5d', 'volume_ratio_20d', 'obv_change',
        'body_ratio', 'upper_shadow', 'lower_shadow',
        'price_position_52w', 'volatility_20d'
    ]
    
    # 이동평균 이격도
    for w in CFG.ma_windows:
        features.append(f'ma_{w}_ratio')
    
    return features


def prepare_train_test_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    학습/테스트 데이터 준비 (캐싱 지원)
    """
    os.makedirs(CFG.feature_dir, exist_ok=True)
    
    train_cache = os.path.join(CFG.feature_dir, 'train_features.parquet')
    test_cache = os.path.join(CFG.feature_dir, 'test_features.parquet')
    
    # 캐시 확인
    if os.path.exists(train_cache) and os.path.exists(test_cache):
        print("[INFO] Loading cached features...")
        train_df = pd.read_parquet(train_cache)
        test_df = pd.read_parquet(test_cache)
        return train_df, test_df
    
    # 전체 데이터 로드 (2000 ~ 2026)
    print("[INFO] Building features from scratch...")
    all_data = load_all_bars(CFG.train_start, CFG.test_end)
    
    # 피처 엔지니어링
    all_data = build_features(all_data, parallel=True)
    
    # 날짜로 분할
    all_data['date_str'] = all_data['date'].dt.strftime('%Y-%m-%d')
    train_df = all_data[all_data['date_str'] <= CFG.train_end].copy()
    test_df = all_data[all_data['date_str'] >= CFG.test_start].copy()
    
    # 캐시 저장
    train_df.to_parquet(train_cache, index=False)
    test_df.to_parquet(test_cache, index=False)
    
    print(f"[INFO] Train: {len(train_df):,} rows, Test: {len(test_df):,} rows")
    
    return train_df, test_df


if __name__ == "__main__":
    # 테스트 실행
    train_df, test_df = prepare_train_test_data()
    print("\nTrain data shape:", train_df.shape)
    print("Test data shape:", test_df.shape)
    print("\nTarget distribution (Train):")
    print(train_df['target'].value_counts().sort_index())
