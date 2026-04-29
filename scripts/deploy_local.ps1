# ==============================================================================
# 로컬 개발/테스트 환경 원클릭 배포 스크립트 (Windows PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"

Write-Host "🚀 [1/4] 환경 변수 확인 중..." -ForegroundColor Cyan
if (-Not (Test-Path ".env")) {
    Write-Host "   .env 파일이 없습니다. .env.example을 복사합니다." -ForegroundColor Yellow
    Copy-Item ".env.example" -Destination ".env"
}

Write-Host "🐳 [2/4] Docker Compose 빌드 및 기동..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "⏳ [3/4] 데이터베이스 컨테이너 준비 대기 중..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

Write-Host "🛠️ [4/4] 데이터베이스 마이그레이션 실행 중 (Alembic)..." -ForegroundColor Cyan
docker compose exec app alembic upgrade head

Write-Host ""
Write-Host "✅ 배포 완료! 애플리케이션이 로컬에 구동되었습니다." -ForegroundColor Green
Write-Host "   - API 서버: http://localhost:8000"
Write-Host "   - API 문서(Swagger): http://localhost:8000/docs"
Write-Host "   - 로그 확인: docker compose logs -f app"
