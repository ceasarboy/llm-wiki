"""综述与对比分析 API"""

import time
import threading
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import (
    vault_index,
    background_tasks,
    _cleanup_old_tasks,
    WIKI_PATH,
)
from api.middleware.auth import require_role

router = APIRouter(prefix="/synthesis", tags=["synthesis"])


class SurveyRequest(BaseModel):
    keyword: str
    max_papers: int = 20


class CompareRequest(BaseModel):
    mode: str
    items: List[str]
    max_per_concept: int = 5


class TaskResponse(BaseModel):
    task_id: str
    status: str


class SynthesisItem(BaseModel):
    id: str
    title: str
    type: str
    tags: List[str]
    updated: str
    query_origin: str


class SynthesisListResponse(BaseModel):
    items: List[SynthesisItem]
    total: int


def _run_survey_task(task_id: str, keyword: str, max_papers: int):
    try:
        import sys
        scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from survey import generate_survey, save_survey
        from review_survey import review_survey_with_fix_cycle

        background_tasks[task_id]["status"] = "generating"
        background_tasks[task_id]["progress"] = 30

        content = generate_survey(keyword, max_papers)
        if not content:
            background_tasks[task_id]["status"] = "failed"
            background_tasks[task_id]["error"] = "LLM 生成失败"
            background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return

        background_tasks[task_id]["status"] = "reviewing"
        background_tasks[task_id]["progress"] = 60

        result, fixed_content = review_survey_with_fix_cycle(content)
        background_tasks[task_id]["review_score"] = result.overall_score
        background_tasks[task_id]["review_passed"] = result.passed

        if not result.passed:
            fixed_content = content

        background_tasks[task_id]["status"] = "saving"
        background_tasks[task_id]["progress"] = 80

        filepath = save_survey(keyword, fixed_content)
        vault_index.scan()

        background_tasks[task_id]["status"] = "completed"
        background_tasks[task_id]["progress"] = 100
        background_tasks[task_id]["result_file"] = str(filepath)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    except Exception as e:
        background_tasks[task_id]["status"] = "failed"
        background_tasks[task_id]["error"] = str(e)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")


def _run_compare_task(task_id: str, mode: str, items: List[str], max_per_concept: int):
    try:
        import sys
        scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from compare import generate_compare, save_compare
        from review_compare import review_compare_with_fix_cycle

        background_tasks[task_id]["status"] = "generating"
        background_tasks[task_id]["progress"] = 30

        paper_ids = items if mode == "papers" else None
        concepts = items if mode == "concepts" else None

        content = generate_compare(mode=mode, paper_ids=paper_ids, concepts=concepts, max_per_concept=max_per_concept)
        if not content:
            background_tasks[task_id]["status"] = "failed"
            background_tasks[task_id]["error"] = "LLM 生成失败"
            background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return

        background_tasks[task_id]["status"] = "reviewing"
        background_tasks[task_id]["progress"] = 60

        result, fixed_content = review_compare_with_fix_cycle(content)
        background_tasks[task_id]["review_score"] = result.overall_score
        background_tasks[task_id]["review_passed"] = result.passed

        if not result.passed:
            fixed_content = content

        background_tasks[task_id]["status"] = "saving"
        background_tasks[task_id]["progress"] = 80

        topic = " vs ".join(items)
        filepath = save_compare(topic, fixed_content)
        vault_index.scan()

        background_tasks[task_id]["status"] = "completed"
        background_tasks[task_id]["progress"] = 100
        background_tasks[task_id]["result_file"] = str(filepath)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    except Exception as e:
        background_tasks[task_id]["status"] = "failed"
        background_tasks[task_id]["error"] = str(e)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")


@router.post("/survey", response_model=TaskResponse)
async def create_survey(request: SurveyRequest, user=Depends(require_role("core"))):
    _cleanup_old_tasks()
    task_id = f"survey_{int(time.time())}"
    background_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "type": "survey",
        "keyword": request.keyword,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    thread = threading.Thread(target=_run_survey_task, args=(task_id, request.keyword, request.max_papers))
    thread.daemon = True
    thread.start()
    return TaskResponse(task_id=task_id, status="running")


@router.post("/compare", response_model=TaskResponse)
async def create_compare(request: CompareRequest, user=Depends(require_role("core"))):
    _cleanup_old_tasks()
    if request.mode not in ("papers", "concepts"):
        raise HTTPException(status_code=400, detail="mode must be 'papers' or 'concepts'")
    if len(request.items) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个对比项")

    task_id = f"compare_{int(time.time())}"
    background_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "type": "compare",
        "mode": request.mode,
        "items": request.items,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    thread = threading.Thread(target=_run_compare_task, args=(task_id, request.mode, request.items, request.max_per_concept))
    thread.daemon = True
    thread.start()
    return TaskResponse(task_id=task_id, status="running")


@router.get("/task/{task_id}")
async def get_task_status(task_id: str, user=Depends(require_role("core"))):
    if task_id not in background_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return background_tasks[task_id]


@router.get("/list", response_model=SynthesisListResponse)
async def list_syntheses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type_filter: Optional[str] = Query(None, alias="type"),
    user=Depends(require_role("general")),
):
    items = []
    for page_id, info in vault_index.pages.items():
        if info.get("type") != "synthesis":
            continue
        if type_filter:
            tags = info.get("tags", [])
            if type_filter == "survey" and "survey" not in tags:
                continue
            if type_filter == "comparison" and "comparison" not in tags:
                continue
        items.append(SynthesisItem(
            id=page_id,
            title=info.get("title", page_id),
            type="synthesis",
            tags=info.get("tags", []),
            updated=info.get("updated", ""),
            query_origin="",
        ))

    total = len(items)
    start = (page - 1) * page_size
    items = items[start:start + page_size]
    return SynthesisListResponse(items=items, total=total)
