# -*- coding: utf-8 -*-
"""Train Model5 with LightGBM.

Model5 target (binary):
- Buy at day t close.
- Positive if either next-day open OR next-day close is >= +2% vs buy close.

Train: 2000-01-01 ~ 2024-12-31 (cached features via prepare_train_test_data)
Validation: year == 2024

Outputs:
- ml/models/lgbm_model5_YYYYmmdd_HHMMSS.txt
- ml/models/lgbm_model5_YYYYmmdd_HHMMSS_meta.json
"""

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from ml.config import CFG
from ml.data_pipeline import prepare_train_test_data, get_feature_columns


def add_model5_target(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])

    # next-day prices
    df['next_open'] = df.groupby('code')['open'].shift(-1)
    df['next_close'] = df.groupby('code')['close'].shift(-1)

    base = df['close']
    df['next_open_return'] = df['next_open'] / base - 1
    df['next_close_return'] = df['next_close'] / base - 1

    # Korea equities daily limit is around +/-30%.
    # Treat beyond this range as invalid for this strategy (auction/limit situations or bad data).
    lo, hi = -0.30, 0.295
    bad = (
        (df['next_open_return'] < lo) | (df['next_open_return'] > hi) |
        (df['next_close_return'] < lo) | (df['next_close_return'] > hi)
    )
    df.loc[bad, ['next_open_return', 'next_close_return']] = np.nan

    df['target_model5'] = (
        np.maximum(df['next_open_return'], df['next_close_return']) >= 0.02
    ).astype(int)

    return df


def train_model5() -> Tuple[str, Dict]:
    try:
        import lightgbm as lgb
    except Exception as e:
        raise RuntimeError("LightGBM is required. Install with `pip install lightgbm`.") from e

    print("[INFO] Loading cached features...")
    train_df, _ = prepare_train_test_data()

    feature_cols = get_feature_columns()

    df = add_model5_target(train_df)
    df['year'] = df['date'].dt.year

    # split
    train_mask = df['year'] < 2024
    val_mask = df['year'] == 2024

    # drop rows where next-day returns are invalid
    df = df.dropna(subset=['target_model5']).copy()
    train_mask = df['year'] < 2024
    val_mask = df['year'] == 2024

    X_train = df.loc[train_mask, feature_cols]
    y_train = df.loc[train_mask, 'target_model5']
    X_val = df.loc[val_mask, feature_cols]
    y_val = df.loc[val_mask, 'target_model5']

    print(f"[INFO] Training set: {len(X_train):,}")
    print(f"[INFO] Validation set: {len(X_val):,}")

    pos = int(y_train.sum())
    neg = int((y_train == 0).sum())
    print(f"[INFO] Target distribution (train) pos={pos:,} ({pos/len(y_train)*100:.2f}%), neg={neg:,}")

    # imbalance
    scale_pos_weight = (neg / max(pos, 1))

    params = dict(
        objective='binary',
        boosting_type='gbdt',
        learning_rate=0.05,
        n_estimators=2000,
        num_leaves=63,
        max_depth=-1,
        min_child_samples=50,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        n_jobs=-1,
        force_col_wise=True,
        random_state=42,
        scale_pos_weight=scale_pos_weight,
    )

    model = lgb.LGBMClassifier(**params)

    print("[INFO] Training LightGBM...")
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        eval_metric='auc',
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=True, first_metric_only=True),
            lgb.log_evaluation(period=100),
        ],
    )

    # metrics
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, accuracy_score

    proba = model.predict_proba(X_val)[:, 1]
    auc = float(roc_auc_score(y_val, proba))

    preds_05 = (proba >= 0.5).astype(int)
    acc_05 = float(accuracy_score(y_val, preds_05))
    prec_05 = float(precision_score(y_val, preds_05, zero_division=0))
    rec_05 = float(recall_score(y_val, preds_05, zero_division=0))

    # Choose a practical threshold by maximizing F1 on validation (coarse sweep)
    best_thr = 0.5
    best_f1 = -1.0
    for thr in np.linspace(0.05, 0.50, 46):
        preds = (proba >= thr).astype(int)
        p = precision_score(y_val, preds, zero_division=0)
        r = recall_score(y_val, preds, zero_division=0)
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = float(f1)
            best_thr = float(thr)

    preds_best = (proba >= best_thr).astype(int)
    acc_best = float(accuracy_score(y_val, preds_best))
    prec_best = float(precision_score(y_val, preds_best, zero_division=0))
    rec_best = float(recall_score(y_val, preds_best, zero_division=0))

    metrics = {
        'auc': auc,
        'best_iteration': int(getattr(model, 'best_iteration_', model.n_estimators)),
        'scale_pos_weight': float(scale_pos_weight),
        'thr_0.50': {
            'accuracy': acc_05,
            'precision': prec_05,
            'recall': rec_05,
        },
        'thr_best_f1': {
            'threshold': best_thr,
            'f1': best_f1,
            'accuracy': acc_best,
            'precision': prec_best,
            'recall': rec_best,
        },
    }

    print("[RESULT] Validation")
    print(f"  auc: {metrics['auc']:.4f}")
    print(f"  best_iteration: {metrics['best_iteration']}")
    print(f"  scale_pos_weight: {metrics['scale_pos_weight']:.4f}")
    t05 = metrics['thr_0.50']
    print(f"  thr=0.50 accuracy={t05['accuracy']:.4f} precision={t05['precision']:.4f} recall={t05['recall']:.4f}")
    tb = metrics['thr_best_f1']
    print(
        f"  thr(best_f1)={tb['threshold']:.2f} f1={tb['f1']:.4f} accuracy={tb['accuracy']:.4f} "
        f"precision={tb['precision']:.4f} recall={tb['recall']:.4f}"
    )

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = CFG.model_dir
    os.makedirs(out_dir, exist_ok=True)

    model_path = os.path.join(out_dir, f"lgbm_model5_{timestamp}.txt")
    model.booster_.save_model(model_path)

    meta = {
        'train_date': datetime.now().isoformat(),
        'model_name': 'model5',
        'library': 'lightgbm',
        'train_samples': int(len(X_train)),
        'val_samples': int(len(X_val)),
        'features': feature_cols,
        'target': 'target_model5',
        'definition': 'max(next_open_return,next_close_return) >= 0.02',
        'train_end': CFG.train_end,
        'val_year': 2024,
        'params': params,
        'metrics': metrics,
    }
    meta_path = model_path.replace('.txt', '_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Model saved: {model_path}")
    print(f"[INFO] Meta saved: {meta_path}")

    return model_path, meta


def main():
    print("=" * 60)
    print("Model5 Training (LightGBM)")
    print("Target: next-day open OR close >= +2% vs buy close")
    print("=" * 60)
    train_model5()


if __name__ == '__main__':
    main()
