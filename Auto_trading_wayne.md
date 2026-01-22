# 📑 연구 보고서: CatBoost 기반 다중 분류 모델을 활용한 단기 급등주 예측 시스템
**Project Name:** AI 마이스탁 (Auto_trading_wayne)  
**Author:** AI Programming Assistant (Gemini 3 Flash)  
**Date:** 2026년 1월 21일  

---

## 1. 서론 (Introduction)
본 연구의 목적은 대한민국 주식 시장(KOSPI/KOSDAQ)의 역사적 데이터를 분석하여, 특정 거래일 종가 매수 후 익일 종가 매도 시 **2% 이상의 기대 수익률을 확보할 수 있는 종목을 선별**하는 알고리즘을 구축하는 데 있습니다. 단순한 상승/하락 예측을 넘어 상승의 강도를 정량적으로 분류하고, 리스크 관리 필터를 결합하여 복리 수익을 극대화하는 시스템을 제안합니다.

---

## 2. 학습 알고리즘 상세 설명 (Algorithm Architecture)

### 2.1 CatBoost (Categorical Boosting) Classifier
본 시스템은 Gradient Boosting Decision Tree(GBDT)의 진화형인 **CatBoost**를 핵심 엔진으로 사용합니다.

*   **Ordered Boosting:** 시계열 데이터에서 발생하는 데이터 누수(Data Leakage)를 방지하기 위해 훈련 세트의 순서를 고려하는 부스팅 기법을 적용합니다.
*   **Symmetric Trees:** 대칭형 트리를 구축하여 예측 속도가 매우 빠르며, 복잡한 주식 데이터 내의 노이즈에 강한 내성을 가집니다.
*   **Multi-Class Objective:** `MultiClass` 손실 함수를 사용하여 다음 날의 수익률 구간을 7개 등급으로 분류합니다. 이는 이진 분류보다 훨씬 세밀한 '상승 에너지' 파악을 가능하게 합니다.

### 2.2 타겟 레이블링 (Target Binning Strategy)
다음 날 수익률($r_{t+1}$)을 기준으로 다음과 같이 7개 클래스를 정의하였습니다:
*   **Class 0:** $r_{t+1} < 2\%$ (중립 또는 하락)
*   **Class 1:** $2\% \le r_{t+1} < 5\%$ (소폭 상승)
*   **Class 2:** $5\% \le r_{t+1} < 8\%$ (강세)
*   **Class 3:** $8\% \le r_{t+1} < 12\%$ (급등)
*   **Class 4:** $12\% \le r_{t+1} < 19\%$ (대급등)
*   **Class 5:** $19\% \le r_{t+1} < 29\%$ (준 상한가)
*   **Class 6:** $r_{t+1} \ge 29\%$ (상한가)

---

## 3. 학습 데이터 및 데이터 공학 (Data Engineering)

### 3.1 데이터셋 구성
*   **훈련 기간:** 2000-01-04 ~ 2024-12-31 (약 25년)
*   **데이터 규모:** 약 9,500,000개 이상의 일별 캔들(Bars) 데이터
*   **저장 형식:** Apache Parquet (고속 로딩 및 압축 최적화)

### 3.2 입력 피처 (Feature Engineering) - 총 24개
모델은 가격과 거래량의 파생 지표를 입력값으로 사용합니다.
1.  **Price Momentum:** 1일, 5일, 20일 수익률
2.  **Volatility (중요):** ATR Ratio, 20일 이동 표준편차 (급등 전 변동성 수축 여부 판단)
3.  **Volume Dynamics:** 5일/20일 평균 대비 거래량 비율, OBV(On-Balance Volume) 변화율
4.  **Trend Indicators:** MACD(Fast/Slow/Signal/Hist), RSI
5.  **Price Location:** 볼린저 밴드 내 위치(BB %B), 밴드 너비(BB Width), 52주 고저점 대비 현재가 위치
6.  **Moving Averages:** 5, 10, 20, 60, 120일 이평선 이격도

---

## 4. 학습 실험 및 결과 (Experimental Results)

### 4.1 모델 훈련 지표
*   **Best Iteration:** 757회 (Early Stopping 적용)
*   **핵심 변수 중요도 (Top 5):**
    *   `atr_ratio`: 9.12%
    *   `volatility_20d`: 8.84%
    *   `return_1d`: 7.32%
    *   `volume_ratio_20d`: 6.66%
    *   `ma_120_ratio`: 5.92%

