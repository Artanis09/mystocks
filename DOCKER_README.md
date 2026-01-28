# MyStocks Docker 배포 가이드

## 📦 구성 파일

- `Dockerfile` - 프로덕션용 통합 이미지 (프론트엔드 빌드 + 백엔드)
- `Dockerfile.frontend` - 프론트엔드 전용 (Vite React)
- `Dockerfile.backend` - 백엔드 전용 (Flask)
- `docker-compose.yml` - 개발용 (프론트엔드 + 백엔드 분리)
- `docker-compose.prod.yml` - 프로덕션용 (Nginx 포함 옵션)
- `nginx.conf` - Nginx 리버스 프록시 설정

## 🚀 빠른 시작

### 1. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 API 키들을 설정하세요
```

### 2. 개발 모드 실행

```bash
# 프론트엔드(3000) + 백엔드(5000) 분리 실행
docker compose up -d

# 로그 확인
docker compose logs -f
```

### 3. 프로덕션 모드 실행

```bash
# 통합 이미지로 실행 (포트 5000)
docker compose -f docker-compose.prod.yml up -d

# Nginx 포함 실행 (포트 80/443)
docker compose -f docker-compose.prod.yml --profile with-nginx up -d
```

## 🔧 서비스 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| Frontend | 3000 | Vite 개발 서버 |
| Backend | 5000 | Flask API 서버 |
| Nginx | 80/443 | 리버스 프록시 (옵션) |

## 📁 볼륨 마운트

- `/app/db` - SQLite 데이터베이스 (영속성 유지)
- `/app/data` - KRX 주식 가격 데이터 (Parquet)
- `/app/ml/models` - 학습된 ML 모델 파일

## ⚠️ 라이브러리 추가 및 업데이트 시 주의사항

새로운 라이브러리를 추가하거나 버전을 변경할 때, 도커 빌드 과정에서 `npm ci` 단계에서 오류가 발생할 수 있습니다 (lock file 불일치). 이 경우 다음 단계를 수행하세요:

1. **Lock 파일 업데이트**: 호스트 시스템에 Node.js가 없는 경우 도커를 사용하여 업데이트합니다.
   ```bash
   docker run --rm -v "${PWD}":/app -w /app node:20-alpine npm install --package-lock-only
   ```
2. **이미지 재빌드**:
   ```bash
   docker compose build frontend
   docker compose up -d frontend
   ```

마찬가지로 파이썬 패키지를 추가한 경우 `Dockerfile.backend` 빌드 시 자동으로 반영되도록 `requirements.txt`를 선제적으로 업데이트하세요.

- `./data` → `/app/data` - 주식 데이터 (Parquet)
- `db-data` → `/app/db` - SQLite 데이터베이스
- `./config.ini` → `/app/config.ini` - DART API 설정
- `./.env` → `/app/.env` - 환경 변수

## 🛠️ 관리 명령어

```bash
# 서비스 상태 확인
docker compose ps

# 로그 확인
docker compose logs -f backend
docker compose logs -f frontend

# 서비스 재시작
docker compose restart backend

# 서비스 중지
docker compose down

# 이미지 재빌드
docker compose build --no-cache

# 볼륨 포함 완전 삭제
docker compose down -v
```

## 🔒 환경 변수 설정 (.env)

```env
# Gemini API Key (Google AI Studio)
GEMINI_API_KEY=your_gemini_api_key_here

# 한국투자증권 KIS API 설정
KIS_APP_KEY=your_kis_app_key_here
KIS_APP_SECRET=your_kis_app_secret_here
KIS_ACCOUNT_NO=your_account_number_here
```

## 🌐 외부 접속

exe.dev VM에서 외부 접속을 허용하려면:

1. VM 방화벽에서 포트 3000, 5000 (또는 80/443) 허용
2. exe.dev 대시보드에서 포트 포워딩 설정

접속 URL:
- 프론트엔드: `http://<VM_IP>:3000`
- 백엔드 API: `http://<VM_IP>:5000/api/`

## ⚠️ 주의사항

1. **KIS API**: 한국투자증권 API 키가 없으면 실시간 주가 조회가 제한됩니다
2. **데이터**: `data/` 폴더에 기존 Parquet 데이터가 있어야 정상 동작합니다
3. **메모리**: ML 모델 (CatBoost, LightGBM) 사용 시 최소 4GB RAM 권장
