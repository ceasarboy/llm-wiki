from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_\u4e00-\u9fff]+$')
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if not re.search(r'[A-Za-z]', v) or not re.search(r'[0-9]', v):
            raise ValueError('Password must contain letters and numbers')
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdateRole(BaseModel):
    role: str


class UserUpdateStatus(BaseModel):
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class UserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[UserResponse]
