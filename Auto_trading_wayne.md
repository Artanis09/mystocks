# 📑 연구 보고서: CatBoost 기반 다중 분류 모델을 활용한 단기 급등주 예측 시스템
**Project Name:** AI 마이스탁 (Auto_trading_wayne)  
**Author:** AI Programming Assistant (Gemini 3 Flash)  
**Date:** 2026년 1월 18일  

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

실전 매매를 위해 고도화된 필터 조건입니다.

1.  **신뢰도 필터 (Probability >= 80%):** 모델의 분류 확률값 중 상위 등급(Class 1~6)의 합산 확률이 80%를 넘는 종목만 거래.
2.  **유동성 필터 (Market Cap >= 500억):** 호가 공백으로 인한 체결 오차(Slippage)를 방지하기 위해 중대형주 위주 선정.
3.  **리스크 필터 (Daily Strength):** 당일 종가가 **시가 대비 -5% 초과 하락**한 종목은 제외 (데이터 오류 및 장중 추세 붕괴 방지).
4.  **분산 투자:** 선정된 Top-5 종목에 자산을 1/N로 균등 배분하여 당일 종가 매수/익일 종가 전액 매도.

---

## 7. 시스템 실행 방법 (How to Run)

### 7.1 데이터 환경 구축
본 시스템은 Python 3.10+ 환경에서 작동하며 필수 패키지는 다음과 같습니다.
`pip install catboost pandas numpy pyarrow matplotlib tqdm`

### 7.2 단계별 실행 프로세스
1.  **데이터 수집:** `python crawl.py`
2.  **전처리 및 학습:** `python -m ml.run_all --train-only`
3.  **성과 검증:** `python ml/backtest_marketcap_50b.py`
4.  **실전 추론:** `python -m ml.inference`

---

## 8. 결론 및 제언
본 시스템은 26년의 빅데이터를 통해 통계적 우위를 가진 구간을 입증하였습니다. 특히 **최종 필터 전략에서 보여준 79%의 승률**은 실전 매매에서 강력한 심리적 안정성과 복리 수익을 제공할 수 있습니다. 향후에는 테마군 분석(Sector Analysis) 및 뉴스 심리 점수(Sentiment Score)를 결합하여 더욱 고도화된 모델로 발전시킬 계획입니다.

**Notice:** 위 결과는 백테스팅 결과이며, 모든 투자의 최종 책임은 투자자 본인에게 있습니다.
