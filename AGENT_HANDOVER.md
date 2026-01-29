# Agent Handover & Context History (2026-01-29)

이 문서는 다른 PC 환경이나 다른 AI 모델(Agent)이 작업을 이어받을 때 현재까지의 진행 상황과 주요 수정 사항을 이해하기 위해 작성되었습니다.

## 0. 최신 작업 (2026-01-29)

### NXT(야간거래) 기능 추가
*   **요청 사항:** 
    1. KIS API 문서 참고하여 NXT/KRX 거래 가능 여부를 모든 UI 종목 정보에 `+NXT` 형태로 표시
    2. NXT 거래 가능 종목은 NXT 시간대(17:30~익일 08:00)에 실시간 현재가 조회 가능하도록 구현
*   **구현 내용:**
    - **백엔드 (`update_stock_prices.py`):**
      - NXT 종목 관리 함수: `load_nxt_stocks()`, `save_nxt_stocks()`, `is_nxt_hours()`, `is_nxt_stock()`
      - NXT 현재가 조회: `get_nxt_realtime_price()`, `get_smart_realtime_price()`
      - API 엔드포인트: `/api/nxt/stocks`, `/api/nxt/check/<code>`, `/api/nxt/price/<code>`, `/api/nxt/status`, `/api/nxt/init-default`
      - `/api/realtime-prices` API가 NXT 시간대에 자동으로 NXT 시세 조회
    - **프론트엔드:**
      - `types.ts`: `is_nxt`, `market` 필드 추가
      - `services/stockService.ts`: `loadNxtStocks`, `isNxtStock`, `checkNxtHours`, `getNxtInfoBatch`, `getNxtPrice` 함수 추가
      - `StockCard.tsx`: NXT 뱃지 표시 (Moon 아이콘 + "NXT")
      - `Recommendations.tsx`: 추천 종목에 NXT 뱃지, 헤더에 NXT 상태 표시
      - `AutoTradingPage.tsx`: 자동매매 대상에 NXT 뱃지, 헤더에 NXT 상태 표시
*   **NXT 시간대:** 17:30 ~ 익일 08:00 (한국 시간)
*   **NXT 종목 초기화:** `POST /api/nxt/init-default` 호출로 KOSPI200+KOSDAQ150 기준 종목 설정

## 1. 최근 주요 이슈 및 해결 내역

### 자산 조회 0원 이슈 (Asset Balance Zero Issue)
*   **원인 1 (로직 결함):** KIS API 호출 실패 시 에러를 반환하지 않고 0원 데이터를 반환하여 엔진 내부 자산 값을 0으로 고착시키는 문제가 있었음.
*   **원인 2 (환경 변수/경로):** 모의/실전 투자의 토큰 파일 및 상태 저장 파일이 상대 경로로 되어 있어, 실행 위치에 따라 파일을 읽지 못하는 현상이 발생함.
*   **원인 3 (키 호환성):** 토큰 저장 시 `expired_time`과 `expiry` 키가 혼용되어 다른 스크립트와의 호환성이 깨졌고, 이로 인해 무한 재발급 시도가 발생하여 API 403 차단(1분 제한)에 걸림.
*   **해결책:** 
    *   `_get_account_balance`에서 API 에러 발생 시 즉시 상위로 에러 전파.
    *   `_update_balance` 메서드를 신설하여 `total_eval`과 `net_asset` 중 유효한 값을 선택하는 방어 로직 구현.
    *   모든 파일 경로(`state_file`, `token_file`)를 `os.path.dirname(__file__)` 기준 절대 경로로 수정.
    *   토큰 저장/로드 시 `expired_time`과 `expiry` 키를 모두 지원하도록 수정.

### 휴장일 및 주말 체크 로직 제거
*   **요청 사항:** 엔진이 휴장일이나 주말에 관계없이 항상 동작하도록 수정 요청.
*   **작업 내용:** 
    *   `get_korean_holidays`, `is_trading_day` 등의 복잡한 공휴일 체크 로직 삭제.
    *   `_determine_phase`에서 요일 체크(`weekday() >= 5`) 로직 제거.
    *   타 스크립트 호환성을 위해 `is_trading_day` 함수는 항상 `True`를 반환하도록 단순화.

## 2. 현재 시스템 상태 및 주의 사항

*   **현재 날짜:** 2026년 1월 29일 기준 작업 완료.
*   **동작 모드:** `.env` 파일의 `KIS_MOCK` 값이나 DB 설정을 통해 모의/실전 모드 전환 가능.
*   **API 제한:** 토큰 발급은 1분당 1회 제한이 엄격함. 오류 발생 시 즉시 재시도하지 말고 최소 1분 이상의 간격을 두어야 함.
*   **자산 조회:** 휴장일에는 API 필드에 따라 일부 값이 0으로 올 수 있으나, 현재 보강된 로직은 순자산(`nass_amt`)을 참조하여 0원 표기 문제를 방지함.
*   **NXT 기능:** NXT 종목 데이터가 없으면 `POST /api/nxt/init-default`로 초기화 필요.

## 3. 향후 작업 제안 (Pending Tasks)

*   [ ] **NXT 종목 마스터 자동 갱신:** KIS 종목정보 파일 자동 다운로드 및 NXT 마스터 갱신
*   [ ] **API 타임아웃 처리 강화:** 현재 10초로 설정된 타임아웃 외에 네트워크 불안정 시의 재시도 로직 보강 필요.
*   [ ] **로그 파일 관리:** `auto_trading.log` 파일의 크기가 커질 경우를 대비한 로테이션 설정.
*   [ ] **실전 투자 검증:** 모의투자에서는 조회가 확인되었으나, 실전 투자 시의 시장 데이터 지연 현상에 대한 모니터링 필요.

## 4. 핵심 파일 정보
*   `auto_trading_strategy1.py`: 자동매매 핵심 엔진 (가장 많은 수정이 이루어짐)
*   `update_stock_prices.py`: Flask 백엔드 서버 (NXT API 포함)
*   `data/nxt_stocks.json`: NXT 거래 가능 종목 목록 저장 파일
*   `.env`: KIS API 키 및 계좌 정보 설정 파일
*   `mystock.db`: 전략 설정 및 매매 로그가 저장되는 SQLite DB

---
*Next Agent Note: 작업 시작 전 `docker compose logs -f backend`로 현재 엔진의 토큰 발급 상태를 먼저 확인하십시오.*