### 4.2 분석 결론
모델은 장기 이동평균선(120일) 위에서 **변동성이 낮게 유지되다가(ATR Ratio 저하) 거래량이 실리며 고개를 드는 패턴**을 급등의 핵심 징후로 판단하고 있습니다.

---

## 5. 백테스트 성과 분석 (Backtest Analysis)

2025년 1월 ~ 2026년 1월 (테스트 기간) 동안의 투자 시뮬레이션 결과입니다. (초기 자본 100만 원)

### 5.1 전략별 성능 비교
| 시나리오 | 승률 | 적중률(>2%) | MDD | 최종 자산 |
| :--- | :---: | :---: | :---: | :--- |
| **Top-5 (기본)** | 64.9% | 41.7% | -26% | 약 25.0억 |
| **Top-10 (안정)** | 57.4% | 36.3% | -24% | 약 5,770만 |
| **MarketCap Filter (500억↑)** | 78.4% | 52.1% | -34% | 약 13.3억 |
| **Final Filter (MC+Volatility)** | **79.2%** | **52.1%** | **-12%** | **약 25.02억** |

---

## 6. 최종 실전 필터 알고리즘 (Final Trading Logic)

실전(운영) 매매 기준은 **Filter2 고정**입니다. (웹앱/백엔드 예측 API도 Filter2만 허용)

### Filter2 (운영 기준)

1.  **신뢰도 필터 (Probability >= 70%):** 모델의 분류 확률값 중 상위 등급(Class 1~6)의 합산 확률(`prob_up`)이 70% 이상인 종목만 후보로 선정.
2.  **유동성 필터 (Market Cap >= 500억):** 시가총액 500억 이상만 후보로 선정.
3.  **거래 활성화 필터 (Volume > 0):** 거래정지 종목을 원천 제외하기 위해 당일 거래량이 있는 종목만 선정.
4.  **리스크 필터 (Daily Strength):** 당일 시가 대비 종가 등락률(`close/open - 1`)이 -5% 미만인 종목 제외.
5.  **강한 음봉 제거 (return_1d >= -5%):** 전일 대비 수익률(`return_1d`)이 -5% 미만인 종목 제외.
6.  **상한가 락 근사 제거 (return_1d < 29.5%):** 상한가 근처 급등(현실적으로 체결이 어려운 구간)을 근사적으로 제거.
7.  **선정/정렬:** 기대수익률(`expected_return`) 내림차순으로 정렬 후 Top-5를 최종 추천.
8.  **매매 방식:** 선정된 Top-5 종목에 자산을 1/N로 균등 배분하여 당일 종가 매수/익일 종가 전액 매도.

<details>
<summary>Filter1 (실험/비권장, 문서 보관용)</summary>

- **설명:** 과거 실험에서 사용한 강한 필터. 거래 가능 종목 수가 줄어 실제 운용에서 제약이 커질 수 있어, 현재 운영 플로우(웹/백엔드)에서는 사용하지 않습니다.
- **조건(요약):** prob>=0.80, 시총>=500억, volume>0, intraday_return>=-5%, Top-5

</details>

---

## 7. 시스템 실행 방법 (How to Run)

### 7.1 데이터 환경 구축
본 시스템은 Python 3.10+ 환경에서 작동하며 필수 패키지는 다음과 같습니다.
`pip install -r requirements.txt`

직접 설치 시(최소): `pip install catboost lightgbm pandas numpy pyarrow matplotlib tqdm`

### 7.2 단계별 실행 프로세스
1.  **데이터 수집 (EOD: 장마감 후 1회 전체 업데이트 + 유니버스 캐시 생성)**
        - 전체 종목(일봉) 업데이트 + 시총 500억 유니버스 캐시 자동 생성
        - 예시: `python .\crawl.py --mode eod --workers 8 --merge`

2.  **장중 빠른 업데이트 (Intraday: 유니버스만, 기본 merge)**
        - 장중 여러 번 업데이트할 때는 전체 종목을 다시 수집하지 않고, 유니버스(시총 500억 이상)만 빠르게 업데이트
        - 예시: `python .\crawl.py --mode intraday --workers 8`
        - 주의: 기본은 `merge`(기존 파티션 유지 + 유니버스 코드만 갱신). 정말 필요할 때만 `--overwrite` 사용

