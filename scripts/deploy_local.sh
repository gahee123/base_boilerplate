#!/bin/bash
# ==============================================================================
# 로컬 개발/테스트 환경 원클릭 배포 스크립트 (Linux / Mac / WSL)
# ==============================================================================
set -e

echo "🚀 [1/4] 환경 변수 확인 중..."
if [ ! -f ".env" ]; then
    echo "   .env 파일이 없습니다. .env.example을 복사합니다."
    cp .env.example .env
fi

echo "🐳 [2/4] Docker Compose 빌드 및 기동..."
docker compose up -d --build

echo "⏳ [3/4] 데이터베이스 컨테이너 준비 대기 중 (5초)..."
sleep 5

echo "🛠️ [4/4] 데이터베이스 마이그레이션 실행 중 (Alembic)..."
docker compose exec -T app alembic upgrade head

echo ""
echo "✅ 배포 완료! 애플리케이션이 로컬에 구동되었습니다."
echo "   - API 서버: http://localhost:8000"
echo "   - API 문서(Swagger): http://localhost:8000/docs"
echo "   - 로그 확인: docker compose logs -f app"
