# 🔐 Kubernetes Secrets 가이드 (TASK-043)

보안상 민감한 정보(JWT Secret, DB 비밀번호 등)는 `ConfigMap`이 아닌 `Secret`으로 관리해야 합니다.

## 1. Secret 생성 명령어 (CLI)

아래 명령어를 사용하여 네임스페이스에 비밀 값을 직접 등록합니다.

```bash
kubectl create secret generic app-secrets \
  --namespace fastapi-boilerplate \
  --from-literal=JWT_SECRET_KEY='your-very-secure-secret-key' \
  --from-literal=DB_PASSWORD='postgres-password'
```

## 2. 매니페스트 예시 (YAML)

파일로 관리할 경우 반드시 암호화(SealedSecrets 등)하여 저장하십시오.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
  namespace: fastapi-boilerplate
type: Opaque
data:
  # base64 encoded values
  JWT_SECRET_KEY: <base64-encoded-key>
  DB_PASSWORD: <base64-encoded-password>
```

## 3. 적용 확인

```bash
kubectl get secret app-secrets -n fastapi-boilerplate -o yaml
```
