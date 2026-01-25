# 자동매매 전략 1 구현 문서
# KIS Open API 상한가 갭상승 모멘텀 전략

> **최종 업데이트**: 2026-01-25  
> **버전**: 2.1.0 (시가총액 필터 및 진입 실패 처리 강화)

---

## 목차
1. [개요](#1-개요)
2. [전략 파라미터](#2-전략-파라미터)
3. [시스템 아키텍처](#3-시스템-아키텍처)
4. [투자 모드 (모의/실전)](#4-투자-모드-모의실전)
5. [자동 실행 타임라인](#5-자동-실행-타임라인)
6. [유니버스 구축 로직](#6-유니버스-구축-로직)
7. [주문 방식 상세](#7-주문-방식-상세)
8. [API 엔드포인트](#8-api-엔드포인트)
9. [데이터베이스 스키마](#9-데이터베이스-스키마)
10. [휴장일 처리](#10-휴장일-처리)
11. [운영 매뉴얼](#11-운영-매뉴얼)
12. [문제 해결](#12-문제-해결)
13. [변경 이력](#13-변경-이력)

---

## 1. 개요

### 1.1 전략 소개
- **전략명**: 전일 상한가 종목의 갭상승 모멘텀 전략 (Strategy 1 - Upper Limit Gap Momentum)
- **기본 원리**: 전일 상한가(+29.5% 이상) 달성 종목 중 다음 날 갭상승(+2% 이상)으로 시작하는 종목에 진입
- **익절/손절**: TP +10%, SL -3%
- **청산 방식**: 익절/손절 도달 또는 장 마감 전 강제 청산 (EOD)

### 1.2 구현 범위
- ✅ 백엔드 엔진 (`auto_trading_strategy1.py`)
- ✅ REST API 엔드포인트 (`update_stock_prices.py`)
- ✅ 프론트엔드 UI (`components/AutoTradingPage.tsx`)
- ✅ 모의투자/실전투자 모드 전환
- ✅ 휴장일 자동 체크
- ✅ 시간대별 유니버스 데이터 선택
- ✅ 자동 실행 루프 (Threading 기반)
- ✅ 상태 영속화 (JSON 파일)
- ✅ 로깅 시스템 (파일 + DB)

### 1.3 파일 구조
```
mystocks/
├── auto_trading_strategy1.py          # 자동매매 엔진 핵심 로직
├── update_stock_prices.py             # Flask API 서버 + 라우트
├── auto_trading_state_mock.json       # 모의투자 상태 저장
├── auto_trading_state_real.json       # 실전투자 상태 저장
├── kis_token_mock.json                # 모의투자 토큰 캐시
├── kis_token_real.json                # 실전투자 토큰 캐시
├── auto_trading.log                   # 로그 파일
├── components/
│   └── AutoTradingPage.tsx            # 프론트엔드 자동매매 UI
└── data/krx/bars/                     # 일봉 데이터 (parquet)
```

---

## 2. 전략 파라미터

### 2.1 실제 구현된 기본값 (StrategyConfig 클래스)

| 파라미터 | 코드 상수명 | 기본값 | 설명 |
|---------|-------------|--------|------|
| 상한가 기준 | `UPPER_LIMIT_RATE` | **29.5%** | 전일 등락률 기준 |
| 최소 시가총액 | `MIN_MARKET_CAP` | **500억** | KIS API 실시간 조회 필터 |
| 갭상승 기준 | `GAP_THRESHOLD` | **2.0%** | 시가 갭 기준 |
| 갭 확인 횟수 | `GAP_CONFIRM_COUNT` | **2회** | 노이즈 제거용 |
| 진입 시작 | `ENTRY_START_TIME` | **09:00** | 진입 가능 시작 시간 |
| 진입 종료 | `ENTRY_END_TIME` | **09:03** | 진입 가능 종료 시간 |
| 급등 진입 금지 | `ENTRY_MAX_RISE_RATE` | **8.0%** | 미체결 시 이 이상 오르면 포기 |
| 미체결 타임아웃 | `ENTRY_PENDING_TIMEOUT`| **60초** | 주문 후 미체결 시 취소 대기시간 |
| 익절 기준 | `TAKE_PROFIT_RATE` | **+10%** | 익절 청산 |
| 손절 기준 | `STOP_LOSS_RATE` | **-3%** | 손절 청산 |
| EOD 청산 시작 | `EOD_SELL_START` | **15:20** | 장마감 전 청산 시작 |
| EOD 청산 종료 | `EOD_SELL_END` | **15:28** | 장마감 전 청산 종료 |
| 일일 최대 손실 | `MAX_DAILY_LOSS_RATE` | **-5%** | 초과 시 신규 진입 차단 |
| 최대 동시 포지션 | `MAX_POSITIONS` | **5개** | 1/N 투자 방식 |
| 슬리피지 허용 틱 | `ORDER_SLIPPAGE_TICKS` | **2틱** | 공격 지정가 틱 수 |
| 주문 타임아웃 | `ORDER_TIMEOUT_SEC` | **5초** | 주문 응답 타임아웃 |
| 주문 재시도 | `ORDER_RETRY_COUNT` | **3회** | 실패 시 재시도 횟수 |
| 윈도우 후 취소 | `ENTRY_ORDER_CANCEL_AFTER_WINDOW` | **True** | 09:03 이후 미체결 건 즉시 취소 |

> *참고: 시가총액 정보는 KIS API(`주식현재가 시세`)를 통해 실시간으로 획득하여 필터링 및 우선순위 정렬에 사용함

### 2.2 API로 변경 가능한 파라미터
```
POST /api/auto-trading/config
```
변경 가능 항목:
- `max_positions`, `take_profit_rate`, `stop_loss_rate`
- `gap_threshold`, `min_market_cap`
- `entry_start_time`, `entry_end_time`

---

## 3. 시스템 아키텍처

### 3.1 상태 기계 (State Machine)

#### 전략 단계 (StrategyPhase)
```
IDLE → PREPARING → ENTRY_WINDOW → MONITORING → EOD_CLOSING → CLOSED
       (08:40)    (09:00)        (09:03)       (15:20)       (15:28)
```

| 단계 | 시간대 | 동작 | 루프 간격 |
|-----|--------|------|----------|
| `IDLE` | ~08:40, 15:28~ | 비활성 (주말/휴장일 포함) | 60초 |
| `PREPARING` | 08:40~09:00 | 토큰 확인, 계좌 조회, 유니버스 구축 | **5초** |
| `ENTRY_WINDOW` | 09:00~09:03 | 갭상승 시그널 감시 + 매수 주문 | **0.5초** |
| `MONITORING` | 09:03~15:20 | TP/SL 시그널 감시 + 청산 주문 | **2초** |
| `EOD_CLOSING` | 15:20~15:28 | 미청산 포지션 강제 매도 | **1초** |
| `CLOSED` | 15:28~ | 당일 거래 종료, 잔여 포지션 경고 | 60초 |

#### 포지션 상태 (PositionState)
```
         ┌──────────────────────────────────────────────┐
         │                                              │
  IDLE ──┼── WATCHING ──── ENTRY_PENDING ──── ENTERED ──┼── EXIT_PENDING ─── CLOSED
         │      │              │                  │     │
         │      └── SKIPPED ◄──┘                  │     │
         │                                        │     │
         └──────────────────── ERROR ◄────────────┘     │
                                                        │
                                      (TP/SL/EOD/MANUAL)
```

| 상태 | 설명 | 전환 조건 |
|-----|------|----------|
| `IDLE` | 초기 상태 | 유니버스 미포함 |
| `WATCHING` | 갭상승 감시 중 | 유니버스 편입 시 |
| `ENTRY_PENDING` | 매수 주문 체결 대기 | 갭 시그널 확인(2회) → 매수 주문 |
| `ENTERED` | 보유 중 | 매수 체결 완료 |
| `EXIT_PENDING` | 매도 주문 체결 대기 | TP/SL/EOD 시그널 → 매도 주문 |
| `CLOSED` | 청산 완료 | 매도 체결 완료 |
| `SKIPPED` | 진입 조건 미달로 건너뜜 | 수량 부족, 최대 포지션 도달, 일일 손실 한도, **급등 포기**, **미체결 타임아웃** |
| `ERROR` | 오류 발생 | API 오류, 체결 실패 등 |

---

## 4. 투자 모드 (모의/실전)

### 4.1 모드별 설정

| 항목 | 모의투자 (Mock) | 실전투자 (Real) |
|-----|----------------|-----------------|
| **KIS API URL** | `https://openapivts.koreainvestment.com:29443` | `https://openapi.koreainvestment.com:9443` |
| **환경변수** | `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` | `KIS_REAL_APP_KEY`, `KIS_REAL_APP_SECRET`, `KIS_REAL_ACCOUNT_NO` |
| **토큰 파일** | `kis_token_mock.json` | `kis_token_real.json` |
| **상태 파일** | `auto_trading_state_mock.json` | `auto_trading_state_real.json` |
| **TR_ID 접두사** | `V` (예: VTTC0802U) | `T` (예: TTTC0802U) |

### 4.2 모드 전환 API
```
GET  /api/auto-trading/mode          # 현재 모드 조회
POST /api/auto-trading/mode          # 모드 전환
     Body: { "mode": "mock" }  또는  { "mode": "real" }
```

**주의사항:**
- 모드 전환 시 실행 중인 엔진은 자동 중지됨
- 모의/실전 엔진은 별도 인스턴스로 분리되어 있음
- 각 모드별 토큰과 상태 파일이 독립적으로 관리됨

### 4.3 Docker 환경변수 설정 (docker-compose.yml)
```yaml
environment:
  # 모의투자 키
  - KIS_APP_KEY=${KIS_APP_KEY}
  - KIS_APP_SECRET=${KIS_APP_SECRET}
  - KIS_ACCOUNT_NO=${KIS_ACCOUNT_NO}
  # 실전투자 키 (선택)
  - KIS_REAL_APP_KEY=${KIS_REAL_APP_KEY}
  - KIS_REAL_APP_SECRET=${KIS_REAL_APP_SECRET}
  - KIS_REAL_ACCOUNT_NO=${KIS_REAL_ACCOUNT_NO}
```

---

## 5. 자동 실행 타임라인

### 5.1 장중 자동 동작 (거래일 기준)

```
시간        동작
────────────────────────────────────────────────────────
~08:40     IDLE 상태 (아무 동작 없음)

08:40      [자동] PREPARING 단계 진입
           - KIS 토큰 확인/발급
           - 계좌 잔고 조회 → total_asset, available_cash 업데이트
           - 유니버스 구축 (아직 안했으면)
           - 유니버스 종목을 WATCHING 상태로 초기화

09:00      [자동] ENTRY_WINDOW 단계 진입
           - 0.5초마다 갭상승 시그널 체크
           - 시가가 전일종가 대비 +2% 이상이면 gap_confirms +1
           - 현재가가 +8% 이상 급등 시 진입 포기 (SKIPPED)
           - gap_confirms >= 2 이면 매수 주문 실행 (공격 지정가)
           - 60초간 미체결 시 주문 취소 후 진입 포기 (SKIPPED)
           - 체결 확인 → ENTERED 상태로 전환

09:03      [자동] MONITORING 단계 진입
           - 진입 윈도우 종료 시점의 모든 미체결 매수 주문 즉시 취소
           - 2초마다 TP(+10%) / SL(-3%) 시그널 체크
           - 시그널 발생 시 즉시 시장가 매도 주문
           - 체결 확인 → CLOSED 상태로 전환

09:03      [자동] MONITORING 단계 진입
           - 2초마다 현재가 조회
           - TP(+10%) 또는 SL(-3%) 도달 시 시장가 매도
           - 일일 손실률 -5% 초과 시 신규 진입 차단

15:20      [자동] EOD_CLOSING 단계 진입
           - ENTERED 상태 포지션 전량 시장가 매도
           - 체결 확인 → CLOSED 상태로 전환

15:28      [자동] CLOSED 단계 진입
           - 미청산 포지션 경고 로그
           - 당일 거래 종료

15:30~     다음 날까지 대기
           (만약 엔진이 실행 중이면 계속 대기, 새 거래일에 상태 리셋)
```

### 5.2 수동 실행 시 영향

| 시나리오 | 동작 |
|---------|------|
| **08:40 이전 "시작" 클릭** | IDLE 상태로 대기, 08:40에 PREPARING 자동 진입 |
| **09:00 이후 "시작" 클릭** | 현재 시간에 맞는 단계로 즉시 진입 (예: 09:30이면 MONITORING) |
| **"유니버스 구축" 수동 클릭** | 즉시 유니버스 구축, 08:40 자동 구축은 스킵됨 (이미 있으므로) |
| **"포지션 동기화" 클릭** | 증권사 잔고 조회 → 내부 상태와 동기화 |
| **15:28 이후 "시작" 클릭** | CLOSED 상태, 60초마다 대기 (다음 날까지) |
| **휴장일에 "시작" 클릭** | IDLE 상태 유지, 주문 불가 |

### 5.3 새 거래일 감지

엔진은 상태 파일(`auto_trading_state_*.json`)의 `today` 필드와 현재 날짜를 비교합니다:
- **날짜가 다르면**: 새로운 `StrategyState` 생성, 모든 포지션/유니버스 초기화
- **날짜가 같으면**: 기존 상태 복원 (서버 재시작 후에도 상태 유지)

---

## 6. 유니버스 구축 로직

### 6.1 대상 날짜 선택 (`_get_universe_target_date`)

| 현재 시간 | 유니버스 기준일 | 설명 |
|----------|----------------|------|
| **20:00 이후** | 당일 | 오늘 상한가 종목 → 내일 매매용 |
| **08:00 ~ 20:00** | 전일 | 어제 상한가 종목 → 오늘 매매용 |

```python
def _get_universe_target_date(self) -> date:
    now = datetime.now()
    current_hour = now.hour
    today = now.date()
    
    if current_hour >= 20:
        # 저녁 8시 이후: 당일 데이터
        if is_trading_day(today):
            return today
        else:
            return get_prev_trading_day(today)
    else:
        # 오전~저녁: 전일 데이터
        return get_prev_trading_day(today)
```

### 6.2 데이터 소스 우선순위

1. **로컬 Parquet 데이터** (우선): `data/krx/bars/date=YYYY-MM-DD/`
2. **pykrx 폴백**: 로컬 데이터 없을 시 API 조회

### 6.3 유니버스 조건 및 필터링

1. **상한가 조건**: 전일 등락률 ≥ 29.5%
2. **시가총액 필터**: KIS API(`주식현재가 시세`)를 통해 종목별 시가총액(`hts_avls`) 실시간 조회 및 **500억 미만 제외**
3. **우선순위 정렬**: 시가총액이 **높은 종목** 순으로 정렬하여 상위 N개 선정

```python
# 실제 구현 로직 (auto_trading_strategy1.py)
for code in potential_codes:
    mkt_cap = self._get_market_cap(code) # 억원 단위
    if mkt_cap >= self.config.MIN_MARKET_CAP / 100_000_000:
        universe.append(...)
universe.sort(key=lambda x: x.market_cap, reverse=True)
```

### 6.4 영속성 및 저장
- **상태 저장**: `auto_trading_state_[mode].json`에 저장되어 서버 재시작 시에도 유지됨
- **DB 기록**: 구축된 유니버스는 `universe_history` 테이블에 자동 저장되어 과거 유니버스 추적 가능

### 6.5 수동 유니버스 구축

```
POST /api/auto-trading/build-universe
```

응답:
```json
{
  "success": true,
  "count": 5,
  "universe": [
    { "code": "001140", "name": "국보", "prev_close": 130, "change_rate": 29.92 },
    ...
  ]
}
```

---

## 7. 주문 방식 상세

### 7.1 매수 주문 (execute_entry)

| 항목 | 값 |
|-----|---|
| **주문 방식** | **공격 지정가** |
| **주문 가격** | 매도호가(Ask) + (슬리피지틱 × 호가단위) |
| **슬리피지 틱** | 2틱 (기본값) |
| **수량 계산** | `총자산 / MAX_POSITIONS / 주문가격` |
| **TR_ID** | 모의: `VTTC0802U`, 실전: `TTTC0802U` |
| **ORD_DVSN** | `00` (지정가) |

#### 진입 실패 및 취소 로직 (Update 2.1.0)
1. **급등 진입 금지**: 진입 시도 시 현재가가 `ENTRY_MAX_RISE_RATE`(8%) 이상 오르면 `SKIPPED` 처리하고 진입을 포기합니다. (추격 매수 방지)
2. **미체결 타임아웃**: 매수 주문 후 `ENTRY_PENDING_TIMEOUT`(60초) 내에 체결되지 않으면 주문을 취소하고 `SKIPPED` 처리합니다.
3. **진입 윈도우 마감 취소**: 장 초반 변동성 구간(09:00~09:03)이 종료되면 체결되지 않은 모든 매수 대기 주문을 즉시 취소합니다.

```python
# 주문 가격 계산
order_price = ask_price + (self.config.ORDER_SLIPPAGE_TICKS * self._get_tick_size(current_price))

# 수량 계산 (1/N 방식)
position_amount = self.state.total_asset / self.config.MAX_POSITIONS
quantity = int(position_amount / order_price)
```

### 7.2 매도 주문 (execute_exit)

| 항목 | 값 |
|-----|---|
| **주문 방식** | **시장가** |
| **주문 가격** | 0 (시장가) |
| **수량** | 보유 전량 |
| **TR_ID** | 모의: `VTTC0801U`, 실전: `TTTC0801U` |
| **ORD_DVSN** | `01` (시장가) |

```python
# 시장가 매도 (빠른 청산을 위해)
result = self._place_order(position.code, position.quantity, 'sell', 0)
```

### 7.3 호가 단위 (tick_size)

```python
def _get_tick_size(self, price: int) -> int:
    if price < 1000:     return 1
    elif price < 5000:   return 5
    elif price < 10000:  return 10
    elif price < 50000:  return 50
    elif price < 100000: return 100
    elif price < 500000: return 500
    else:                return 1000
```

### 7.4 주문 정정/취소 (_cancel_order)
- **목적**: 미체결된 매수 주문의 자동 취소 (Update 2.1.0)
- **API**: KIS API 주식주문(정정취소)
- **TR_ID**: 모의: `VTTC0803U`, 실전: `TTTC0803U`
- **로직**: 원주문 번호를 참조하여 전량 취소 요청

### 7.5 청산 사유 (exit_reason)

| 코드 | 설명 | 트리거 조건 |
|-----|------|-----------|
| `TP` | 익절 (Take Profit) | 수익률 >= +10% |
| `SL` | 손절 (Stop Loss) | 수익률 <= -3% |
| `EOD` | 장마감 청산 (End of Day) | 15:20 이후 |
| `MANUAL` | 수동 매도 | 사용자 직접 매도 버튼 클릭 |

---

## 8. API 엔드포인트

### 8.1 상태 조회
```
GET /api/auto-trading/status
```
응답:
```json
{
  "success": true,
  "isTradingDay": true,
  "is_running": true,
  "phase": "MONITORING",
  "today": "2026-01-25",
  "total_asset": 10000000,
  "available_cash": 8000000,
  "daily_pnl": 150000,
  "daily_pnl_rate": 1.5,
  "mode": "mock",
  "label": "모의투자",
  "is_mock": true,
  "universe": [...],
  "positions": {
    "001140": {
      "code": "001140",
      "name": "국보",
      "state": "WATCHING",
      "prev_close": 130,
      "entry_price": 0,
      "current_price": 0,
      "quantity": 0,
      "unrealized_pnl": 0,
      "unrealized_pnl_rate": 0,
      "gap_confirms": 1,
      "order_id": "",
      "entry_time": "",
      "exit_time": "",
      "exit_reason": "",
      "error_message": ""
    }
  },
  "total_trades": 3,
  "winning_trades": 2,
  "losing_trades": 1,
  "logs": [...],
  "last_update": "2026-01-25T10:30:00"
}
```

### 8.2 전략 시작/중지
```
POST /api/auto-trading/start     # 자동매매 엔진 시작
POST /api/auto-trading/stop      # 자동매매 엔진 중지
```

### 8.3 모드 전환
```
GET  /api/auto-trading/mode
POST /api/auto-trading/mode      Body: { "mode": "real" }
```

### 8.4 거래일 확인
```
GET /api/auto-trading/is-trading-day
```
응답:
```json
{
  "success": true,
  "date": "2026-01-25",
  "is_trading_day": false,
  "reason": "토요일"
}
```

### 8.5 유니버스 구축
```
POST /api/auto-trading/build-universe
```

### 8.6 수동 매매
```
POST /api/auto-trading/manual-buy
Body: { "code": "005930", "quantity": 10 }

POST /api/auto-trading/manual-sell
Body: { "code": "005930", "quantity": 0 }  // 0이면 전량 매도
```

### 8.7 포지션 동기화
```
POST /api/auto-trading/refresh-positions
```

### 8.8 전략 설정
```
GET  /api/auto-trading/config
POST /api/auto-trading/config
     Body: { "max_positions": 3, "take_profit_rate": 8.0 }
```

### 8.9 거래 내역
```
GET /api/auto-trading/trade-history?days=7
```

### 8.10 로그 조회
```
GET /api/auto-trading/logs?limit=100
```

---

## 9. 데이터베이스 스키마

### 9.1 auto_trading_logs 테이블
```sql
CREATE TABLE IF NOT EXISTS auto_trading_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    level TEXT NOT NULL,
    phase TEXT,
    code TEXT,
    event TEXT NOT NULL,
    message TEXT,
    data TEXT
)
```

### 9.2 auto_trading_trades 테이블
```sql
CREATE TABLE IF NOT EXISTS auto_trading_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    trade_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,
    exit_reason TEXT,
    pnl REAL,
    pnl_rate REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

### 9.3 auto_trading_universe 테이블
```sql
CREATE TABLE IF NOT EXISTS auto_trading_universe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    prev_close REAL,
    change_rate REAL,
    market_cap REAL,
    result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, code)
)
```

---

## 10. 휴장일 처리

### 10.1 휴장일 판별 로직

```python
def is_trading_day(check_date: date = None) -> bool:
    if check_date is None:
        check_date = date.today()
    
    # 1. 주말 체크 (토=5, 일=6)
    if check_date.weekday() >= 5:
        return False
    
    # 2. 공휴일 체크
    holidays = get_korean_holidays(check_date.year)
    if check_date.strftime('%Y-%m-%d') in holidays:
        return False
    
    return True
```

### 10.2 등록된 휴장일 (2026년)

```python
holidays = {
    "2026-01-01",  # 신정
    "2026-01-28", "2026-01-29", "2026-01-30",  # 설날 연휴
    "2026-02-17",  # 대체공휴일
    "2026-03-01",  # 삼일절
    "2026-05-05",  # 어린이날
    "2026-05-24",  # 부처님오신날
    "2026-06-06",  # 현충일
    "2026-08-15",  # 광복절
    "2026-10-03",  # 개천절
    "2026-10-04", "2026-10-05", "2026-10-06",  # 추석 연휴
    "2026-10-09",  # 한글날
    "2026-12-25",  # 크리스마스
    "2026-12-31",  # 연말
}
```

### 10.3 휴장일 동작

- **엔진 시작 시**: `is_trading_day()` 체크 → False면 IDLE 상태 유지
- **UI 표시**: "오늘은 휴장일입니다" 경고 배너
- **버튼 비활성화**: 매수/매도/포지션 동기화 버튼 disabled
- **자동 루프**: `_determine_phase()` → 휴장일이면 항상 IDLE 반환

---

## 11. 운영 매뉴얼

### 11.1 일반적인 운영 흐름 (거래일)

#### 방법 1: 완전 자동 (권장)
```
1. 08:30 이전: 웹 UI에서 "시작" 버튼 클릭
2. 08:40~09:00: 자동으로 유니버스 구축 + 계좌 조회
3. 09:00~09:03: 갭상승 종목 자동 매수
4. 09:03~15:20: 익절/손절 자동 감시
5. 15:20~15:28: 미청산 포지션 EOD 청산
6. 15:28 이후: 결과 확인
```

#### 방법 2: 수동 유니버스 + 자동 매매
```
1. 전날 20:00 이후: "유니버스 구축" 클릭 (내일 매매 종목 확인)
2. 08:30: "시작" 버튼 클릭
3. 이후 자동 매매 진행
```

### 11.2 수동 개입 시나리오

| 상황 | 조치 |
|-----|------|
| 특정 종목 수동 매수 | "수동 매수" 입력창에 종목코드, 수량 입력 후 매수 |
| 손절 기다리기 싫음 | 해당 포지션 "전량매도" 버튼 클릭 |
| 유니버스 외 종목 매수 | 수동 매수로 추가 → 포지션에 자동 등록 |
| 증권사 앱에서 매수함 | "포지션 동기화" 클릭 → 내부 상태에 반영 |
| 모의 → 실전 전환 | 상단 "모의투자/실전투자" 토글 클릭 |

### 11.3 서버 재시작 시

- 상태 파일(`auto_trading_state_*.json`)에서 자동 복원
- 같은 날이면 기존 포지션/유니버스 유지
- 다른 날이면 새로운 상태로 초기화

### 11.4 문제 발생 시 체크리스트

1. **토큰 만료**: 자동 재발급됨, 로그에서 `TOKEN_ISSUED` 확인
2. **API 오류**: 로그에서 `ERROR` 레벨 메시지 확인
3. **주문 실패**: `error_message` 필드 확인, 계좌 잔고 확인
4. **상태 불일치**: "포지션 동기화" 실행

---

## 12. 문제 해결

### 12.1 자주 묻는 질문

**Q: 엔진을 시작했는데 아무 동작도 안 해요**
- A1: 휴장일인지 확인 (`is_trading_day` API 호출)
- A2: 현재 시간이 08:40 이전이면 IDLE 상태로 대기

**Q: 유니버스가 비어있어요**
- A1: 전일 상한가 종목이 없을 수 있음
- A2: 로컬 데이터(`data/krx/bars/`)가 최신인지 확인
- A3: 20:00 이후에 구축하면 당일 데이터 사용

**Q: 매수가 안 돼요**
- A1: 가용 현금 확인 (`available_cash`)
- A2: 최대 포지션 수(5개) 도달 여부 확인
- A3: 일일 손실 한도(-5%) 초과 여부 확인

**Q: 모의투자는 되는데 실전투자가 안 돼요**
- A1: `KIS_REAL_*` 환경변수 설정 확인
- A2: 실전투자 API 키가 활성화되어 있는지 확인
- A3: 토큰 파일(`kis_token_real.json`) 삭제 후 재시도

### 12.2 로그 확인 방법

```bash
# 파일 로그
tail -f auto_trading.log

# API로 로그 조회
curl http://localhost:5000/api/auto-trading/logs?limit=50 | jq
```

---

## 13. 변경 이력

| 날짜 | 버전 | 내용 |
|-----|------|------|
| 2025-01-23 | 1.0.0 | 초기 구현 완료 |
| 2026-01-25 | 2.0.0 | 전면 업데이트: 모의/실전 모드 분리, 휴장일 체크, 시간대별 유니버스 로직, 상세 매뉴얼 추가 |
| 2026-01-25 | 2.1.0 | 시가총액 필터링(500억+) 추가, 급등 방지(+8%) 및 미체결 타임아웃 주문 취소 로직 구현 |

---

## 14. 환경변수 정리

### 14.1 .env 파일 (권장 구조)

```env
# === Gemini API ===
GEMINI_API_KEY=your_gemini_api_key

# === KIS 모의투자 ===
KIS_APP_KEY=your_mock_app_key
KIS_APP_SECRET=your_mock_app_secret
KIS_ACCOUNT_NO=12345678-01

# === KIS 실전투자 (선택) ===
KIS_REAL_APP_KEY=your_real_app_key
KIS_REAL_APP_SECRET=your_real_app_secret
KIS_REAL_ACCOUNT_NO=87654321-01

# === Flask ===
FLASK_ENV=production
FLASK_DEBUG=0
```

---

## 15. 참조 문서

- KIS Open API 공식 문서: https://apiportal.koreainvestment.com/
- 원본 전략 가이드: `kis_open_api_자동매매_전략1_개발자_가이드.md`
- Docker 운영 가이드: `DOCKER_README.md`
- 사용자 매뉴얼: `USER_MANUAL.md`