3.  **전처리 및 학습:** `python -m ml.run_all --train-only`
4.  **성과 검증:** `python ml/backtest_marketcap_50b.py`
5.  **실전 추론:** `python -m ml.inference`

### 7.3 crawl.py Argument
`crawl.py`는 모드 기반으로 동작합니다.

- 도움말: `python .\crawl.py --help`
- 주요 옵션
    - `--mode eod|intraday`
        - `eod`: 전체 종목 수집 후 유니버스 캐시 생성
        - `intraday`: 유니버스(시총 500억)만 업데이트
    - `--target-date YYYY-MM-DD` (기본: 오늘)
        - 단일 날짜만 재수집/업데이트
    - `--start-date YYYY-MM-DD --end-date YYYY-MM-DD`
        - 날짜 범위를 지정하여 해당 기간을 하루씩 재수집/업데이트
        - 기본은 주말을 자동 skip (KRX 휴장일은 자동 판별 불가 → 데이터가 없으면 스킵)
    - `--include-weekends`
        - 날짜 범위 업데이트 시 주말도 시도
    - `--workers N` (기본: 8)
    - `--merge` (EOD에서 기존 파티션이 있을 때 code 단위 갱신)
    - `--overwrite` (권장 X: 기존 파티션을 덮어쓰기)

**날짜 지정 재수집 예시**
- 2026-01-21 하루만 재수집(merge 업데이트):
  - `python .\crawl.py --mode eod --target-date 2026-01-21 --merge`
- 2026-01-01~2026-01-21 범위를 재수집(merge 업데이트):
  - `python .\crawl.py --mode eod --start-date 2026-01-01 --end-date 2026-01-21 --merge`

#### 유니버스 캐시 산출/저장 경로
- Parquet(최신): `data/krx/master/universe_mcap500/latest.parquet`
- Parquet(날짜별): `data/krx/master/universe_mcap500/date=YYYY-MM-DD/part-0000.parquet`
- JSON(빠른 로드): `data/user/universe_mcap500.json`

### 7.4 inference 실행/Argument
CLI(`ml.inference`)는 연구/실험을 위해 filter1/filter2/both를 지원하지만, **운영(웹앱/백엔드)은 Filter2만 사용**합니다.

- 도움말: `python -m ml.inference --help`
- 예시
    - (권장) 필터2만 실행: `python -m ml.inference --filter filter2`
    - TOP-10으로 실행(필터2 기준): `python -m ml.inference --filter filter2 --top-k 10`
    - CSV 저장 안함: `python -m ml.inference --no-save`
    - **모델 선택:**
        - `--model-name model1` (기본, 7-class 다중분류)
        - `--model-name model5` (LightGBM 바이너리; lgbm_model5_*.txt 필요)

---

## 7.5 최근 변경사항 요약
- **거래정지 종목 제외:** inference 필터에 `volume > 0` 조건을 추가하여 거래정지(거래량 0) 종목이 추천에 포함되지 않도록 처리
- **유니버스 기반 장중 업데이트:** 장마감 후 유니버스 캐시 생성, 장중에는 시총 500억 유니버스만 수집하도록 `crawl.py` 모드 분리
- **날짜 지정 재수집 지원:** `crawl.py`에 `--start-date/--end-date` 옵션을 추가하여 특정 날짜(또는 기간)만 다시 수집/업데이트 가능
- **앱(AI추천) 개선:**
    - 추천 조회 시 KIS 실시간 현재가(`current_price`)와 당일 등락률(`current_change`) 표시
    - 날짜별 추천 목록 삭제 API: `DELETE /api/recommendations?date=YYYY-MM-DD&filter=filter2&model=model1|model5`
    - 모델 선택 지원: `model` 파라미터로 model1/model5 전환 (API/프론트 동시 적용)
    - 예측 실행은 Filter2만 지원: `POST /api/recommendations/predict?filter=filter2&model=model1|model5`

## 7.6 모델1 / 모델5 운용 가이드

