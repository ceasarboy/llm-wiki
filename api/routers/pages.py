"""知识库页面 CRUD API"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

import yaml
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.dependencies import (
    vault_index,
    _safe_path,
    WIKI_PATH,
    VAULT_PATH,
    get_db_ctx,
)
from api.database import get_db
from api.middleware.auth import require_role
from api.models import User

router = APIRouter(prefix="/pages", tags=["pages"])


class PageItem(BaseModel):
    id: str
    title: str
    type: str
    tags: List[str]
    updated: str
    summary: Optional[str] = None


class PageListResponse(BaseModel):
    items: List[PageItem]
    total: int


class PageDetail(BaseModel):
    id: str
    title: str
    type: str
    status: str
    content: str
    frontmatter: dict
    tags: List[str]
    updated: str


class PageUpdateRequest(BaseModel):
    content: str


class ManualReviewRequest(BaseModel):
    action: str
    comment: str = ""
    reviewer: str = ""


class ManualReviewResponse(BaseModel):
    success: bool
    message: str
    new_status: str


class RecheckRequest(BaseModel):
    reason: str = ""


class HistoryVersion(BaseModel):
    version: int
    filename: str
    path: str
    saved_at: str
    save_reason: str
    size: int


class HistoryListResponse(BaseModel):
    items: List[HistoryVersion]
    total: int


class HistoryDetailResponse(BaseModel):
    version: int
    filename: str
    content: str
    saved_at: str
    save_reason: str
    frontmatter: Dict[str, Any]


HISTORY_DIR = WIKI_PATH / "history"


def _find_page_file(id: str) -> Path | None:
    if id in vault_index.pages:
        return Path(vault_index.pages[id]["file_path"])

    type_suffixes = {
        "papers": "_论文",
        "entities": "",
        "concepts": "",
        "summaries": "",
        "syntheses": "_综合",
    }
    for subdir, suffix in type_suffixes.items():
        for pattern in [f"{id}{suffix}.md", f"{id}.md"]:
            test_path = WIKI_PATH / subdir / pattern
            if test_path.exists():
                return test_path
    return None


@router.get("", response_model=PageListResponse)
async def get_pages(type: Optional[str] = None, page: int = 1, page_size: int = 20):
    if type and type in vault_index.by_type:
        page_ids = vault_index.by_type[type]
    else:
        page_ids = list(vault_index.pages.keys())

    start = (page - 1) * page_size
    end = start + page_size

    results = []
    for pid in page_ids[start:end]:
        p = vault_index.pages[pid]
        results.append(
            PageItem(
                id=pid,
                title=p["title"],
                type=p["type"],
                tags=p["tags"],
                updated=p["updated"],
            )
        )

    return PageListResponse(items=results, total=len(page_ids))


@router.get("/{id:path}", response_model=PageDetail)
async def get_page_detail(id: str):
    file_path = _find_page_file(id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    content = file_path.read_text(encoding="utf-8")
    frontmatter = {}

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass
            content = parts[2].strip()

    raw_tags = frontmatter.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = [raw_tags] if raw_tags else []
    safe_tags = [str(t) for t in raw_tags]

    raw_updated = frontmatter.get(
        "updated",
        datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d"),
    )

    return PageDetail(
        id=id,
        title=str(frontmatter.get("title", file_path.stem)),
        type=str(frontmatter.get("type", "unknown")),
        status=str(frontmatter.get("status", "stable")),
        content=content,
        frontmatter=frontmatter,
        tags=safe_tags,
        updated=str(raw_updated),
    )


@router.put("/{id:path}")
async def update_page(
    id: str,
    update: PageUpdateRequest,
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    file_path = _find_page_file(id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    file_path.write_text(update.content, encoding="utf-8")
    vault_index.scan()
    return {"success": True, "message": "页面已保存"}


@router.post("/{id:path}/manual-review", response_model=ManualReviewResponse)
async def set_manual_review(
    id: str,
    request: ManualReviewRequest,
    current_user: User = Depends(require_role(["admin", "maintainer", "core"])),
):
    sys_path = __import__("sys")
    sys_path.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
    from version_control import save_version

    file_path = _find_page_file(id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    content = file_path.read_text(encoding="utf-8")

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2]
            except Exception:
                frontmatter = {}
                body = parts[2]
        else:
            frontmatter = {}
            body = content
    else:
        frontmatter = {}
        body = content

    try:
        save_version(file_path, f"人工审核: {request.action}")
    except Exception as e:
        print(f"保存版本失败: {e}")

    status_map = {"approve": "reviewed", "reject": "pending"}
    new_status = status_map.get(request.action, "generated")

    frontmatter["status"] = new_status
    frontmatter["reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frontmatter["reviewer"] = request.reviewer
    if request.comment:
        frontmatter["review_comment"] = request.comment

    new_content = (
        "---\n"
        + yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
        + "---\n\n"
        + body.strip()
    )
    file_path.write_text(new_content, encoding="utf-8")
    vault_index.scan()

    return ManualReviewResponse(
        success=True,
        message=f"审核完成，状态已更新为 {new_status}",
        new_status=new_status,
    )


@router.post("/{id:path}/recheck")
async def recheck_page(
    id: str,
    request: RecheckRequest = RecheckRequest(),
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

    file_path = _find_page_file(id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    content = file_path.read_text(encoding="utf-8")
    frontmatter = {}

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                frontmatter = {}

    source = frontmatter.get("source")
    review_comment = frontmatter.get("review_comment")

    if not source:
        raise HTTPException(status_code=400, detail="页面缺少source信息")
    if not review_comment:
        raise HTTPException(status_code=400, detail="页面缺少审核意见")

    if isinstance(source, list):
        source_path = source[0]
    else:
        source_path = source

    source_path = source_path.strip("[]")
    full_source_path = VAULT_PATH / source_path

    if not full_source_path.exists():
        raise HTTPException(
            status_code=404, detail=f"原始文档不存在: {source_path}"
        )

    try:
        from recheck import recheck_page as do_recheck

        success, wiki_path, error = do_recheck(
            str(full_source_path), review_comment, str(file_path.parent)
        )

        if success:
            vault_index.scan()
            try:
                with get_db_ctx() as db:
                    from api.services.log_service import LogService

                    LogService.log_system_event(
                        db, "INFO", "review", "recheck", f"复审成功: {id}"
                    )
            except Exception:
                pass
            return {"success": True, "message": "复审成功", "wiki_path": wiki_path}
        else:
            raise HTTPException(status_code=500, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"复审失败: {str(e)}")


@router.get("/{page_id:path}/history", response_model=HistoryListResponse)
async def get_page_history(page_id: str):
    file_path = _find_page_file(page_id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    history_items = []

    if HISTORY_DIR.exists():
        try:
            relative = file_path.relative_to(WIKI_PATH)
            history_subdir = HISTORY_DIR / relative.parent
            stem = file_path.stem

            if history_subdir.exists():
                for f in sorted(
                    history_subdir.glob(f"{stem}_v*.md"), reverse=True
                ):
                    match = re.search(r"_v(\d+)\.md$", f.name)
                    if match:
                        version = int(match.group(1))
                        h_content = f.read_text(encoding="utf-8")
                        saved_at = ""
                        save_reason = ""

                        if h_content.startswith("---"):
                            h_parts = h_content.split("---", 2)
                            if len(h_parts) >= 3:
                                try:
                                    h_fm = yaml.safe_load(h_parts[1])
                                    saved_at = h_fm.get("saved_at", "")
                                    save_reason = h_fm.get("save_reason", "")
                                except Exception:
                                    pass

                        history_items.append(
                            HistoryVersion(
                                version=version,
                                filename=f.name,
                                path=str(f.relative_to(WIKI_PATH)),
                                saved_at=saved_at,
                                save_reason=save_reason,
                                size=f.stat().st_size,
                            )
                        )
        except ValueError:
            pass

    return HistoryListResponse(items=history_items, total=len(history_items))


@router.get(
    "/{page_id:path}/history/{version:int}", response_model=HistoryDetailResponse
)
async def get_history_version(page_id: str, version: int):
    file_path = _find_page_file(page_id)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    try:
        relative = file_path.relative_to(WIKI_PATH)
        history_subdir = HISTORY_DIR / relative.parent
        stem = file_path.stem
        history_file = history_subdir / f"{stem}_v{version}.md"

        if not history_file.exists():
            raise HTTPException(status_code=404, detail="History version not found")

        content = history_file.read_text(encoding="utf-8")
        frontmatter = {}
        saved_at = ""
        save_reason = ""
        body = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    saved_at = frontmatter.get("saved_at", "")
                    save_reason = frontmatter.get("save_reason", "")
                    body = parts[2].strip()
                except Exception:
                    pass

        return HistoryDetailResponse(
            version=version,
            filename=history_file.name,
            content=body,
            saved_at=saved_at,
            save_reason=save_reason,
            frontmatter=frontmatter,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="History version not found")
