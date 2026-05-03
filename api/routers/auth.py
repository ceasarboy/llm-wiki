from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from api.database import get_db
from api.models import User
from api.schemas.user import UserCreate, UserLogin, UserResponse, Token
from api.services.auth import AuthService
from api.services.log_service import LogService
from api.middleware.auth import get_current_active_user
from collections import defaultdict
import time

router = APIRouter(prefix="/auth", tags=["auth"])

_login_attempts = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 5


def _check_rate_limit(ip: str):
    now = time.time()
    attempts = _login_attempts[ip]
    _login_attempts[ip] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    _login_attempts[ip].append(now)


@router.post("/register", response_model=UserResponse)
def register(
    user_create: UserCreate,
    db: Session = Depends(get_db),
):
    if AuthService.get_user_by_username(db, user_create.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed",
        )
    if AuthService.get_user_by_email(db, user_create.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed",
        )
    
    user = AuthService.create_user(db, user_create)
    return user


@router.post("/login", response_model=Token)
def login(
    user_login: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    
    user = AuthService.authenticate_user(db, user_login.username, user_login.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    
    access_token = AuthService.create_access_token(data={"sub": user.username})
    
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    
    LogService.log_user_action(
        db=db,
        user_id=user.id,
        username=user.username,
        action="login",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user),
    )


@router.post("/logout")
def logout(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    LogService.log_user_action(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="logout",
        ip_address=request.client.host if request.client else None,
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user
