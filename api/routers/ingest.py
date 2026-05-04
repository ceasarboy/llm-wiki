"""论文导入 Ingest API"""

import re
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.dependencies import (
    vault_index,
    RAW_DIR,
    VAULT_PATH,
    WIKI_PATH,
    RAGTEST_DIR,
    SCRIPTS_DIR,
    get_db_ctx,
)
from api.database import PDFFile
from api.middleware.auth import require_role
from api.models import User

router = APIRouter(prefix="/ingest", tags=["ingest"])

LOG_FILE = RAGTEST_DIR / "ingest.log"


class PendingDoc(BaseModel):
    filename: str
    path: str
    size: int
    modified: str


class PendingDocsResponse(BaseModel):
    count: int
    items: List[PendingDoc]


class IngestResult(BaseModel):
    success: bool
    message: str
    processed: int


class IngestLogResponse(BaseModel):
    log: str
    finished: bool


def _get_processed_docs() -> set:
    processed = set()

    if LOG_FILE.exists():
        content = LOG_FILE.read_text(encoding="utf-8")
        pattern1 = r"原始文档:\s*([^\n]+)"
        for match in re.findall(pattern1, content):
            processed.add(match.strip())
        pattern2 = r"\|\s*原始文档:\s*(raw/papers/markdown/[^\n]+)"
        for match in re.findall(pattern2, content):
            processed.add(match.strip())

    wiki_papers_dir = WIKI_PATH / "papers"
    if wiki_papers_dir.exists():
        for paper_file in wiki_papers_dir.glob("*_论文.md"):
            stem = paper_file.stem.replace("_论文", "")
            processed.add(f"raw/papers/markdown/{stem}.md")

    try:
        with get_db_ctx() as db:
            for pdf in db.query(PDFFile).all():
                if pdf.status == "completed":
                    processed.add(pdf.filename)
    except Exception:
        pass

    return processed


@router.get("/pending", response_model=PendingDocsResponse)
async def get_pending_docs():
    if not RAW_DIR.exists():
        raise HTTPException(status_code=404, detail="Raw directory not found")

    all_docs = list(RAW_DIR.glob("*.md"))
    processed = _get_processed_docs()

    pending = []
    for doc in all_docs:
        rel_path = f"raw/papers/markdown/{doc.name}"
        if rel_path not in processed and doc.name not in processed:
            stat = doc.stat()
            pending.append(
                PendingDoc(
                    filename=doc.name,
                    path=str(doc),
                    size=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )
            )

    return PendingDocsResponse(count=len(pending), items=pending)


@router.post("/run", response_model=IngestResult)
async def run_ingest(
    limit: int = 10,
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    log_file = RAGTEST_DIR / "ingest.log"
    log_file.write_text(f"开始导入 {limit} 篇论文...\n", encoding="utf-8")

    try:
        with get_db_ctx() as db:
            from api.services.log_service import LogService

            LogService.log_system_event(
                db, "INFO", "ingest", "start", f"开始导入 {limit} 篇论文"
            )

        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPTS_DIR / "batch.py"),
                "--batch-size",
                str(limit),
                "--max-batches",
                "1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(RAGTEST_DIR),
        )

        with open(log_file, "a", encoding="utf-8") as f:
            for line in process.stdout:
                f.write(line)
                f.flush()

        process.wait(timeout=600)

        if process.returncode != 0:
            return IngestResult(
                success=False, message="导入失败，请查看日志", processed=0
            )

        vault_index.scan()
        return IngestResult(
            success=True, message="导入完成", processed=limit
        )
    except subprocess.TimeoutExpired:
        return IngestResult(
            success=False, message="导入超时（超过10分钟）", processed=0
        )
    except Exception as e:
        return IngestResult(
            success=False, message=f"导入出错: {str(e)}", processed=0
        )


@router.get("/log", response_model=IngestLogResponse)
async def get_ingest_log():
    log_file = RAGTEST_DIR / "ingest.log"
    if not log_file.exists():
        return IngestLogResponse(log="", finished=True)

    content = log_file.read_text(encoding="utf-8")
    finished = any(
        kw in content for kw in ["导入完成", "导入失败", "导入超时"]
    )
    return IngestLogResponse(log=content[-5000:], finished=finished)
