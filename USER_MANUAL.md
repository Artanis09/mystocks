# MyStock AI Trading System - 사용자 매뉴얼 (User Manual)

이 문서는 MyStock 프로젝트의 설치, 설정, 실행 및 데이터 관리에 대한 상세 가이드를 제공합니다.

---

## 🏗️ 1. 사전 준비 및 설치 (Installation)

### 1-1. Python 환경 설정
Python 3.10 이상 사용을 권장합니다.

```bash
# 가상환경 생성 (최초 1회)
python -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate

# 가상환경 활성화 (Mac/Linux)
source .venv/bin/activate
```

### 1-2. 필수 패키지 설치 (Requirements)
`requirements.txt` 파일을 통해 필요한 라이브러리를 일괄 설치합니다.

```bash
pip install -r requirements.txt
```

---

## 🔑 2. 보안 및 환경 설정 (.env)

**⚠️ 보안 주의:** API Key는 절대 Git 저장소(Github 등)에 업로드하지 마세요. 이 프로젝트는 `.env` 파일을 통해 키를 안전하게 관리합니다.

### 2-1. `.env` 파일 생성
프로젝트 최상위 경로(루트)에 `.env` 파일을 생성하고 아래 내용을 본인의 키로 채워 작성하세요.

```ini
# 한국투자증권(KIS) API 설정
KIS_APP_KEY=본인의_KIS_APP_KEY
KIS_APP_SECRET=본인의_KIS_APP_SECRET

# DART(전자공시시스템) API 설정
DART_API_KEY=본인의_DART_API_KEY
```

*   **참고:** `kis_token.json` 파일은 API 호출 시 자동 생성되는 임시 토큰 파일이므로 직접 생성할 필요가 없습니다.

---

## 🔄 3. 데이터 파이프라인 및 실행 순서 (Workflow)

시스템 구동을 위해서는 **[데이터 수집] -> [AI 예측] -> [웹 서버 실행]** 의 순서를 권장합니다.

### Step 1. 데이터 수집: `crawl.py`
매일 장 마감 후 실행하여 최신 데이터를 로컬 스토리지(`data`)에 업데이트합니다.

```bash
python crawl.py
```

> **📋 `crawl.py` 작동 원리 (상세)**
>
> 1.  **증분 업데이트 (Incremental Update)**
>     *   마지막으로 저장된 데이터 날짜를 확인합니다.
>     *   마지막 날짜가 '어제' 이전이라면, 빠진 날짜(Gap)만큼 데이터를 순차적으로 수집하여 쌓습니다.
>
> 2.  **오늘 데이터 갱신 (Overwrite)**
>     *   프로그램 실행 시점이 '오늘'이라면, 장 중이거나 장 마감 후 여부에 상관없이 **오늘 자 데이터를 다시 수집하여 기존 데이터를 덮어씁니다.**
>     *   이를 통해 장 마감 후 최종 확정된 종가(Close Price)를 확실하게 업데이트할 수 있습니다.
>     *   따라서 `crawl.py`는 하루에 여러 번 실행해도 데이터가 꼬이지 않고 안전하게 최신화됩니다.

### Step 2. AI 모델 예측: `ml/inference.py`
수집된 최신 데이터를 바탕으로 내일 상승할 확률이 높은 종목을 예측합니다.

```bash
python ml/inference.py
```
*   **기능:** 전체 종목을 대상으로 AI 모델이 상승 확률을 계산하고, 상위 추천 종목을 DB(`stock.db`)에 저장합니다.
*   **결과 확인:** 실행 후 웹 대시보드의 '추천 종목' 탭에서 결과를 볼 수 있습니다.
*   **모델 학습 (`ml/train.py`):** 기본 모델이 포함되어 있으므로 평소에는 실행할 필요가 없습니다. 모델 성능을 개선하거나 새 데이터를 학습시키고 싶을 때만 `python ml/train.py`를 실행하세요.

### Step 3. 웹 애플리케이션 실행
백엔드와 프론트엔드 서버를 모두 실행하여 서비스를 이용합니다.

**3-1. 백엔드 (Flask) 실행**
```bash
python update_stock_prices.py
```
*   **포트:** 5000 (`http://localhost:5000`)
*   **역할:** API 서버, DB 입출력 담당, KIS API를 통한 실시간 시세 및 자산 정보 조회

**3-2. 프론트엔드 (React/Vite) 실행**
새로운 터미널 창을 열고 실행하세요.
```bash
npm run dev
```
*   **포트:** 3000 (`http://localhost:3000`)
*   **역할:** 사용자 인터페이스 (대시보드, 차트, 매매입력)

---

## 📂 4. 폴더 및 데이터 구조 설명

```text
마이스탁/
├── .env                  # (필수) API Key 관리 파일 (Git 무시됨)
├── crawl.py              # 데이터 수집 스크립트
├── update_stock_prices.py # 백엔드 서버 메인 파일
├── requirements.txt      # 파이썬 패키지 목록
├── data/                 # 로컬 데이터 저장소 (Parquet 파일)
│   └── krx/
│       ├── daily_price/  # (구버전) 일별 주가 데이터
│       └── bars/         # (신버전) 차트용 OHLCV 데이터 (날짜별 파티셔닝)
├── ml/                   # 머신러닝 관련 코드
│   ├── inference.py      # AI 추천 실행 스크립트
│   ├── train.py          # 모델 학습 스크립트
│   └── models/           # 학습 완료된 CatBoost 모델 파일 (.cbm)
└── instance/
    └── stock.db          # SQLite 데이터베이스 (사용자 매매일지, 추천 이력 등)
```

---

## ❓ 5. 자주 묻는 질문 (Troubleshooting)

**Q1. `crawl.py` 실행 시 "No module named dotenv" 에러가 발생합니다.**
> A. `requirements.txt`에 포함된 패키지가 설치되지 않았습니다. 아래 명령어를 실행하세요.
> ```bash
> pip install -r requirements.txt
> ```

**Q2. 오늘 AI 추천 종목이 보이지 않습니다.**
> A. 다음 단계를 확인해 보세요.
> 1. `crawl.py`를 실행하여 오늘 날짜의 데이터 폴더(`data/krx/bars/date=YYYY-MM-DD`)가 생성되었는지 확인합니다.
> 2. `ml/inference.py`를 실행하여 에러 없이 완료되었는지 확인합니다.
> 3. 웹 화면에서 페이지를 새로고침하거나 상단의 "AI 수동 실행" 버튼을 눌러보세요.

**Q3. 실시간 가격이 0원으로 표시됩니다.**
> A. `.env` 파일에 KIS API Key가 올바르게 입력되었는지 확인하세요. 또한 장 운영 시간이 아니라면 전일 종가가 표시되어야 하는데, API 호출 한도를 초과했거나 모의투자/실전투자 도메인 설정이 잘못되었을 수 있습니다.

**Q4. Git에 코드를 올릴 때 주의할 점이 있나요?**
> A. 네, `.env` 파일과 `kis_token.json` 파일, 그리고 `data/` 폴더 안의 대용량 데이터들은 `.gitignore`에 등록되어 있어 올라가지 않습니다. 이 설정 파일을 유지해 주세요.
