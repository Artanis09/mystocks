# -*- coding: utf-8 -*-
"""
Training Script - CatBoost 모델 학습
"""
import argparse
import os
import json
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.model_selection import train_test_split

from ml.config import CFG
from ml.data_pipeline import prepare_train_test_data, get_feature_columns


def train_model(train_df: pd.DataFrame, save_path: str = None, model_name: str = "model1") -> CatBoostClassifier:
    """CatBoost 모델 학습 (model1: 7-class 다중분류)."""

    feature_cols = get_feature_columns()

    df = train_df.copy()
    df['year'] = df['date'].dt.year

    if model_name != "model1":
        raise ValueError("Only model1 training is supported. For model5, use ml/train_model5_lgbm.py")

    target_col = 'target'
    params = CFG.catboost_params
    class_names = ['<2%', '2-5%', '5-8%', '8-12%', '12-19%', '19-29%', '>=29%']

    train_mask = df['year'] < 2024
    val_mask = df['year'] == 2024

    X_train = df.loc[train_mask, feature_cols].values
    y_train = df.loc[train_mask, target_col].values.astype(int)
    X_val = df.loc[val_mask, feature_cols].values
    y_val = df.loc[val_mask, target_col].values.astype(int)

    print(f"[INFO] Training set: {len(X_train):,} samples")
    print(f"[INFO] Validation set: {len(X_val):,} samples")
    print(f"[INFO] Number of features: {len(feature_cols)}")

    # 클래스 분포 확인
    print("\n[INFO] Class distribution (Train):")
    unique, counts = np.unique(y_train, return_counts=True)
    for u, c in zip(unique, counts):
        print(f"  Class {u}: {c:,} ({c/len(y_train)*100:.2f}%)")

    # CatBoost Pool 생성
    train_pool = Pool(X_train, y_train, feature_names=feature_cols)
    val_pool = Pool(X_val, y_val, feature_names=feature_cols)

    # 모델 학습
    print("\n[INFO] Starting training...")
    model = CatBoostClassifier(**params)

    model.fit(
        train_pool,
        eval_set=val_pool,
        use_best_model=True,
        plot=False
    )

    # 모델 저장
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        model.save_model(save_path)
        print(f"\n[INFO] Model saved to {save_path}")

        # 피처 중요도 저장
        importance = model.get_feature_importance()
        importance_df = pd.DataFrame({
            'feature': feature_cols,
            'importance': importance
        }).sort_values('importance', ascending=False)

        importance_path = save_path.replace('.cbm', '_feature_importance.csv')
        importance_df.to_csv(importance_path, index=False)
        print(f"[INFO] Feature importance saved to {importance_path}")

        # 메타데이터 저장
        meta = {
            'train_date': datetime.now().isoformat(),
            'train_samples': int(len(X_train)),
            'val_samples': int(len(X_val)),
            'features': feature_cols,
            'best_iteration': model.get_best_iteration(),
            'class_names': class_names,
            'target': target_col,
            'model_name': model_name,
        }
        if model_name == "model1":
            meta['target_bins'] = CFG.target_bins
        meta_path = save_path.replace('.cbm', '_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    return model


def main(argv=None):
    """메인 학습 함수 (model1: 7-class)."""
    parser = argparse.ArgumentParser(description="Train CatBoost model")
    parser.add_argument(
        "--model-name",
        choices=["model1"],
        default="model1",
        help="model1: 7-class",
    )
    args = parser.parse_args(argv)

    model_name = args.model_name

    print("=" * 60)
    print(f"Stock Price Prediction - Model Training ({model_name})")
    print("=" * 60)

    # 데이터 준비
    train_df, test_df = prepare_train_test_data()

    # 모델 저장 경로
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_path = os.path.join(CFG.model_dir, f'catboost_{timestamp}.cbm')

    # 학습
    model = train_model(train_df, save_path=model_path, model_name=model_name)

    # 검증 세트 성능 출력
    feature_cols = get_feature_columns()
    train_df['year'] = train_df['date'].dt.year
    val_mask = train_df['year'] == 2024
    X_val = train_df.loc[val_mask, feature_cols].values
    
    y_val = train_df.loc[val_mask, 'target'].values.astype(int)
    predictions = model.predict(X_val)
    accuracy = (predictions.flatten() == y_val).mean()
    print(f"\n[INFO] Validation Accuracy: {accuracy:.4f}")

    pred_positive = predictions.flatten() >= CFG.min_positive_class
    true_positive = y_val >= CFG.min_positive_class
    if pred_positive.sum() > 0:
        precision = (pred_positive & true_positive).sum() / pred_positive.sum()
        print(f"[INFO] Precision (>=2% rise): {precision:.4f}")

    print("\n[INFO] Training completed!")
    return model


if __name__ == "__main__":
    main()
