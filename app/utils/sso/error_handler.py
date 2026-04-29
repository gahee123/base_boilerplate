"""
app/utils/sso/error_handler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HMG SSO 맞춤형 에러 응답 변환 유틸리티.

Java(VTDM) HmgErrorUtil + HmgSsoServiceImpl.getHealthcheckErrorMessage() 를
Python으로 이식한 것입니다.

Healthcheck 내부 에러 코드 및 SSO 인사 관리 상태를 전방위에 맞게 핸들링합니다.
"""
from app.utils.exceptions import AppException


class HmgHealthcheckError(AppException):
    """Healthcheck 오류 상황 공통 처리.

    Java(VTDM) HmgSsoServiceImpl.getHealthcheckErrorMessage() 기준:
    2xxx ~ 5xxx 상태 코드에 맞게 에러 코드와 사용자 친화적 메시지를 파생합니다.
    """
    def __init__(self, status_code: int) -> None:
        self.status_code = 500  # 서버 내부 혹은 설정 연동 오류인 경우가 대다수
        self.code_val = status_code
        self.error_code = f"HMG_HEALTH_ERR_{status_code}"
        
        # Java HmgSsoServiceImpl.getHealthcheckErrorMessage() 그대로 매핑
        msg_map = {
            2000: "body에 파라미터가 없음. 파라미터 확인 후 재시도",
            2100: "필수 파라미터가 1개 이상 없음. 파라미터 확인 후 재시도",
            3000: "등록되지 않은 회사. HMG SSO 관리자에게 문의",
            3100: "등록되지 않은 서비스. HMG SSO 관리자에게 문의",
            3200: "등록되지 않은 redirect_uri. HMG SSO 관리자에게 문의",
            3300: "서비스에 연동되지 않은 회사. HMG SSO 관리자에게 문의",
            4000: "사용된 state. 신규 값으로 재시도",
            5000: "알 수 없는 오류. HMG SSO 관리자에게 문의",
        }
        self.message = msg_map.get(
            status_code,
            f"HMG Healthcheck 에러 발생 (코드: {status_code})"
        )
        
        super().__init__(self.message)


class HmgAuthorizeError(AppException):
    """인가(Authorize) 도중 전달받은 인사 권한 오류 제어.

    Java(VTDM) HmgErrorUtil.AuthorizeResponse 기준:
    - authorize 에러: invalid_request, unsupported_response_type, invalid_scope, unauthorized_client, access_denied
    - access_denied 사유: HEALTHCHECK_NOT_DONE, BLOCKED, RETIRED, SUSPENDED, REST, EXPIRED
    """

    # Java: HmgErrorUtil.AuthorizeResponse 에러 코드 상수
    AUTHORIZE_ERROR_MAP = {
        "INVALID_REQUEST": "잘못된 요청입니다. 올바른 파라미터 이용 필요.",
        "UNSUPPORTED_RESPONSE_TYPE": "지원하지 않는 응답 타입입니다. 올바른 파라미터 이용 필요.",
        "INVALID_SCOPE": "유효하지 않은 범위입니다. 올바른 파라미터 이용 필요.",
        "UNAUTHORIZED_CLIENT": "인증되지 않은 클라이언트입니다. (HMG SSO 관리자에게 문의)",
    }

    # Java: HmgErrorUtil.AuthorizeResponse.AccessDeniedReason
    ACCESS_DENIED_MAP = {
        "HEALTHCHECK NOT DONE": (401, "네트워크 일시 오류로 사전 검증 과정이 무시되었습니다. 다시 로그인 화면으로 진입해주세요."),
        "BLOCKED": (403, "권한이 없는 사용자입니다."),
        "RETIRED": (403, "퇴직 처리된 계정입니다. 해당 서비스에 접근할 수 없습니다."),
        "SUSPENDED": (403, "현재 정직 상태의 계정입니다."),
        "REST": (403, "휴직 중인 계정의 접근이 제한됩니다."),
        "EXPIRED": (401, "사내망 비밀번호 변경 기한이 초과되었습니다. HMG 포탈에서 비밀번호를 최신화해주세요."),
    }

    def __init__(self, error_desc: str) -> None:
        error_upper = error_desc.upper().strip()
        self.error_code = f"HMG_AUTH_{error_upper.replace(' ', '_')}"

        # 1) 일반 authorize 에러 매칭
        if error_upper in self.AUTHORIZE_ERROR_MAP:
            self.status_code = 400
            self.message = self.AUTHORIZE_ERROR_MAP[error_upper]
        # 2) access_denied 세부 사유 매칭
        elif error_upper in self.ACCESS_DENIED_MAP:
            self.status_code, self.message = self.ACCESS_DENIED_MAP[error_upper]
        # 3) 알 수 없는 에러
        else:
            self.status_code = 403
            self.message = f"접근이 거부되었습니다. ({error_desc})"

        super().__init__(self.message)
