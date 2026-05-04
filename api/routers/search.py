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
        from qmd_search_simple import hybrid_search

        search_results = hybrid_search(request.question, top_k=30)

        query_lower = request.question.lower()
        query_keywords = set(re.findall(r"[a-zA-Z]+", query_lower))
        cn_segments = re.findall(r"[\u4e00-\u9fff]+", query_lower)
        stop_words = {
            "有几种", "有哪些", "是什么", "什么是", "如何", "怎么", "为什么",
            "哪些", "几种", "什么", "可以", "能够", "之间", "关系", "区别",
            "联系", "还有", "其他", "的", "了", "在", "是", "我", "你", "他",
            "她", "它", "们", "这", "那", "一", "个", "不", "没", "会", "能",
            "要", "说", "去", "做", "看", "想", "给", "让", "被", "把", "从",
            "到", "对", "向", "为", "以", "用", "也", "都", "和",
        }
        for seg in cn_segments:
            query_keywords.add(seg)
            for i in range(len(seg)):
                for j in range(i + 2, min(len(seg) + 1, i + 5)):
                    sub = seg[i:j]
                    if sub not in stop_words and len(sub) >= 2:
                        query_keywords.add(sub)

        if query_keywords:
            existing_ids = {r["id"] for r in search_results}
            core_keywords = [
                kw for kw in query_keywords if len(kw) >= 2 and kw not in stop_words
            ]
            for page_id, page_info in vault_index.pages.items():
                if page_id in existing_ids:
                    continue
                matched = any(
                    kw in page_info.get("title", "").lower() for kw in core_keywords
                )
                if not matched:
                    continue
                try:
                    md_file = _safe_path(WIKI_PATH, page_id)
                except HTTPException:
                    continue
                if md_file.exists():
                    content = md_file.read_text(encoding="utf-8")
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2]
                    search_results.append(
                        {
                            "id": page_id,
                            "content": content[:2000],
                            "metadata": {
                                "page_name": page_id,
                                "title": page_info.get("title", ""),
                                "type": page_info.get("type", ""),
                            },
                            "final_score": 0.6,
                            "vector_score": 0,
                            "keyword_score": 0,
                        }
                    )
                    existing_ids.add(page_id)

        search_results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        search_results = search_results[:20]

        sources = []
        contexts = []
        for r in search_results:
            metadata = r.get("metadata", {})
            sources.append(
                SourceRef(
                    id=metadata.get("page_name", r["id"]),
                    title=metadata.get("title", r["id"]),
                    path=f"wiki/{r['id']}",
                    relevance=r.get("final_score", 0.5),
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
        return QueryResponse(
            answer=f"搜索功能暂时不可用: {str(e)}",
            sources=[],
            related_questions=HOT_QUERIES[:3],
        )


@router.get("/hot-queries", response_model=HotQueriesResponse)
async def get_hot_queries():
    return HotQueriesResponse(queries=HOT_QUERIES)


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
