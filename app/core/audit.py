"""
app/core/audit.py
~~~~~~~~~~~~~~~~~
플러그형 감사 로그 핵심 엔진.

SQLAlchemy의 Session Event (before_flush)를 후킹하여, 모델 계층에 명시된
Auditable 대상을 감지하고 변경분을 자동으로 `audit_logs` 테이블에 적재합니다.
"""
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.event import listens_for
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit_log import AuditLog


class AuditableMixin:
    """
    이 Mixin을 상속받는 DB 모델은 Audit Log(감사 이력) 추적 대상이 됩니다.
    
    `__audit_exclude__` 속성에 컬럼명을 명시하면, 해당 컬럼의 변경 이력은
    시스템 내부 필드(updated_at)로 취급하여 무시합니다.
    """
    __audit_exclude__: set[str] = {"created_at", "updated_at", "deleted_at"}


def _serialize_object(obj: Any, keys: set[str]) -> dict[str, Any]:
    """객체의 지정된 컬럼 값들을 Dictionary로 직렬화합니다."""
    # SQLAlchemy 내부 상태 객체로 컬럼 값 조회
    state = inspect(obj)
    serializable = {}
    for key in keys:
        val = getattr(obj, key, None)
        # JSON 직렬화 불가 객체(UUID, datetime 등)는 문자열로 변환 처리
        serializable[key] = str(val) if val is not None else None
    return serializable


@listens_for(Session, "before_flush")
def receive_before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    """
    세션에 변경 사항이 Database로 밀어넣어지기 직전(flush)에 발생합니다.
    (주의: 이 이벤트 핸들러는 동기 코드로 동작해야 합니다.)
    """
    if not settings.AUDIT_LOG_ENABLED:
        return

    # User 정보를 컨텍스트에서 가져오는 부분은 FastAPI의 request contextvars 등을
    # 활용해야 완벽하지만, boilerplate 구조에서는 일단 시스템/로직 레벨 로깅에 집중합니다.
    # TODO: contextvars를 이용한 current_user 할당

    for obj in session.new:
        if isinstance(obj, AuditableMixin):
            _create_audit_record(session, obj, "INSERT", is_new=True)

    for obj in session.dirty:
        if isinstance(obj, AuditableMixin) and session.is_modified(obj):
            _create_audit_record(session, obj, "UPDATE", is_new=False)

    for obj in session.deleted:
        if isinstance(obj, AuditableMixin):
            _create_audit_record(session, obj, "DELETE", is_new=False)


def _create_audit_record(session: Session, obj: Any, action: str, is_new: bool) -> None:
    state = inspect(obj)
    mapper = state.mapper

    # Audit 대상 컬럼 필터링 (excluding fields)
    excluded = getattr(obj, "__audit_exclude__", set())
    all_columns = {col.key for col in mapper.columns}
    target_columns = all_columns - excluded

    old_data = None
    new_data = None

    if action == "INSERT":
        new_data = _serialize_object(obj, target_columns)
    elif action == "DELETE":
        old_data = _serialize_object(obj, target_columns)
    elif action == "UPDATE":
        old_temp = {}
        new_temp = {}
        # 변경된 속성만 기록하거나, 전체를 기록할 수 있음
        for attr in state.attrs:
            if attr.key in target_columns and attr.history.has_changes():
                # 삭제된 이전 값 추출
                if attr.history.deleted:
                    old_temp[attr.key] = str(attr.history.deleted[0])
                elif attr.history.unchanged:
                    old_temp[attr.key] = str(attr.history.unchanged[0])
                else:
                    old_temp[attr.key] = None

                # 새로 할당된 값 추출
                if attr.history.added:
                    new_temp[attr.key] = str(attr.history.added[0])
                else:
                    new_temp[attr.key] = None

        old_data = old_temp if old_temp else None
        new_data = new_temp if new_temp else None

        # 실제 값이 변한게 없으면 건너뜀
        if not old_data and not new_data:
            return

    # obj.id가 아직 생성되지 않은 상태일 수 있으므로(INSERT의 경우 UUID 기본값이지만 DB시퀀스라면 None임)
    # 여기서는 UUID default=uuid4 할당으로 인해 id가 존재함.
    target_id = str(getattr(obj, "id", "UNKNOWN"))

    audit_log = AuditLog(
        target_table=mapper.local_table.name,
        target_id=target_id,
        action=action,
        old_data=old_data,
        new_data=new_data,
        # user_id=None # 나중에 추가
    )
    session.add(audit_log)
