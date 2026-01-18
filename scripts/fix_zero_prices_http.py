#!/usr/bin/env python3
import sqlite3
import requests
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / 'mystock.db'
API_BASE = 'http://localhost:5000'

def get_zero_price_codes(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, name FROM stock WHERE price=0 OR price IS NULL")
    return cur.fetchall()

def update_stock(conn, stock_id, updates: dict):
    fields = []
    values = []
    for k, v in updates.items():
        fields.append(f"{k} = ?")
        values.append(v)
    if not fields:
        return
    values.append(stock_id)
    sql = f"UPDATE stock SET {', '.join(fields)} WHERE id = ?"
    conn.execute(sql, values)
    conn.commit()

def main():
    if not DB_PATH.exists():
        print(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    rows = get_zero_price_codes(conn)
    print(f"갱신 대상 종목 수: {len(rows)}")

    updated = 0
    for idx, (stock_id, symbol, name) in enumerate(rows, 1):
        code = str(symbol).zfill(6) if symbol else None
        print(f"[{idx}/{len(rows)}] {stock_id} / {code} / {name}")
        if not code:
            continue
        try:
            r = requests.get(f"{API_BASE}/api/debug/kis-raw/{code}", timeout=10)
            if r.status_code != 200:
                print(f"  API 오류: {r.status_code}")
                continue
            j = r.json()
            if not j.get('success'):
                print(f"  API 실패: {j.get('error')}")
                continue
            parsed = j.get('parsed') or {}
            if not parsed or 'currentPrice' not in parsed:
                print("  시세 없음, 건너뜀")
                continue

            updates = {
                'price': float(parsed.get('currentPrice', 0) or 0),
                'change': float(parsed.get('change', 0) or 0),
                'change_percent': float(parsed.get('changePercent', 0) or 0),
                'volume': int(parsed.get('volume', 0) or 0),
                'market_cap': int(parsed.get('marketCap', 0) or 0),
                'per': float(parsed.get('per', 0) or 0),
                'pbr': float(parsed.get('pbr', 0) or 0),
                'eps': float(parsed.get('eps', 0) or 0),
            }

            update_stock(conn, stock_id, updates)
            updated += 1
            print(f"  업데이트 완료: price={updates['price']}, market_cap={updates['market_cap']}")
            time.sleep(0.2)
        except Exception as e:
            print(f"  오류: {e}")

    print(f"완료: {updated}건 업데이트됨")
    conn.close()

if __name__ == '__main__':
    main()
