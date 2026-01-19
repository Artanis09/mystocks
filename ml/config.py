# -*- coding: utf-8 -*-
"""
ML Configuration - 학습 관련 설정
"""
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class MLConfig:
    # 데이터 경로
    bars_dir: str = "data/krx/bars"
    model_dir: str = "ml/models"
    feature_dir: str = "ml/features"
    
    # 기간 설정
    train_start: str = "2000-01-01"
    train_end: str = "2024-12-31"
    test_start: str = "2025-01-01"
    test_end: str = "2026-12-31"
    
    # 타겟 클래스 정의 (상승률 구간)
    # 0: < 2%, 1: 2~5%, 2: 5~8%, 3: 8~12%, 4: 12~19%, 5: 19~29%, 6: >= 29%
    target_bins: List[float] = field(default_factory=lambda: [
        -float('inf'), 0.02, 0.05, 0.08, 0.12, 0.19, 0.29, float('inf')
    ])
    target_labels: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 7 bins -> 7 labels
    
    # 2% 이상 상승으로 간주할 최소 클래스
    min_positive_class: int = 1
    
    # 피처 윈도우 설정
    ma_windows: List[int] = field(default_factory=lambda: [5, 10, 20, 60, 120])
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    atr_period: int = 14
    
    # 모델 설정
    catboost_params: dict = field(default_factory=lambda: {
        'iterations': 1000,
        'learning_rate': 0.05,
        'depth': 8,
        'loss_function': 'MultiClass',
        'eval_metric': 'MultiClass',
        'random_seed': 42,
        'verbose': 100,
        'early_stopping_rounds': 50,
        'task_type': 'CPU',  # GPU 가능시 'GPU'
        'class_weights': [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0]  # 희귀 클래스에 높은 가중치
    })
    
    # 평가 설정
    top_k_list: List[int] = field(default_factory=lambda: [5, 10, 20, 50])
    initial_capital: float = 100_000_000  # 1억원


CFG = MLConfig()
