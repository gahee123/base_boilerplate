"""
app/models/enums.py
~~~~~~~~~~~~~~~~~~~
애플리케이션 전역에서 사용되는 열거형(Enum) 정의.
순환 참조를 방지하기 위해 별도의 파일로 관리합니다.
"""
import enum

class UserRole(str, enum.Enum):
    """사용자 역할 Enum (5단계 RBAC)"""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    USER = "user"
    PERMISSION_REQUESTED = "permission_requested"
    PERMISSION_REQUIRED = "permission_required"

class HmgSite(str, enum.Enum):
    """HMG 계열사 회사코드"""
    HMC = "H101_W"
    KMC = "K101_W"
    HAE = "H199_W"
    HKMC = "HKMC_W"
    ALL = "ALL"
