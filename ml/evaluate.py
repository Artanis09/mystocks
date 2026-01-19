# -*- coding: utf-8 -*-
"""
Evaluation & Backtesting - Top-K 수익률 시뮬레이션
"""
import os
import glob
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from catboost import CatBoostClassifier
from tqdm import tqdm

from ml.config import CFG
from ml.data_pipeline import prepare_train_test_data, get_feature_columns


def load_latest_model() -> Tuple[CatBoostClassifier, str]:
    """
    가장 최근에 학습된 모델 로드
    """
    model_files = glob.glob(os.path.join(CFG.model_dir, 'catboost_*.cbm'))
    if not model_files:
        raise FileNotFoundError("No trained model found. Run train.py first.")
    
    latest_model = max(model_files, key=os.path.getctime)
    model = CatBoostClassifier()
    model.load_model(latest_model)
    print(f"[INFO] Loaded model: {latest_model}")
    
    return model, latest_model


def predict_with_probability(model: CatBoostClassifier, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    예측 및 2% 이상 상승 확률 계산
    """
    # 각 클래스별 확률
    proba = model.predict_proba(X)
    
    # 클래스 1 이상(2% 이상 상승)의 확률 합
    positive_proba = proba[:, CFG.min_positive_class:].sum(axis=1)
    
    # 가중치를 적용한 기대 수익률 (클래스별 중간값 * 확률)
    # 클래스: 0(<2%), 1(2-5%), 2(5-8%), 3(8-12%), 4(12-19%), 5(19-29%), 6(>=29%)
    class_returns = np.array([0.0, 0.035, 0.065, 0.10, 0.155, 0.24, 0.35])
    expected_return = (proba * class_returns).sum(axis=1)
    
    return positive_proba, expected_return


def backtest_topk(
    test_df: pd.DataFrame,
    model: CatBoostClassifier,
    top_k: int = 10,
    min_prob_threshold: float = 0.3
) -> pd.DataFrame:
    """
    Top-K 백테스팅
    매일 상승 확률이 높은 상위 K개 종목을 금일 종가에 매수, 다음날 종가에 매도
    """
    feature_cols = get_feature_columns()
    
    # 날짜별로 그룹화
    test_df = test_df.copy()
    test_df['date_str'] = test_df['date'].dt.strftime('%Y-%m-%d')
    
    dates = sorted(test_df['date_str'].unique())
    
    results = []
    
    print(f"\n[INFO] Backtesting Top-{top_k} strategy...")
    
    for i, date in enumerate(tqdm(dates[:-1], desc="Backtesting")):  # 마지막 날 제외 (다음날 없음)
        day_data = test_df[test_df['date_str'] == date].copy()
        
        if len(day_data) < top_k:
            continue
        
        # 예측
        X = day_data[feature_cols].values
        positive_proba, expected_return = predict_with_probability(model, X)
        
        day_data['positive_proba'] = positive_proba
        day_data['expected_return'] = expected_return
        
        # 확률 임계값 이상인 종목만 필터
        candidates = day_data[day_data['positive_proba'] >= min_prob_threshold]
        
        if len(candidates) < 1:
            # 임계값 충족 종목이 없으면 스킵
            results.append({
                'date': date,
                'n_selected': 0,
                'portfolio_return': 0.0,
                'avg_prob': 0.0
            })
            continue
        
        # 기대 수익률 기준 상위 K개 선택
        top_stocks = candidates.nlargest(min(top_k, len(candidates)), 'expected_return')
        
        # 실제 다음날 수익률 계산 (next_return은 이미 계산되어 있음)
        actual_returns = top_stocks['next_return'].values
        valid_returns = actual_returns[~np.isnan(actual_returns)]
        
        if len(valid_returns) == 0:
            continue
        
        # 동일 비중 포트폴리오 수익률
        portfolio_return = valid_returns.mean()
        
        results.append({
            'date': date,
            'n_selected': len(valid_returns),
            'portfolio_return': portfolio_return,
            'avg_prob': top_stocks['positive_proba'].mean(),
            'avg_expected_return': top_stocks['expected_return'].mean(),
            'hit_rate': (valid_returns >= 0.02).mean(),  # 2% 이상 상승 적중률
            'selected_codes': top_stocks['code'].tolist()
        })
    
    return pd.DataFrame(results)


def calculate_cumulative_returns(backtest_results: pd.DataFrame) -> pd.DataFrame:
    """
    누적 수익률 계산
    """
    df = backtest_results.copy()
    
    # 일별 수익률을 누적 (복리)
    df['cumulative_return'] = (1 + df['portfolio_return']).cumprod()
    
    # 벤치마크 (Buy & Hold 코스피) - 여기서는 일별 평균 수익률 사용
    df['cumulative_return_no_compound'] = 1 + df['portfolio_return'].cumsum()
    
    return df


def evaluate_strategy(backtest_results: pd.DataFrame, top_k: int) -> Dict:
    """
    전략 성과 평가 지표 계산
    """
    df = backtest_results[backtest_results['n_selected'] > 0].copy()
    
    if len(df) == 0:
        return {}
    
    returns = df['portfolio_return'].values
    
    # 누적 수익률
    cumulative = (1 + returns).prod() - 1
    
    # 연환산 수익률 (CAGR)
    n_days = len(df)
    cagr = (1 + cumulative) ** (252 / n_days) - 1 if n_days > 0 else 0
    
    # 샤프 비율 (무위험 수익률 3% 가정)
    excess_returns = returns - 0.03 / 252
    sharpe = np.sqrt(252) * excess_returns.mean() / (excess_returns.std() + 1e-10)
    
    # 최대 낙폭 (MDD)
    cum_returns = (1 + returns).cumprod()
    peak = np.maximum.accumulate(cum_returns)
    drawdown = (cum_returns - peak) / peak
    mdd = drawdown.min() if len(drawdown) > 0 else 0
    
    # 승률
    win_rate = (returns > 0).mean()
    
    # 2% 이상 상승 적중률
    hit_rate = df['hit_rate'].mean() if 'hit_rate' in df.columns else 0
    
    metrics = {
        'top_k': top_k,
        'total_trading_days': len(df),
        'cumulative_return': cumulative,
        'cagr': cagr,
        'sharpe_ratio': sharpe,
        'max_drawdown': mdd,
        'win_rate': win_rate,
        'avg_daily_return': returns.mean(),
        'daily_volatility': returns.std(),
        'avg_hit_rate': hit_rate,
        'avg_selected': df['n_selected'].mean()
    }
    
    return metrics


def plot_results(backtest_results: pd.DataFrame, metrics: Dict, save_path: str = None):
    """
    백테스팅 결과 시각화
    """
    df = calculate_cumulative_returns(backtest_results)
    df = df[df['n_selected'] > 0]
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    
    # 1. 누적 수익률
    ax1 = axes[0]
    ax1.plot(range(len(df)), df['cumulative_return'], 'b-', linewidth=1.5, label='Cumulative Return')
    ax1.axhline(y=1, color='gray', linestyle='--', alpha=0.5)
    ax1.set_title(f"Top-{metrics['top_k']} Strategy Cumulative Return", fontsize=14)
    ax1.set_ylabel('Cumulative Return')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 일별 수익률 분포
    ax2 = axes[1]
    ax2.bar(range(len(df)), df['portfolio_return'] * 100, 
            color=['green' if r > 0 else 'red' for r in df['portfolio_return']], alpha=0.7)
    ax2.axhline(y=0, color='black', linewidth=0.5)
    ax2.set_title('Daily Portfolio Return (%)', fontsize=14)
    ax2.set_ylabel('Return (%)')
    ax2.grid(True, alpha=0.3)
    
    # 3. 적중률 추이
    ax3 = axes[2]
    if 'hit_rate' in df.columns:
        rolling_hit = df['hit_rate'].rolling(window=20, min_periods=1).mean()
        ax3.plot(range(len(df)), rolling_hit * 100, 'purple', linewidth=1.5, label='20-day Rolling Hit Rate')
        ax3.axhline(y=50, color='gray', linestyle='--', alpha=0.5)
    ax3.set_title('Hit Rate (>=2% Rise Accuracy)', fontsize=14)
    ax3.set_ylabel('Hit Rate (%)')
    ax3.set_xlabel('Trading Days')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"[INFO] Plot saved to {save_path}")
    
    plt.show()


def main():
    """
    메인 평가 함수
    """
    import argparse
    parser = argparse.ArgumentParser(description='Backtesting Evaluation')
    parser.add_argument('--top-k', type=int, default=None, help='Top-K stocks to select')
    parser.add_argument('--min-prob', type=float, default=0.3, help='Minimum probability threshold')
    args = parser.parse_args()

    print("=" * 60)
    print("Stock Price Prediction - Backtesting & Evaluation")
    print("=" * 60)
    
    # 데이터 및 모델 로드
    _, test_df = prepare_train_test_data()
    model, model_path = load_latest_model()
    
    # 평가 대상 Top-K 리스트 결정
    top_k_list = [args.top_k] if args.top_k is not None else CFG.top_k_list
    min_prob = args.min_prob
    
    all_metrics = []
    
    for top_k in top_k_list:
        print(f"\n{'='*40}")
        print(f"Evaluating Top-{top_k} Strategy (Min Prob: {min_prob})")
        print('='*40)
        
        # 백테스팅 실행
        backtest_results = backtest_topk(test_df, model, top_k=top_k, min_prob_threshold=min_prob)
        
        # 성과 평가
        metrics = evaluate_strategy(backtest_results, top_k)
        all_metrics.append(metrics)
        
        # 결과 출력
        print(f"\n[Results for Top-{top_k}]")
        print(f"  Total Trading Days: {metrics.get('total_trading_days', 0)}")
        print(f"  Cumulative Return: {metrics.get('cumulative_return', 0)*100:.2f}%")
        print(f"  CAGR: {metrics.get('cagr', 0)*100:.2f}%")
        print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.3f}")
        print(f"  Max Drawdown: {metrics.get('max_drawdown', 0)*100:.2f}%")
        print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.2f}%")
        print(f"  Avg Hit Rate (>=2%): {metrics.get('avg_hit_rate', 0)*100:.2f}%")
        
        # 시각화 (Top-K가 지정되었거나 Top-10인 경우)
        if args.top_k is not None or top_k == 10:
            suffix = f"_backtest_top{top_k}_p{int(min_prob*100)}"
            plot_path = model_path.replace('.cbm', f'{suffix}.png')
            plot_results(backtest_results, metrics, save_path=plot_path)
            
            # 백테스팅 상세 결과 저장
            result_path = model_path.replace('.cbm', f'{suffix}.csv')
            backtest_results.to_csv(result_path, index=False)
            print(f"[INFO] Backtest results saved to {result_path}")
    
    # 전체 비교 테이블
    print("\n" + "=" * 60)
    print("Strategy Comparison Summary")
    print("=" * 60)
    
    comparison_df = pd.DataFrame(all_metrics)
    print(comparison_df.to_string(index=False))
    
    # 비교 테이블 저장
    comparison_path = os.path.join(CFG.model_dir, 'strategy_comparison.csv')
    comparison_df.to_csv(comparison_path, index=False)
    print(f"\n[INFO] Comparison saved to {comparison_path}")


if __name__ == "__main__":
    main()
