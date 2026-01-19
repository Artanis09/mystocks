# -*- coding: utf-8 -*-
"""
Run All - 전체 ML 파이프라인 실행
1. 데이터 전처리 및 피처 엔지니어링
2. 모델 학습
3. 백테스팅 및 평가
4. 추론 (다음 날 예측)
"""
import os
import sys
import argparse
from datetime import datetime

def run_pipeline(steps: list = None):
    """
    전체 또는 선택된 단계 실행
    
    Args:
        steps: ['data', 'train', 'evaluate', 'inference'] 중 선택
               None이면 전체 실행
    """
    if steps is None:
        steps = ['data', 'train', 'evaluate', 'inference']
    
    print("\n" + "=" * 70)
    print("🚀 Stock Price Prediction ML Pipeline")
    print(f"   Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Steps: {', '.join(steps)}")
    print("=" * 70)
    
    # Step 1: 데이터 준비
    if 'data' in steps:
        print("\n" + "-" * 50)
        print("📊 Step 1: Data Preparation & Feature Engineering")
        print("-" * 50)
        from ml.data_pipeline import prepare_train_test_data
        train_df, test_df = prepare_train_test_data()
        print(f"✅ Data prepared: Train={len(train_df):,}, Test={len(test_df):,}")
    
    # Step 2: 모델 학습
    if 'train' in steps:
        print("\n" + "-" * 50)
        print("🎯 Step 2: Model Training")
        print("-" * 50)
        from ml.train import main as train_main
        model = train_main()
        print("✅ Model training completed")
    
    # Step 3: 백테스팅
    if 'evaluate' in steps:
        print("\n" + "-" * 50)
        print("📈 Step 3: Backtesting & Evaluation")
        print("-" * 50)
        from ml.evaluate import main as evaluate_main
        evaluate_main()
        print("✅ Evaluation completed")
    
    # Step 4: 추론
    if 'inference' in steps:
        print("\n" + "-" * 50)
        print("🔮 Step 4: Inference (Next Day Prediction)")
        print("-" * 50)
        from ml.inference import main as inference_main
        predictions = inference_main()
        print("✅ Inference completed")
    
    print("\n" + "=" * 70)
    print("🎉 Pipeline Completed!")
    print(f"   Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Stock Prediction ML Pipeline')
    parser.add_argument(
        '--steps', 
        nargs='+', 
        choices=['data', 'train', 'evaluate', 'inference'],
        help='Steps to run (default: all)'
    )
    parser.add_argument(
        '--train-only',
        action='store_true',
        help='Run only training (data + train)'
    )
    parser.add_argument(
        '--predict-only',
        action='store_true',
        help='Run only inference'
    )
    
    args = parser.parse_args()
    
    if args.train_only:
        steps = ['data', 'train']
    elif args.predict_only:
        steps = ['inference']
    else:
        steps = args.steps
    
    run_pipeline(steps)


if __name__ == "__main__":
    main()
