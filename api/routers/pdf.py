"""PDF 管理 API"""

import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.dependencies import (
    _safe_filename,
    VAULT_PATH,
    get_db_ctx,
    vault_index,
)
from api.database import PDFFile, MarkdownFile
from api.middleware.auth import require_role
from api.models import User

router = APIRouter(prefix="/pdf", tags=["pdf"])
legacy_router = APIRouter(prefix="/pdfs", tags=["pdfs_legacy"])

PDF_DIR = VAULT_PATH / "raw" / "papers" / "pdf"
MD_DIR = VAULT_PATH / "raw" / "papers" / "markdown"
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


class PDFListResponse(BaseModel):
    items: List[dict]
    total: int


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    if not file.filename or not file.filename.endswith(".pdf"):
        try:
            with get_db_ctx() as db:
                from api.services.log_service import LogService
                LogService.log_system_event(
                    db, "WARNING", "pdf", "upload_reject",
                    f"非PDF文件被拒绝: {file.filename}"
                )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="只支持PDF文件")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        try:
            with get_db_ctx() as db:
                from api.services.log_service import LogService
                LogService.log_system_event(
                    db, "WARNING", "pdf", "upload_reject",
                    f"文件过大被拒绝: {file.filename}, 大小={len(contents)}"
                )
        except Exception:
            pass
        raise HTTPException(status_code=413, detail=f"文件过大，最大允许 50MB")

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_DIR / _safe_filename(file.filename)

    with open(pdf_path, "wb") as buffer:
        buffer.write(contents)

    try:
        with get_db_ctx() as db:
            from api.services.log_service import LogService

            LogService.log_system_event(
                db, "INFO", "pdf", "upload", f"上传PDF文件: {file.filename}"
            )
            pdf_file = PDFFile(
                filename=file.filename,
                path=str(pdf_path),
                size=pdf_path.stat().st_size,
                status="pending",
            )
            db.add(pdf_file)
            db.commit()
            db.refresh(pdf_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {str(e)}")

    return {
        "success": True,
        "message": "上传成功",
        "file": {
            "filename": file.filename,
            "path": str(pdf_path),
            "size": pdf_path.stat().st_size,
            "uploaded_at": datetime.now().isoformat(),
        },
    }


@router.get("/list")
async def list_pdfs(page: int = 1, page_size: int = 20, status: Optional[str] = None):
    with get_db_ctx() as db:
        query = db.query(PDFFile)
        if status:
            query = query.filter(PDFFile.status == status)
        total = query.count()
        items = (
            query.order_by(PDFFile.uploaded_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [
                {
                    "filename": item.filename,
                    "path": item.path,
                    "size": item.size,
                    "uploaded_at": item.uploaded_at.isoformat()
                    if item.uploaded_at
                    else None,
                    "status": item.status,
                    "markdown_path": item.markdown_path,
                }
                for item in items
            ],
            "total": total,
        }


@router.post("/convert")
async def convert_pdf(
    filename: str,
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    from scripts.pdf_converter import convert_pdf_to_markdown

    with get_db_ctx() as db:
        pdf_file = db.query(PDFFile).filter(PDFFile.filename == filename).first()
        if not pdf_file:
            raise HTTPException(status_code=404, detail="文件不存在")
        if pdf_file.status == "converting":
            raise HTTPException(status_code=400, detail="文件正在转换中")

        pdf_file.status = "converting"
        db.commit()

        try:
            pdf_path = Path(pdf_file.path)
            MD_DIR.mkdir(parents=True, exist_ok=True)
            success, markdown_path, error = convert_pdf_to_markdown(
                pdf_path, MD_DIR
            )

            if success:
                pdf_file.status = "completed"
                pdf_file.markdown_path = markdown_path
                pdf_file.converted_at = datetime.now()
                db.commit()

                from api.services.log_service import LogService

                LogService.log_system_event(
                    db, "INFO", "pdf", "convert", f"PDF转换成功: {filename}"
                )
                return {"success": True, "message": "转换成功", "markdown_path": markdown_path}
            else:
                pdf_file.status = "failed"
                pdf_file.error_message = error
                db.commit()
                raise HTTPException(status_code=500, detail=error or "转换失败")
        except HTTPException:
            raise
        except Exception as e:
            pdf_file.status = "failed"
            pdf_file.error_message = str(e)
            db.commit()
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/serve/{filename}")
async def serve_pdf(filename: str):
    with get_db_ctx() as db:
        pdf_file = db.query(PDFFile).filter(PDFFile.filename == filename).first()
        if not pdf_file:
            raise HTTPException(status_code=404, detail="PDF not found")
        path = Path(pdf_file.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found on disk")
        return FileResponse(path, media_type="application/pdf")


@router.delete("/{filename}")
async def delete_pdf(
    filename: str, current_user: User = Depends(require_role(["admin"]))
):
    with get_db_ctx() as db:
        pdf_file = db.query(PDFFile).filter(PDFFile.filename == filename).first()
        if not pdf_file:
            raise HTTPException(status_code=404, detail="文件不存在")

        pdf_path = Path(pdf_file.path)
        if pdf_path.exists():
            pdf_path.unlink()

        if pdf_file.markdown_path:
            md_path = Path(pdf_file.markdown_path)
            if md_path.exists():
                md_path.unlink()

        db.delete(pdf_file)
        db.commit()
        return {"success": True, "message": "删除成功"}


@legacy_router.get("")
async def list_legacy_pdfs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = "",
):
    pdf_dir = VAULT_PATH / "raw" / "papers" / "pdf"
    if not pdf_dir.exists():
        return PDFListResponse(items=[], total=0)

    search_lower = search.lower()
    items = []

    for pdf_file in sorted(pdf_dir.glob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True):
        title = pdf_file.stem
        if search_lower and search_lower not in title.lower():
            continue

        stat = pdf_file.stat()
        items.append(
            {
                "id": pdf_file.stem,
                "title": title,
                "path": str(pdf_file),
                "size": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "updated": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                ),
            }
        )

    total = len(items)
    start = (page - 1) * page_size
    return PDFListResponse(items=items[start : start + page_size], total=total)


@legacy_router.get("/{pdf_id}")
async def get_legacy_pdf(pdf_id: str):
    pdf_dir = VAULT_PATH / "raw" / "papers" / "pdf"
    pdf_file = pdf_dir / f"{pdf_id}.pdf"
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_file, media_type="application/pdf")