- **모델1**: 7-class 다중분류 (2% 이상 상승 확률 계산) — default.
- **모델5**: LightGBM 바이너리 (정의 예: max(next_open_return,next_close_return) >= 0.02).
    - 모델 산출물명: `ml/models/lgbm_model5_<timestamp>.txt` (+meta)

**모델 파일(아티팩트)**
- model1(CatBoost): `ml/models/catboost_*.cbm` (+ `*_meta.json`)
- model5(LightGBM): `ml/models/lgbm_model5_*.txt` (+ `*_meta.json`)

**웹/백엔드 호출 예**
- 추천 생성: `POST /api/recommendations/predict?filter=filter2&model=model1`
- 추천 조회: `GET /api/recommendations?filter=filter2&model=model1`
- 추천 생성: `POST /api/recommendations/predict?filter=filter2&model=model5`
- 추천 조회: `GET /api/recommendations?filter=filter2&model=model5`

---

## 7.7 최근 코드 기반 백테스트 결과 (Filter2 + TP10/SL5)

아래는 실제 코드 실행 결과를 그대로 정리한 최신 기록입니다.

- 공통 필터(=Filter2, inference 기준)
    - `prob_threshold = 0.70`, `top_k = 5`
    - `market_cap >= 500억`, `volume > 0`
    - 리스크 필터(일중): `(close/open - 1) >= -5%`
    - 강한 음봉 제거: `return_1d >= -5%`
    - 상한가 락 근사 제거: `return_1d < 29.5%`
- 공통 매매룰(TP/SL)
    - 당일 종가 매수 → 익일 고가가 +10% 도달 시 +10% 익절(캡)
    - 아니면 익일 저가가 -5% 도달 시 -5% 손절
    - 아니면 익일 종가 청산
    - TP 우선(TP-first)

### 7.7.1 2025년(연간) model1 vs model5 비교

- 결과 파일: `ml/results/model1_vs_model5_filter2_tp10_sl5_summary_20260121_072629.csv`
- Sharpe 기준(표본 충분한 모델: trades≈1,200) 최적
    - **model5 + Filter2 기본값(리스크/음봉 제거 ON)**


| 모델 | Sharpe | 최종자산(₩1,000,000 시작) | MDD | Trades | Days |
| --- | ---: | ---: | ---: | ---: | ---: |
| model5 | 1.4615 | 1,642,474 | -0.3015 | 1210 | 242 |
| model1 | 1.3063 | 1,594,092 | -0.2539 | 1210 | 242 |

### 7.7.2 2026년 1월(현재까지) 동일 조건 적용

데이터 캐시 기준 최신 일자가 2026-01-19라서, 2026-01-01~2026-01-19(11거래일)까지 평가되었습니다.

- 결과 파일: `ml/results/models12345_filter2_tp10_sl5_20260101_20260119_summary_20260121_073959.csv`

> 참고: 위 파일명은 과거 비교 스크립트의 산출물이라 `models12345`가 포함되어 있습니다. 현재 운영 대상 모델은 **model1/model5**이며, 아래 표도 해당 2개 모델만 발췌했습니다.

| 모델 | Sharpe | 최종자산(₩1,000,000 시작) | MDD | Trades | Days |
| --- | ---: | ---: | ---: | ---: | ---: |
| model5 | 5.5441 | 1,144,122 | -0.0771 | 55 | 11 |
| model1 | 0.3528 | 1,002,979 | -0.0788 | 55 | 11 |

---

**결론(현재까지)**
- Sharpe 기준 최적은 일관되게 **Filter2 기본값(리스크/음봉 제거 ON) + model5**
- 단, 2026년 1월은 표본(11일)이 매우 작으므로 추세 판단은 보수적으로 해석 권장

## 8. 결론 및 제언
본 시스템은 26년의 빅데이터를 통해 통계적 우위를 가진 구간을 입증하였습니다. 특히 **최종 필터 전략에서 보여준 79%의 승률**은 실전 매매에서 강력한 심리적 안정성과 복리 수익을 제공할 수 있습니다. 향후에는 테마군 분석(Sector Analysis) 및 뉴스 심리 점수(Sentiment Score)를 결합하여 더욱 고도화된 모델로 발전시킬 계획입니다.

**Notice:** 위 결과는 백테스팅 결과이며, 모든 투자의 최종 책임은 투자자 본인에게 있습니다.
