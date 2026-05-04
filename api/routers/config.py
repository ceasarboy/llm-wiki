"""系统配置 API"""

from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.dependencies import (
    RAGTEST_DIR,
    get_db_ctx,
)
from api.middleware.auth import require_role
from api.models import User

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_FILE = RAGTEST_DIR / "config.yaml"


class LLMConfig(BaseModel):
    api_url: str
    model: str
    api_key: str
    temperature: float = 0.3
    max_tokens: int = 8192
    timeout: int = 300


class SystemConfig(BaseModel):
    vault_root: str
    raw_dir: str
    wiki_dir: str
    work_dir: str
    index_dir: str
    llm: LLMConfig


class ConfigUpdateRequest(BaseModel):
    vault_root: Optional[str] = None
    raw_dir: Optional[str] = None
    wiki_dir: Optional[str] = None
    llm: Optional[LLMConfig] = None


@router.get("", response_model=SystemConfig)
async def get_config(
    current_user: User = Depends(require_role(["admin"])),
):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    paths = config.get("paths", {})
    llm = config.get("llm", {})
    api_key = llm.get("api_key", "")
    masked_key = (api_key[:4] + "****") if len(api_key) > 4 else "****"
    return SystemConfig(
        vault_root=paths.get("vault_root", ""),
        raw_dir=paths.get("raw_dir", ""),
        wiki_dir=paths.get("wiki_dir", ""),
        work_dir=paths.get("work_dir", ""),
        index_dir=paths.get("index_dir", ""),
        llm=LLMConfig(
            api_url=llm.get("api_url", ""),
            model=llm.get("model", ""),
            api_key=masked_key,
            temperature=llm.get("temperature", 0.3),
            max_tokens=llm.get("max_tokens", 8192),
            timeout=llm.get("timeout", 300),
        ),
    )


class ConfigUpdateResponse(BaseModel):
    success: bool
    message: str


@router.put("", response_model=ConfigUpdateResponse)
async def update_config(
    update: ConfigUpdateRequest,
    current_user: User = Depends(require_role(["admin"])),
):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if update.vault_root:
        config["paths"]["vault_root"] = update.vault_root
    if update.raw_dir:
        config["paths"]["raw_dir"] = update.raw_dir
    if update.wiki_dir:
        config["paths"]["wiki_dir"] = update.wiki_dir
    if update.llm:
        config["llm"]["api_url"] = update.llm.api_url
        config["llm"]["model"] = update.llm.model
        config["llm"]["api_key"] = update.llm.api_key
        config["llm"]["temperature"] = update.llm.temperature
        config["llm"]["max_tokens"] = update.llm.max_tokens
        config["llm"]["timeout"] = update.llm.timeout

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    return {"success": True, "message": "配置已更新，重启服务生效"}
