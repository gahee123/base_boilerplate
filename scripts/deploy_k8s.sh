#!/bin/bash

# ==============================================================================
# Kubernetes 기반 프로덕션 배포 자동화 스크립트 (Helm Chart 연동)
# ==============================================================================

set -e # 오류 발생 시 즉시 중단

PROJECT_NAME="fastapi-boilerplate"
NAMESPACE="fastapi-boilerplate"
RELEASE_NAME="my-fastapi-app"
CHART_DIR="helm/fastapi-boilerplate"
IMAGE_NAME="your-registry/${PROJECT_NAME}"
TAG=$(date +%Y%m%d%H%M%S)

echo "🚀 [1/4] 최신 프로덕션 Docker 이미지 빌드 시작... (Tag: ${TAG})"
# 프로덕션 stage(runtime)만 타겟으로 빌드합니다.
docker build --no-cache --target runtime -t "${IMAGE_NAME}:${TAG}" -t "${IMAGE_NAME}:latest" .

# echo "📤 [2/4] 컨테이너 레지스트리에 이미지 푸시 중..."
    # docker push "${IMAGE_NAME}:${TAG}"
    # docker push "${IMAGE_NAME}:latest"

# [Local Test Only] Kind 클러스터에 이미지 로드
kind load docker-image "${IMAGE_NAME}:${TAG}" --name fastapi-test || true


echo "☸️ [2.5/4] 인프라 의존성(DB, Redis, Secrets) 설정 중..."
# 네임스페이스가 없으면 생성
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# 기본 시크릿 생성 (없을 경우에만)
kubectl create secret generic app-secrets \
  --namespace ${NAMESPACE} \
  --from-literal=JWT_SECRET_KEY='fallback-secret-key-change-me' \
  --from-literal=DB_PASSWORD='postgres-password' \
  --dry-run=client -o yaml | kubectl apply -f -

# PostgreSQL & Redis 배포
kubectl apply -f k8s/db.yaml -n ${NAMESPACE}
kubectl apply -f k8s/redis.yaml -n ${NAMESPACE}

echo "   - 인프라 리소스 적용 완료."

echo "☸️ [3/4] Kubernetes Helm Chart 배포 진행 중..."
echo "   - 대상 네임스페이스: ${NAMESPACE}"
echo "   - 릴리즈 명: ${RELEASE_NAME}"

# Helm을 통해 Install 혹은 Upgrade 실행 (네임스페이스가 없으면 생성)
helm upgrade --install ${RELEASE_NAME} ${CHART_DIR} \
  --namespace ${NAMESPACE} \
  --create-namespace \
  --set image.repository="${IMAGE_NAME}" \
  --set image.tag="${TAG}"

echo "✅ [4/4] Kubernetes(Helm) 배포 명령이 전달되었습니다."
echo "⏳ 배포 안정화 대기 중 (Rollout Status)..."
kubectl rollout status deployment/${RELEASE_NAME}-fastapi-boilerplate -n ${NAMESPACE} --timeout=300s
kubectl rollout status deployment/${RELEASE_NAME}-fastapi-boilerplate-worker -n ${NAMESPACE} --timeout=300s

echo "🎉 모든 배포 프로세스가 완료되었습니다!"
echo "상태 확인: kubectl get pods -n ${NAMESPACE}"
