"""
LLM-Wiki API — Main Application Entry Point

V1.1: Refactored — routers split into separate modules.
"""

import asyncio
import subprocess
import platform
import sys
import os
import traceback
import json
from urllib.parse import unquote
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from api.database import engine, Base, SessionLocal
from api.dependencies import RAW_DIR, VAULT_PATH
from api.routers import (
    auth_router,
    users_router,
    logs_router,
    pages_router,
    raw_router,
    pdf_router,
    pdfs_legacy_router,
    search_router,
    ingest_router,
    config_router,
    graph_router,
    maintenance_router,
    synthesis_router,
)

app = FastAPI(
    title="LLM-Wiki API",
    description="LLM-Wiki: AI-driven knowledge compilation system",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log_error_to_db(level: str, module: str, action: str, message: str):
    try:
        from api.models import SystemLog
        db = SessionLocal()
        try:
            log = SystemLog(
                level=level,
                module=module,
                action=action,
                message=message[:1000],
                details=json.dumps({"timestamp": datetime.now().isoformat()}),
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
    except Exception:
        print(f"[LOGGER_FAILED] {level}|{module}|{action}: {message[:200]}")


@app.middleware("http")
async def error_logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            _log_error_to_db(
                "ERROR" if response.status_code >= 500 else "WARNING",
                request.url.path.split("/")[2] if len(request.url.path.split("/")) > 2 else "unknown",
                f"HTTP_{response.status_code}",
                f"{request.method} {request.url.path} -> {response.status_code}",
            )
        return response
    except Exception:
        _log_error_to_db(
            "ERROR",
            "middleware",
            "unhandled_exception",
            f"{request.method} {request.url.path}\n{traceback.format_exc()[:800]}",
        )
        raise


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        _log_error_to_db(
            "WARNING" if exc.status_code < 500 else "ERROR",
            "http",
            f"HTTP_{exc.status_code}",
            f"{request.method} {request.url.path}: {exc.detail}",
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    _log_error_to_db(
        "ERROR",
        "unhandled",
        type(exc).__name__,
        f"{request.method} {request.url.path}\n{traceback.format_exc()[:1000]}",
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {type(exc).__name__}"},
    )

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(pages_router, prefix="/api")
app.include_router(raw_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")
app.include_router(pdfs_legacy_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(maintenance_router, prefix="/api")
app.include_router(synthesis_router, prefix="/api")


@app.get("/api/assets")
async def get_asset(path: str = Query(...), doc: Optional[str] = Query(None)):
    decoded_path = unquote(path)
    if os.path.isabs(decoded_path) or ".." in decoded_path:
        raise HTTPException(
            status_code=403, detail="Absolute paths and parent references not allowed"
        )

    asset_path = Path(decoded_path)
    if not asset_path.is_absolute():
        asset_path = RAW_DIR / decoded_path

    if not asset_path.exists() and doc:
        doc_path = RAW_DIR / f"{doc}_{decoded_path}"
        if doc_path.exists():
            asset_path = doc_path

    allowed_dirs = [VAULT_PATH / "assets", RAW_DIR]
    is_allowed = False
    for allowed_dir in allowed_dirs:
        try:
            asset_path.resolve().relative_to(allowed_dir.resolve())
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }
    return FileResponse(
        asset_path, media_type=content_types.get(asset_path.suffix.lower(), "application/octet-stream")
    )


async def open_browser():
    await asyncio.sleep(1.5)
    url = "http://localhost:5173"
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(["cmd", "/c", "start", url], shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        print(f"🌐 浏览器已打开: {url}")
    except Exception as e:
        print(f"⚠️ 无法自动打开浏览器: {e}")


@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    asyncio.create_task(open_browser())


@app.get("/")
async def root():
    return {
        "service": "LLM-Wiki API",
        "version": "1.1.0",
        "docs": "/docs",
        "health": "ok",
    }
