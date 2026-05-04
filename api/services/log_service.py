import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from api.models import UserLog, SystemLog

SENSITIVE_FIELDS = {"password", "api_key", "api_key_masked", "secret", "sign",
                    "token", "access_token", "refresh_token", "authorization"}


def _sanitize_details(details: Optional[dict]) -> Optional[dict]:
    if not details:
        return details
    sanitized = {}
    for k, v in details.items():
        k_lower = k.lower()
        if any(s in k_lower for s in SENSITIVE_FIELDS):
            sanitized[k] = "***FILTERED***"
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_details(v)
        else:
            sanitized[k] = v
    return sanitized


class LogService:
    @staticmethod
    def log_user_action(
        db: Session,
        user_id: int,
        username: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserLog:
        log = UserLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(_sanitize_details(details)) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def log_system_event(
        db: Session,
        level: str,
        module: str,
        action: str,
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> SystemLog:
        log = SystemLog(
            level=level,
            module=module,
            action=action,
            message=message,
            details=json.dumps(_sanitize_details(details)) if details else None,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_user_logs(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ):
        query = db.query(UserLog)
        
        if user_id:
            query = query.filter(UserLog.user_id == user_id)
        if action:
            query = query.filter(UserLog.action == action)
        if start_date:
            query = query.filter(UserLog.created_at >= start_date)
        if end_date:
            query = query.filter(UserLog.created_at <= end_date)
        if keyword:
            query = query.filter(UserLog.details.contains(keyword))
        
        total = query.count()
        logs = query.order_by(desc(UserLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()
        
        return logs, total

    @staticmethod
    def get_system_logs(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        level: Optional[str] = None,
        module: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ):
        query = db.query(SystemLog)
        
        if level:
            levels = [l.strip() for l in level.split(',')]
            if len(levels) == 1:
                query = query.filter(SystemLog.level == levels[0])
            else:
                query = query.filter(SystemLog.level.in_(levels))
        if module:
            query = query.filter(SystemLog.module == module)
        if start_date:
            query = query.filter(SystemLog.created_at >= start_date)
        if end_date:
            query = query.filter(SystemLog.created_at <= end_date)
        if keyword:
            query = query.filter(
                (SystemLog.message.contains(keyword)) | (SystemLog.details.contains(keyword))
            )
        
        total = query.count()
        logs = query.order_by(desc(SystemLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()
        
        return logs, total
