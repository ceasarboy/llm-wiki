"""原文 Raw 文档 API"""

import os
from urllib.parse import unquote
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.dependencies import _safe_path, RAW_DIR, VAULT_PATH, WIKI_PATH
from api.middleware.auth import require_role
from api.models import User

router = APIRouter(prefix="/raw", tags=["raw"])


class RawDocument(BaseModel):
    id: str
    title: str
    path: str
    size: int
    updated: str


class RawDocumentListResponse(BaseModel):
    items: List[RawDocument]
    total: int


class RawDocumentDetail(BaseModel):
    id: str
    title: str
    path: str
    content: str
    size: int
    updated: str


@router.get("", response_model=RawDocumentListResponse)
async def list_raw_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
):
    raw_path = RAW_DIR
    if not raw_path.exists():
        return RawDocumentListResponse(items=[], total=0)

    items = []
    for md_file in sorted(raw_path.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = md_file.stat()
        title = md_file.stem

        if search and search.lower() not in title.lower():
            continue

        items.append(
            RawDocument(
                id=md_file.stem,
                title=title,
                path=str(md_file),
                size=stat.st_size,
                updated=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            )
        )

    total = len(items)
    start = (page - 1) * page_size
    return RawDocumentListResponse(items=items[start : start + page_size], total=total)


@router.get("/{id}", response_model=RawDocumentDetail)
async def get_raw_document(id: str):
    raw_path = RAW_DIR
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="Raw directory not found")

    md_file = raw_path / f"{id}.md"
    if not md_file.exists():
        decoded_id = unquote(id)
        md_file = raw_path / f"{decoded_id}.md"

    if not md_file.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    content = md_file.read_text(encoding="utf-8")
    stat = md_file.stat()

    return RawDocumentDetail(
        id=md_file.stem,
        title=md_file.stem,
        path=str(md_file),
        content=content,
        size=stat.st_size,
        updated=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
    )


@router.put("/{id}")
async def update_raw_document(
    id: str,
    body: dict,
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    content = body.get("content", "")
    new_filename = body.get("filename")

    decoded_id = unquote(id)
    md_file = _safe_path(RAW_DIR, decoded_id)
    if not md_file.exists():
        md_file = _safe_path(RAW_DIR, id)
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    if new_filename and new_filename != md_file.stem:
        new_filename = new_filename.strip()
        if (
            not new_filename
            or "/" in new_filename
            or "\\" in new_filename
            or "." in new_filename
        ):
            raise HTTPException(status_code=400, detail="Invalid filename")
        new_path = RAW_DIR / f"{new_filename}.md"
        if new_path.exists() and new_path != md_file:
            raise HTTPException(status_code=400, detail="File already exists")
        md_file.rename(new_path)
        md_file = new_path

    md_file.write_text(content, encoding="utf-8")
    return {"success": True, "message": "保存成功", "new_id": md_file.stem}


@router.api_route("/{id}/pdf", methods=["GET", "HEAD"])
async def get_raw_pdf(id: str):
    decoded_id = unquote(id)
    pdf_dir = VAULT_PATH / "raw" / "papers" / "pdf"
    if not pdf_dir.exists():
        raise HTTPException(status_code=404, detail="PDF directory not found")

    pdf_file = pdf_dir / f"{decoded_id}.pdf"
    if not pdf_file.exists():
        pdf_file = pdf_dir / f"{id}.pdf"
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(pdf_file, media_type="application/pdf")
