# 자동매매 전략 1 구현 문서
# KIS Open API 상한가 갭상승 모멘텀 전략

## 1. 개요

### 1.1 전략 소개
- **전략명**: 전일 상한가 종목의 갭상승 모멘텀 전략
- **기본 원리**: 전일 상한가(+29.5% 이상) 달성 종목 중 다음 날 갭상승으로 시작하는 종목에 진입
- **익절/손절**: TP +10%, SL -3%
- **청산 방식**: 익절/손절 도달 또는 장 마감 전 강제 청산

### 1.2 구현 범위
- ✅ 백엔드 엔진 (Python)
- ✅ REST API 엔드포인트
- ✅ 프론트엔드 UI (React/TypeScript)
- ✅ 데이터베이스 스키마
- ✅ 로깅 시스템
- ⚠️ 실제 자동 루프 실행은 별도 스케줄러 필요

---

## 2. 전략 파라미터

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `UPPER_LIMIT_RATE` | 29.5% | 상한가 기준 등락률 |
| `MIN_MARKET_CAP` | 500억 | 최소 시가총액 |
| `GAP_THRESHOLD` | 2% | 갭상승 기준 (전일 종가 대비) |
| `GAP_CONFIRM_COUNT` | 2 | 갭 확인 횟수 |
| `ENTRY_START_TIME` | 09:01 | 진입 시작 시간 |
| `ENTRY_END_TIME` | 09:30 | 진입 종료 시간 |
| `TAKE_PROFIT_RATE` | 10% | 익절 기준 |
| `STOP_LOSS_RATE` | -3% | 손절 기준 |
| `EOD_SELL_START` | 15:15 | EOD 청산 시작 시간 |
| `EOD_SELL_END` | 15:25 | EOD 청산 종료 시간 |
| `MAX_DAILY_LOSS_RATE` | -5% | 일일 최대 손실률 |
| `MAX_POSITIONS` | 5 | 최대 동시 보유 포지션 |
| `POSITION_SIZE_RATE` | 20% | 종목당 투자 비율 |

---

## 3. 아키텍처

### 3.1 파일 구조
```
mystocks/
├── auto_trading_strategy1.py    # 자동매매 엔진 (Python)
├── update_stock_prices.py       # Flask API + 자동매매 라우트
├── components/
│   └── AutoTradingPage.tsx      # 프론트엔드 UI
├── types.ts                     # TypeScript 타입 정의
├── App.tsx                      # 라우팅 및 메인 앱
└── kis_open_api_자동매매_전략1_개발자_가이드_구현.md  # 이 문서
```

### 3.2 상태 기계 (State Machine)

#### 전략 단계 (StrategyPhase)
```
IDLE → PREPARING → ENTRY_WINDOW → MONITORING → EOD_CLOSING → CLOSED
```

| 단계 | 시간대 | 설명 |
|-----|--------|------|
| `IDLE` | 장 외 시간 | 비활성 상태 |
| `PREPARING` | 08:30 ~ 09:00 | 유니버스 구축 및 초기화 |
| `ENTRY_WINDOW` | 09:01 ~ 09:30 | 진입 신호 감시 및 매수 |
| `MONITORING` | 09:30 ~ 15:15 | 포지션 모니터링 (익절/손절) |
| `EOD_CLOSING` | 15:15 ~ 15:25 | 장 마감 전 강제 청산 |
| `CLOSED` | 15:25 이후 | 당일 거래 종료 |

#### 포지션 상태 (PositionState)
```
IDLE → WATCHING → ENTRY_PENDING → ENTERED → EXIT_PENDING → CLOSED
                                         ↓
                                      SKIPPED
                                      ERROR
```

| 상태 | 설명 |
|-----|------|
| `IDLE` | 초기 상태 |
| `WATCHING` | 갭상승 감시 중 |
| `ENTRY_PENDING` | 매수 주문 체결 대기 |
| `ENTERED` | 보유 중 (포지션 진입 완료) |
| `EXIT_PENDING` | 매도 주문 체결 대기 |
| `CLOSED` | 청산 완료 |
| `SKIPPED` | 진입 조건 미달로 건너뜀 |
| `ERROR` | 오류 발생 |

---

## 4. API 엔드포인트

### 4.1 상태 조회
```
GET /api/auto-trading/status
```
**응답:**
```json
{
  "success": true,
  "is_running": true,
  "phase": "ENTRY_WINDOW",
  "today": "2025-01-23",
  "total_asset": 10000000,
  "available_cash": 8000000,
  "daily_pnl": 50000,
  "daily_pnl_rate": 0.5,
  "universe": [...],
  "positions": {...},
  "total_trades": 10,
  "winning_trades": 7,
  "losing_trades": 3,
  "logs": [...],
  "last_update": "2025-01-23T09:15:00"
}
```

### 4.2 전략 시작/중지
```
POST /api/auto-trading/start
POST /api/auto-trading/stop
```

### 4.3 유니버스 구축
```
POST /api/auto-trading/build-universe
```
전일 상한가 종목을 조회하여 유니버스를 구축합니다.

