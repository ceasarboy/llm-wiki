from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from api.database import get_db
from api.models import User
from api.schemas.log import UserLogListResponse, SystemLogListResponse, UserLogResponse, SystemLogResponse
from api.services.log_service import LogService
from api.middleware.auth import require_role

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/user", response_model=UserLogListResponse)
def get_user_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int = Query(None),
    action: str = Query(None),
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    keyword: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    logs, total = LogService.get_user_logs(
        db=db,
        page=page,
        page_size=page_size,
        user_id=user_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
    )
    
    return UserLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[UserLogResponse.from_orm(log) for log in logs],
    )


@router.get("/system", response_model=SystemLogListResponse)
def get_system_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    level: str = Query(None),
    module: str = Query(None),
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    keyword: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    logs, total = LogService.get_system_logs(
        db=db,
        page=page,
        page_size=page_size,
        level=level,
        module=module,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
    )
    
    return SystemLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[SystemLogResponse.from_orm(log) for log in logs],
    )


@router.get("/search")
def search_logs(
    q: str = Query(None),
    type: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    results = {}
    
    if type in ["user", "all"]:
        user_logs, user_total = LogService.get_user_logs(
            db=db, page=page, page_size=page_size, keyword=q
        )
        results["user_logs"] = {
            "total": user_total,
            "items": [UserLogResponse.from_orm(log) for log in user_logs],
        }
    
    if type in ["system", "all"]:
        system_logs, system_total = LogService.get_system_logs(
            db=db, page=page, page_size=page_size, keyword=q
        )
        results["system_logs"] = {
            "total": system_total,
            "items": [SystemLogResponse.from_orm(log) for log in system_logs],
        }
    
    return results
