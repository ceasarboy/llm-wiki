from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from api.database import get_db
from api.models import User
from api.schemas.user import UserResponse, UserUpdateRole, UserUpdateStatus, UserListResponse
from api.middleware.auth import get_current_active_user, require_role
from api.services.auth import AuthService
import secrets

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str = Query(None),
    is_active: bool = Query(None),
    search: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    query = db.query(User)
    
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        query = query.filter(
            (User.username.contains(search)) | (User.email.contains(search))
        )
    
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return UserListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[UserResponse.from_orm(u) for u in users],
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.put("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    role_update: UserUpdateRole,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own role")
    
    if role_update.role not in ["admin", "maintainer", "core", "general"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role",
        )
    
    user.role = role_update.role
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    status_update: UserUpdateStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own status")
    
    user.is_active = status_update.is_active
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """重置用户密码为随机临时密码"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    temp_password = secrets.token_urlsafe(12)
    user.password_hash = AuthService.get_password_hash(temp_password)
    db.commit()
    
    return {"success": True, "message": "密码已重置", "temp_password": temp_password}
