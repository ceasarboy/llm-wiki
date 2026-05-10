"""搜索与查询 API"""

import re
import sys
import asyncio
from typing import Optional, List
from pathlib import Path

import yaml
import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import (
    vault_index,
    _safe_path,
    HOT_QUERIES,
    WIKI_PATH,
    RAGTEST_DIR,
)

router = APIRouter(prefix="", tags=["search"])


class QueryRequest(BaseModel):
    question: str


class SourceRef(BaseModel):
    id: str
    title: str
    path: str
    relevance: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceRef]
    related_questions: List[str]


class HotQueriesResponse(BaseModel):
    queries: List[str]
    saved: List[dict] = []


class RecentUpdate(BaseModel):
    id: str
    title: str
    type: str
    updated: str


class RecentUpdatesResponse(BaseModel):
    items: List[RecentUpdate]


def _call_llm_for_query(question: str, contexts: list) -> str:
    context_text = "\n\n---\n\n".join(
        [f"【文档{i + 1}】{c[:1500]}" for i, c in enumerate(contexts[:15])]
    )

    prompt = f"""你是一个知识库问答助手。基于以下检索到的文档内容回答用户问题。

要求：
1. 答案要具体、准确，直接回答问题
2. 如果问题涉及列举或统计（如"有几种"、"有哪些"），请尽可能完整地列出所有检索到的相关内容
3. 如果文档内容不足以完整回答，说明已列出的部分并提示可能还有未覆盖的内容
4. 用简洁的中文回答

---
检索到的文档：
{context_text}
---

用户问题：{question}

请回答："""

    try:
        config_path = RAGTEST_DIR / "config.yaml"
        if config_path.exists():
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            llm_config = config.get("llm", {})
            api_url = llm_config.get(
                "api_url", "http://127.0.0.1:28789/v1/chat/completions"
            )
            api_key = llm_config.get("api_key", "")
            model = llm_config.get("model", "Pro/moonshotai/Kimi-K2.5")
        else:
            api_url = "http://127.0.0.1:28789/v1/chat/completions"
            api_key = ""
            model = "Pro/moonshotai/Kimi-K2.5"

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500,
        }

        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"基于检索结果的答案生成失败: {str(e)}\n\n请参考以下文档片段：{contexts[0][:300] if contexts else '无'}..."


@router.get("/search")
async def search(q: str = "", type: Optional[str] = None):
    results = []
    query_lower = q.lower() if q else ""

    for pid, p in vault_index.pages.items():
        if type and p["type"] != type:
            continue
        if (
            query_lower
            and query_lower not in p["title"].lower()
            and query_lower not in " ".join(p["tags"]).lower()
        ):
            continue
        results.append(
            {
                "id": pid,
                "title": p["title"],
                "type": p["type"],
                "tags": p["tags"],
                "updated": p["updated"],
            }
        )

    return {"results": results[:20]}


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    try:
        scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from qdrant_search import hybrid_search_bge

        search_results = hybrid_search_bge(request.question, top_k=30)

        sources = []
        contexts = []
        for r in search_results:
            metadata = r.get("metadata", {})
            sources.append(
                SourceRef(
                    id=metadata.get("page_name", r["id"]),
                    title=metadata.get("title", r["id"]),
                    path=f"wiki/{r['id']}",
                    relevance=min(r.get("final_score", 0.5), 0.99),
                )
            )
            contexts.append(r.get("content", ""))

        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(
            None, _call_llm_for_query, request.question, contexts
        )

        return QueryResponse(
            answer=answer,
            sources=sources,
            related_questions=HOT_QUERIES[:3],
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            from api.services.log_service import LogService
            from api.dependencies import get_db_ctx
            with get_db_ctx() as db:
                LogService.log_system_event(
                    db, "ERROR", "search", "query_failed",
                    f"{request.question[:200]}: {traceback.format_exc()[:800]}"
                )
        except Exception:
            pass
        return QueryResponse(
            answer=f"搜索功能暂时不可用: {str(e)}",
            sources=[],
            related_questions=HOT_QUERIES[:3],
        )


@router.get("/hot-queries", response_model=HotQueriesResponse)
async def get_hot_queries():
    saved = []
    faq_dir = WIKI_PATH / "faq"
    if faq_dir.exists():
        for md_file in sorted(faq_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:10]:
            try:
                content = md_file.read_text(encoding="utf-8")
                match = re.search(r'^question:\s*"(.+?)"', content, re.MULTILINE)
                if not match:
                    match = re.search(r'^# (.+)', content, re.MULTILINE)
                if match:
                    saved.append({
                        "question": match.group(1),
                        "id": f"faq/{md_file.stem}",
                        "path": str(md_file),
                    })
            except Exception:
                pass
    return HotQueriesResponse(queries=HOT_QUERIES, saved=saved)


@router.get("/recent-updates", response_model=RecentUpdatesResponse)
async def get_recent_updates(limit: int = 5):
    sorted_pages = sorted(
        vault_index.pages.values(), key=lambda x: x["updated"], reverse=True
    )
    items = [
        RecentUpdate(
            id=p["id"], title=p["title"], type=p["type"], updated=p["updated"]
        )
        for p in sorted_pages[:limit]
    ]
    return RecentUpdatesResponse(items=items)


class SaveQueryRequest(BaseModel):
    question: str
    answer: str
    sources: list = []


class SaveQueryResponse(BaseModel):
    success: bool
    path: str
    message: str


@router.post("/save-query", response_model=SaveQueryResponse)
async def save_query(request: SaveQueryRequest):
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    safe_question = request.question[:40].replace("/", "_").replace("\\", "_").replace("?", "").replace("？", "")
    filename = f"{today}_{safe_question}.md"

    faq_dir = WIKI_PATH / "faq"
    faq_dir.mkdir(parents=True, exist_ok=True)

    sources_md = ""
    if request.sources:
        sources_md = "\n## 来源\n\n"
        for i, src in enumerate(request.sources):
            title = src.get("title", src.get("id", ""))
            path = src.get("path", "")
            sources_md += f"- [{i+1}] {title} ({path})\n"

    content = f"""---
title: "{request.question[:60]}"
type: faq
tags: []
source: []
created: "{today}"
updated: "{today}"
status: generated
question: "{request.question}"
---

# {request.question}

## 回答

{request.answer}
{sources_md}
---
_保存时间: {datetime.now().isoformat()}_
"""

    filepath = faq_dir / filename
    filepath.write_text(content, encoding="utf-8")

    try:
        from api.database import SessionLocal
        from api.models import SystemLog
        db = SessionLocal()
        try:
            db.add(SystemLog(
                level="INFO", module="search", action="save_query",
                message=f"已保存问答: {request.question[:60]}",
            ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass

    return SaveQueryResponse(
        success=True,
        path=str(filepath),
        message=f"已保存到 {filename}",
    )
