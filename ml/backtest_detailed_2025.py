
import pandas as pd
import numpy as np
import os
from tqdm import tqdm
from datetime import datetime
from ml.config import CFG
from ml.data_pipeline import prepare_train_test_data, get_feature_columns
from ml.evaluate import load_latest_model, predict_with_probability

def generate_detailed_backtest_report(start_assets=1_000_000, min_prob=0.8, top_k=5):
    print("=" * 60)
    print(f"Generating Detailed Backtest Report (2025)")
    print(f"Initial Assets: {start_assets:,} KRW")
    print(f"Strategy: Top-{top_k}, Min Prob: {min_prob}")
    print("=" * 60)

    # 1. Load Data & Model
    _, test_df = prepare_train_test_data()
    model, model_path = load_latest_model()
    
    # Stock name mapping
    try:
        stocks_info = pd.read_csv('public/korea_stocks.csv')
        # Handle code formatting (ensure 6 digits)
        stocks_info['단축코드'] = stocks_info['단축코드'].apply(lambda x: str(x).zfill(6))
        code_to_name = dict(zip(stocks_info['단축코드'], stocks_info['한글 종목약명']))
    except:
        code_to_name = {}

    # Filter for 2025
    test_df['date_str'] = test_df['date'].dt.strftime('%Y-%m-%d')
    dates = sorted(test_df['date_str'].unique())
    dates_2025 = [d for d in dates if d.startswith('2025')]
    
    if not dates_2025:
        # If no dates found in 2025, use the last 250 available days
        print("[WARN] No 2025 data found. Using last 250 days instead.")
        dates_2025 = dates[-251:] 

    feature_cols = get_feature_columns()
    current_assets = start_assets
    report_data = []

    for i, date in enumerate(tqdm(dates_2025[:-1], desc="Simulating 2025")):
        day_data = test_df[test_df['date_str'] == date].copy()
        if len(day_data) == 0: continue

        # Predict
        X = day_data[feature_cols].values
        positive_proba, expected_return = predict_with_probability(model, X)
        
        day_data['prob'] = positive_proba
        day_data['expected_return'] = expected_return
        
        # Filter and Select
        candidates = day_data[day_data['prob'] >= min_prob]
        if len(candidates) == 0:
            # No trades today
            report_data.append({
                'Date': date,
                'Stock_Code': 'CASH',
                'Stock_Name': '현금보유',
                'Buy_Price': 0,
                'Sell_Price': 0,
                'Return': 0.0,
                'Daily_Return': 0.0,
                'Total_Assets': current_assets
            })
            continue
            
        top_stocks = candidates.nlargest(min(top_k, len(candidates)), 'expected_return')
        
        # Calculate daily return
        actual_returns = top_stocks['next_return'].values
        daily_return = np.mean(actual_returns)
        
        # Update assets
        prev_assets = current_assets
        current_assets = prev_assets * (1 + daily_return)
        
        # Log each stock in selection
        for _, row in top_stocks.iterrows():
            code = row['code']
            name = code_to_name.get(code, code)
            buy_price = row['close']
            # next_return = (next_close / close) - 1 => next_close = close * (1 + next_return)
            sell_price = buy_price * (1 + row['next_return'])
            
            report_data.append({
                'Date': date,
                'Stock_Code': f"'{code}", # Excel safety
                'Stock_Name': name,
                'Buy_Price': int(buy_price),
                'Sell_Price': int(sell_price),
                'Return': round(row['next_return'], 4),
                'Daily_Return': round(daily_return, 4),
                'Total_Assets': int(current_assets)
            })

    # Save to CSV
    report_df = pd.DataFrame(report_data)
    os.makedirs('ml/results', exist_ok=True)
    report_path = 'ml/results/backtest_2025_detailed.csv'
    report_df.to_csv(report_path, index=False, encoding='utf-8-sig')
    
    print(f"\n[SUCCESS] Detailed report saved to: {report_path}")
    print(f"Final Assets: {current_assets:,.0f} KRW")
    return report_path

if __name__ == "__main__":
    generate_detailed_backtest_report()
