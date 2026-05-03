from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class UserLogResponse(BaseModel):
    id: int
    user_id: int
    username: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SystemLogResponse(BaseModel):
    id: int
    level: str
    module: str
    action: str
    message: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LogSearchQuery(BaseModel):
    q: Optional[str] = None
    type: str = "all"
    page: int = 1
    page_size: int = 20


class UserLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[UserLogResponse]


class SystemLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[SystemLogResponse]
