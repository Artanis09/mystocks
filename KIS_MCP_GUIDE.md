# 한국투자 코딩도우미 MCP 활용 가이드

이 문서는 한국투자증권 Open API(KIS API)를 효율적으로 사용하기 위해 설치된 MCP(Model Context Protocol) 서버의 활용 방법을 설명합니다.

## 1. MCP 개요
한국투자 코딩도우미 MCP는 KIS API의 복잡한 요청 파라미터와 헤더 설정을 AI 에이전트가 쉽게 이해하고 구현할 수 있도록 돕는 도구입니다. 최신 API 명세와 구현 예제 코드를 검색하고 읽어올 수 있습니다.

## 2. 주요 도구 사용법

### 2.1 API 검색 (`mcp_search_*`)
원하는 기능이 어떤 API를 사용하는지 모를 때 사용합니다.
- 예: `mcp_search_domestic_stock_api(query="삼성전자 잔량 조회", subcategory="기본시세")`
- 결과로 `function_name`, `api_name`, 그리고 샘플 코드가 있는 `url_main`을 반환합니다.

### 2.2 샘플 코드 읽기 (`mcp_read_source_code`)
검색된 API의 실제 구현 코드를 가져옵니다.
- 예: `mcp_read_source_code(url_main="https://github.com/.../inquire_price.py")`
- 반환된 코드는 KIS API 호출에 필요한 `tr_id`, `headers`, `params` 구조를 정확히 포함하고 있습니다.

## 3. 개발 환경 구성 (설정 완료)

현재 프로젝트는 다음과 같이 설정되어 있어 MCP와 함께 바로 개발이 가능합니다.

### 3.1 환경 변수 (`.env`)
프로젝트 루트의 `.env` 파일에 필요한 키가 미리 설정되어 있습니다.
- `KIS_MOCK`: `true` (모의투자), `false` (실전투자)
- `KIS_APP_KEY`, `KIS_APP_SECRET`: 모의투자 키
- `KIS_REAL_APP_KEY`, `KIS_REAL_APP_SECRET`: 실전투자 키

### 3.2 MCP 실행 스크립트
`mystocks/scripts/run_mcp_kis.sh`는 MCP 서버를 로컬에서 직접 실행할 때 `.env`의 설정값을 자동으로 `export`하여 실행해줍니다.

## 4. 새로운 API 적용 프로세스 (에이전트 가이드)

1. **상황**: "실시간 체결 통보 기능을 추가해줘"라는 요청을 받음.
2. **검색**: `mcp_search_domestic_stock_api(query="체결 통보", subcategory="실시간시세")` 호출.
3. **코드 확인**: 결과의 `url_main`을 사용하여 `mcp_read_source_code` 호출.
4. **로직 통합**: 가져온 샘플 코드의 `headers`와 `body` 구성을 참고하여 기존 `auto_trading_strategy1.py` 또는 `update_stock_prices.py`에 반영.
5. **검증**: `.env`의 모의투자 환경에서 먼저 테스트 후 배포.

---
**주의**: KIS API는 1분당 토큰 발급 횟수 제한(1회) 및 거래소별 호출 제한이 있으므로, 샘플 코드 적용 시 중복 토큰 발급을 피하고 기존 토큰 재사용 로직을 유지하십시오.
