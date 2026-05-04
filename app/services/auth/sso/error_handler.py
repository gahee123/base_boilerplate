"""
app/services/auth/sso/error_handler.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HMG SSO 에러 핸들러.
"""
from app.utils.exceptions import AppException


class HmgHealthcheckError(AppException):
    _SPEC_MAP = {
        0:    (503, "SSO_UNAVAILABLE",     "HMG SSO 서버에 연결할 수 없습니다."),
        2000: (500, "SSO_INVALID_REQUEST", "요청 처리 중 오류가 발생했습니다."),
        2100: (500, "SSO_INVALID_REQUEST", "요청 처리 중 오류가 발생했습니다."),
        3000: (503, "SSO_CONFIG_ERROR",    "인증되지 않은 클라이언트입니다."),
        3100: (503, "SSO_CONFIG_ERROR",    "인증되지 않은 클라이언트입니다."),
        3200: (503, "SSO_CONFIG_ERROR",    "인증되지 않은 클라이언트입니다."),
        3300: (503, "SSO_CONFIG_ERROR",    "인증되지 않은 클라이언트입니다."),
        4000: (503, "SSO_UNAVAILABLE",     "HMG SSO 서버에 연결할 수 없습니다."),
        5000: (502, "SSO_UNAVAILABLE",     "알 수 없는 오류가 발생하였습니다."),
    }

    def __init__(self, sso_status: int) -> None:
        http_status, error_code, message = self._SPEC_MAP.get(
            sso_status,
            (502, "SSO_UNAVAILABLE", "알 수 없는 오류가 발생하였습니다."),
        )
        self.status_code = http_status
        self.error_code = error_code
        self.message = message
        self.sso_status = sso_status
        super().__init__(self.message)


class HmgAuthorizeError(AppException):
    AUTHORIZE_ERROR_MAP = {
        "INVALID_REQUEST": "잘못된 요청입니다.",
        "UNSUPPORTED_RESPONSE_TYPE": "지원하지 않는 응답 타입입니다.",
        "INVALID_SCOPE": "유효하지 않은 범위입니다.",
        "UNAUTHORIZED_CLIENT": "인증되지 않은 클라이언트입니다.",
    }
    ACCESS_DENIED_MAP = {
        "HEALTHCHECK NOT DONE": (401, "사전 검증 과정이 무시되었습니다."),
        "BLOCKED": (403, "권한이 없는 사용자입니다."),
        "RETIRED": (403, "퇴직 처리된 계정입니다."),
        "SUSPENDED": (403, "현재 정직 상태의 계정입니다."),
        "REST": (403, "휴직 중인 계정의 접근이 제한됩니다."),
        "EXPIRED": (401, "비밀번호 변경 기한이 초과되었습니다."),
    }

    def __init__(self, error_desc: str) -> None:
        error_upper = error_desc.upper().strip()
        self.error_code = f"HMG_AUTH_{error_upper.replace(' ', '_')}"
        if error_upper in self.AUTHORIZE_ERROR_MAP:
            self.status_code = 400
            self.message = self.AUTHORIZE_ERROR_MAP[error_upper]
        elif error_upper in self.ACCESS_DENIED_MAP:
            self.status_code, self.message = self.ACCESS_DENIED_MAP[error_upper]
        else:
            self.status_code = 403
            self.message = f"접근이 거부되었습니다. ({error_desc})"
        super().__init__(self.message)
