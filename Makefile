.PHONY: up down logs migrate-gen migrate test lint setup clean

# ── 개발 환경 ────────────────────────────────────────────────

## Docker Compose 기동
up:
	docker compose up -d

## Docker Compose 중지
down:
	docker compose down

## 앱 로그 실시간 확인
logs:
	docker compose logs -f app

## 전체 초기화 (볼륨 포함 삭제)
clean:
	docker compose down -v

# ── DB 마이그레이션 ──────────────────────────────────────────

## 마이그레이션 파일 생성 (예: make migrate-gen msg="add posts table")
migrate-gen:
	docker compose exec app alembic revision --autogenerate -m "$(msg)"

## 마이그레이션 실행 (최신 버전까지 업그레이드)
migrate:
	docker compose exec app alembic upgrade head

## 마이그레이션 1단계 롤백
migrate-down:
	docker compose exec app alembic downgrade -1

# ── 테스트 & 린트 ────────────────────────────────────────────

## 테스트 실행
test:
	docker compose exec app pytest -v

## 테스트 커버리지
test-cov:
	docker compose exec app coverage run -m pytest -v
	docker compose exec app coverage report -m

## 코드 린트 (Ruff & MyPy)
lint:
	docker compose exec app ruff check .
	docker compose exec app mypy .

## 코드 자동 포맷
format:
	docker compose exec app ruff check --fix .

# ── 셋업 ─────────────────────────────────────────────────────

## 최초 셋업 (Docker 빌드 → 기동 → DB 마이그레이션)
setup:
	docker compose up -d --build
	@echo "⏳ DB 준비 대기 중..."
	@sleep 5
	$(MAKE) migrate
	@echo ""
	@echo "✅ 셋업 완료!"
	@echo "📖 Swagger UI: http://localhost:8000/docs"
	@echo "📖 ReDoc:      http://localhost:8000/redoc"

# ── Kubernetes ──────────────────────────────────────────────

## K8s 환경 배포
k8s-deploy:
	@bash scripts/deploy_k8s.sh

## K8s 리소스 상태 확인
k8s-status:
	kubectl get all -n fastapi-boilerplate

## K8s 앱 로그 실시간 확인 (가장 최근 생성된 앱 파드 로그)
k8s-logs:
	kubectl logs -f -l app.kubernetes.io/name=fastapi-boilerplate -n fastapi-boilerplate --max-log-requests 1