### 4.4 수동 매매
```
POST /api/auto-trading/manual-buy
Body: { "code": "005930", "quantity": 10 }

POST /api/auto-trading/manual-sell
Body: { "code": "005930", "quantity": 0 }  // 0이면 전량 매도
```

### 4.5 포지션 동기화
```
POST /api/auto-trading/refresh-positions
```
KIS 증권계좌 잔고를 조회하여 포지션 정보를 동기화합니다.

### 4.6 전략 설정 조회
```
GET /api/auto-trading/config
```

### 4.7 거래 내역
```
GET /api/auto-trading/trade-history?days=7
```

### 4.8 로그 조회
```
GET /api/auto-trading/logs?limit=100
```

---

## 5. 데이터베이스 스키마

### 5.1 auto_trading_logs 테이블
```sql
CREATE TABLE IF NOT EXISTS auto_trading_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    code TEXT,
    message TEXT,
    data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### 5.2 auto_trading_trades 테이블
```sql
CREATE TABLE IF NOT EXISTS auto_trading_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    trade_type TEXT NOT NULL,  -- 'buy' or 'sell'
    quantity INTEGER NOT NULL,
    price INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    exit_reason TEXT,  -- 'take_profit', 'stop_loss', 'eod', 'manual'
    pnl INTEGER,
    pnl_rate REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### 5.3 auto_trading_universe 테이블
```sql
CREATE TABLE IF NOT EXISTS auto_trading_universe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    prev_close INTEGER,
    prev_high INTEGER,
    change_rate REAL,
    market_cap INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, code)
)
```

---

## 6. 프론트엔드 UI

### 6.1 주요 기능
- **상태 표시**: 전략 실행 상태, 현재 단계, 일일 손익
- **통계 카드**: 총 자산, 가용 현금, 일일 손익, 승률
- **보유 포지션**: 현재 보유 중인 종목, 손익, 매도 버튼
- **감시 종목**: 유니버스 종목, 갭 확인 횟수, 수동 매수 버튼
- **수동 주문**: 종목코드/수량 입력 후 매수
- **전략 설정**: 파라미터 확인
- **거래 내역**: 최근 7일간 매수/매도 기록
- **실시간 로그**: 이벤트 로그 뷰어

### 6.2 자동 갱신
- 3초마다 상태 자동 갱신
- 실시간 포지션/손익 업데이트

---

## 7. 사용 방법

### 7.1 초기 설정
1. `config.ini`에 KIS 증권 API 키 설정
2. 실계좌/모의계좌 선택 확인
3. Flask 서버 실행

### 7.2 자동매매 운영 (권장 흐름)
1. **08:30 이전**: 웹 UI에서 "유니버스 구축" 클릭
2. **08:50**: "시작" 버튼 클릭하여 전략 활성화
3. **09:01 ~ 09:30**: 진입 구간 - 갭상승 감시 및 자동 진입
4. **09:30 ~ 15:15**: 모니터링 - 익절/손절 자동 실행
5. **15:15 ~ 15:25**: EOD 청산 - 미청산 포지션 강제 매도
6. **15:25 이후**: 당일 거래 종료, 결과 확인

### 7.3 수동 개입
- **수동 매수**: 유니버스에 없는 종목도 직접 매수 가능
- **수동 매도**: 포지션의 "전량매도" 버튼 클릭
- **포지션 동기화**: 증권사 잔고와 동기화

---

## 8. 주의사항

### 8.1 위험 관리
- **일일 최대 손실**: -5% 도달 시 신규 진입 중단
- **최대 포지션**: 5개 초과 시 신규 진입 불가
- **손절 라인**: -3% 도달 시 즉시 청산

### 8.2 제한 사항
- 자동 루프 실행은 별도 스케줄러(cron, APScheduler 등) 필요
- 웹소켓 실시간 시세 미지원 (3초 폴링 방식)
- 동시호가 시간(08:30~09:00)에는 주문 불가

### 8.3 개선 필요 사항
- [ ] 웹소켓 기반 실시간 시세
- [ ] APScheduler 자동 실행
- [ ] 전략 파라미터 실시간 변경
- [ ] 백테스팅 기능
- [ ] 알림 기능 (카카오톡/텔레그램)

---

## 9. 코드 예시

### 9.1 엔진 초기화
```python
from auto_trading_strategy1 import AutoTradingEngine

engine = AutoTradingEngine()

# 유니버스 구축
engine.build_universe()

# 전략 시작
engine.start()

# 상태 확인
status = engine.get_status()
print(f"Running: {status['is_running']}, Phase: {status['phase']}")
```

### 9.2 수동 매수
```python
# 삼성전자 10주 시장가 매수
result = engine.manual_buy("005930", 10)
print(f"주문번호: {result['order_no']}")
```

### 9.3 포지션 동기화
```python
# 증권사 잔고와 동기화
engine.refresh_positions()
```

---

## 10. 변경 이력

| 날짜 | 버전 | 내용 |
|-----|------|------|
| 2025-01-23 | 1.0.0 | 초기 구현 완료 |

---

## 11. 참조

- 원본 가이드: `kis_open_api_자동매매_전략1_개발자_가이드.md`
- KIS Open API 문서: https://apiportal.koreainvestment.com/
- React TypeScript 공식 문서: https://react.dev/
