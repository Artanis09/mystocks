#!/usr/bin/env python3
import update_stock_prices as mod
from update_stock_prices import app, db, Stock
from update_stock_prices import load_etf_cache, save_etf_cache, get_kis_realtime_price
import time

def main():
    with app.app_context():
        print("DB에서 price==0인 종목 조회 중...")
        zero_stocks = Stock.query.filter((Stock.price == 0) | (Stock.price == None)).all()
        print(f"업데이트 대상 종목 수: {len(zero_stocks)}")
        if not zero_stocks:
            return

        cache = load_etf_cache()
        updated = 0
        for s in zero_stocks:
            code = str(s.symbol).zfill(6)
            print(f"[{updated+1}/{len(zero_stocks)}] 조회: {code} ({s.name})")
            try:
                kis = get_kis_realtime_price(code)
                if not kis or ('currentPrice' not in kis):
                    print(f"  KIS 시세 없음: {code}, 건너뜀")
                    continue

                s.price = float(kis.get('currentPrice', s.price) or 0)
                s.change = float(kis.get('change', s.change) or 0)
                s.change_percent = float(kis.get('changePercent', s.change_percent) or 0)
                s.volume = int(kis.get('volume', s.volume) or 0)
                # DB 컬럼은 market_cap 정수
                try:
                    s.market_cap = int(kis.get('marketCap', s.market_cap) or 0)
                except Exception:
                    try:
                        s.market_cap = int(float(kis.get('marketCap', 0)))
                    except Exception:
                        s.market_cap = s.market_cap or 0

                s.per = float(kis.get('per', s.per) or 0)
                s.pbr = float(kis.get('pbr', s.pbr) or 0)
                s.eps = float(kis.get('eps', s.eps) or 0)

                # DB 저장
                db.session.add(s)

                # ETF 캐시도 함께 갱신
                try:
                    entry = cache.get(code, {}) if isinstance(cache, dict) else {}
                    if not isinstance(entry, dict):
                        entry = {}
                    # 이름은 기존 캐시 또는 DB의 이름 유지
                    entry.setdefault('name', s.name)
                    for k in ['currentPrice', 'marketCap', 'per', 'pbr', 'eps', 'volume', 'change', 'changePercent']:
                        if k in kis:
                            entry[k] = kis[k]
                    cache[code] = entry
                except Exception as e:
                    print(f"  캐시 업데이트 실패: {e}")

                updated += 1
                # 커밋을 자주 해서 안전성 확보
                if updated % 10 == 0:
                    db.session.commit()
                    save_etf_cache(cache)
                    print(f"  중간 커밋: {updated}건 처리")
                time.sleep(0.2)
            except Exception as e:
                print(f"  처리 중 오류: {e}")

        # 최종 커밋
        db.session.commit()
        save_etf_cache(cache)
        print(f"완료: {updated}건 업데이트됨")

if __name__ == '__main__':
    main()
