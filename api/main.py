"""
LLM-Wiki API — Main Application Entry Point

V1.1: Refactored — routers split into separate modules.
"""

import asyncio
import subprocess
import platform
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import engine, Base
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
