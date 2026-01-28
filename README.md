

# 마이스탁 (MyStocks) - AI 기반 주식 분석 및 추천 시스템

스마트한 주식 발굴 및 분석 일지 서비스입니다. AI 기반의 종목 추천과 전문적인 캔들 차트를 활용한 대시보드를 제공합니다.

## ✨ 최근 업데이트
- **AI 추천 페이지 고도화**: 트레이딩 UI를 제거하고 분석 데이터 중심의 쾌적한 화면 제공
- **차트 엔진 교체**: 기존 Recharts에서 **Lightweight Charts**로 교체하여 전문적인 차트 분석 기능 강화
- **차트 렌더링 수정**: 음봉의 바디 표현 오류 수정 및 최신 날짜 자동 스크롤 기능 추가

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`

### 서버실행
 C:/Workspace/마이스탁/.venv/Scripts/python.exe update_stock_prices.py

## 데이터 정보
이 프로젝트에서 사용하는 주식 데이터의 상세 구조와 기간은 [DATA_README.md](DATA_README.md)를 참고하세요.

## 사용법 및 매뉴얼 (User Manual)
**프로젝트 설정, API 키 입력 위치, ML 모델 학습 등 상세한 사용 방법은 [USER_MANUAL.md](USER_MANUAL.md) 파일을 참고하세요.**
