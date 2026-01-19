
import pandas as pd
import numpy as np
import os
from tqdm import tqdm
from ml.config import MLConfig
from ml.data_pipeline import prepare_train_test_data, get_feature_columns
from ml.evaluate import load_latest_model, predict_with_probability

def generate_marketcap_backtest_report(start_assets=1_000_000, min_prob=0.8, top_k=5, min_market_cap=50_000_000_000):
    CFG = MLConfig()
    print("=" * 60)
    print(f"Generating MarketCap Backtest Report (2025)")
    print(f"Filter: Market Cap >= {min_market_cap/1e8:.0f} Okgwon (50B KRW)")
    print(f"Initial Assets: {start_assets:,} KRW")
    print(f"Strategy: Top-{top_k}, Min Prob: {min_prob}")
    print("=" * 60)

    # 1. Load Data & Model
    _, test_df = prepare_train_test_data()
    model, model_path = load_latest_model()
    
    # 2. Stock Info (Name & Share Count)
    try:
        stocks_info = pd.read_csv('public/korea_stocks.csv')
        stocks_info['단축코드'] = stocks_info['단축코드'].apply(lambda x: str(x).zfill(6))
        code_to_name = dict(zip(stocks_info['단축코드'], stocks_info['한글 종목약명']))
        code_to_shares = dict(zip(stocks_info['단축코드'], stocks_info['상장주식수']))
    except Exception as e:
        print(f"[ERROR] Failed to load stock info: {e}")
        return

    # Add share count to test_df for filtering
    test_df['shares'] = test_df['code'].map(code_to_shares).fillna(0)
    test_df['market_cap'] = test_df['close'] * test_df['shares']

    # Filter for 2025
    test_df['date_str'] = test_df['date'].dt.strftime('%Y-%m-%d')
    dates = sorted(test_df['date_str'].unique())
    dates_2025 = [d for d in dates if d.startswith('2025')]
    
    if not dates_2025:
        print("[WARN] No 2025 data found. Using last available data.")
        dates_2025 = dates[-251:] 

    feature_cols = get_feature_columns()
    current_assets = start_assets
    report_data = []

    for i, date in enumerate(tqdm(dates_2025[:-1], desc="Simulating 2025 (Cap > 50B)")):
        day_data = test_df[test_df['date_str'] == date].copy()
        if len(day_data) == 0: continue

        # Apply Filters BEFORE selection:
        # 1. Market Cap >= 50B
        # 2. Daily Price Change from Open > -5% (Avoid "Falling Knives" or Data Errors)
        day_data['change_from_open'] = (day_data['close'] - day_data['open']) / day_data['open']
        day_data = day_data[
            (day_data['market_cap'] >= min_market_cap) & 
            (day_data['change_from_open'] > -0.05)
        ]

        if len(day_data) == 0:
            report_data.append({
                'Date': date, 'Stock_Code': 'CASH', 'Stock_Name': '현금보유',
                'Buy_Price': 0, 'Sell_Price': 0, 'Return': 0.0, 'Daily_Return': 0.0, 'Total_Assets': current_assets
            })
            continue

        # Predict
        X = day_data[feature_cols].values
        positive_proba, expected_return = predict_with_probability(model, X)
        
        day_data['prob'] = positive_proba
        day_data['expected_return'] = expected_return
        
        # Filter Probability and Select Top K
        candidates = day_data[day_data['prob'] >= min_prob]
        if len(candidates) == 0:
            report_data.append({
                'Date': date, 'Stock_Code': 'CASH', 'Stock_Name': '현금보유',
                'Buy_Price': 0, 'Sell_Price': 0, 'Return': 0.0, 'Daily_Return': 0.0, 'Total_Assets': current_assets
            })
            continue
            
        top_stocks = candidates.nlargest(min(top_k, len(candidates)), 'expected_return')
        
        # Calculate daily return (1/N)
        actual_returns = top_stocks['next_return'].values
        daily_return = np.mean(actual_returns)
        
        # Update assets
        prev_assets = current_assets
        current_assets = prev_assets * (1 + daily_return)
        
        # Log details
        for _, row in top_stocks.iterrows():
            code = row['code']
            name = code_to_name.get(code, code)
            report_data.append({
                'Date': date,
                'Stock_Code': f"'{code}",
                'Stock_Name': name,
                'Prediction_Strength': f"{row['prob']*100:.1f}%",
                'Buy_Price': int(row['close']),
                'Sell_Price': int(row['close'] * (1 + row['next_return'])),
                'Return': round(row['next_return'], 4),
                'Daily_Return': round(daily_return, 4),
                'Market_Cap': int(row['market_cap']),
                'Total_Assets': int(current_assets)
            })

    # Save to CSV
    report_df = pd.DataFrame(report_data)
    os.makedirs('ml/results', exist_ok=True)
    report_path = 'ml/results/backtest_2025_filtered_final.csv'
    report_df.to_csv(report_path, index=False, encoding='utf-8-sig')
    
    print(f"\n[SUCCESS] Report saved to: {report_path}")
    print(f"Final Assets: {current_assets:,.0f} KRW")
    return report_path

if __name__ == "__main__":
    generate_marketcap_backtest_report()
