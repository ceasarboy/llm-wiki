"""Qdrant + BGE-M3 语义搜索（本地模式）"""
import yaml
import time
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any

from qdrant_client import QdrantClient

from embedding_bge import encode

RAGTEST_DIR = Path(__file__).parent.parent
CONFIG_PATH = RAGTEST_DIR / "config.yaml"
INDEX_DIR = RAGTEST_DIR / "index"
QDRANT_STORAGE = INDEX_DIR / "qdrant_data"

EXCLUDE_IDS = {"log", "index"}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def bge_search(
    query: str,
    top_k: int = 20,
    collection_name: str = "llm_wiki_bge",
) -> List[Dict[str, Any]]:
    client = QdrantClient(path=str(QDRANT_STORAGE))
    query_embedding = encode(query)[0].tolist()

    results = client.query_points(
        collection_name=collection_name,
        query=query_embedding,
        limit=top_k,
    ).points

    items = []
    for hit in results:
        page_id = hit.payload.get("page_id", str(hit.id))
        if page_id in EXCLUDE_IDS:
            continue
        items.append({"id": page_id, "score": float(hit.score)})
    client.close()
    return items


def hybrid_search_bge(
    query: str,
    top_k: int = 30,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> List[Dict[str, Any]]:
    config = load_config()
    qdrant_cfg = config.get("qdrant", {})

    vector_results = bge_search(
        query,
        top_k=top_k * 2,
        collection_name=qdrant_cfg.get("collection_name", "llm_wiki_bge"),
    )

    from api.dependencies import vault_index
    query_lower = query.lower()
    query_keywords = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]+", query_lower))
    stop_words = {"的", "了", "在", "是", "我", "你", "他", "她", "它", "们", "这", "那", "和", "与", "或", "从", "到", "对", "为", "以", "也", "都", "把", "被", "让", "给", "用", "不", "没", "会", "能", "要", "说", "去", "做", "看", "想", "还", "有", "什么", "哪", "吗", "呢", "啊", "怎样", "怎么", "为什么", "如何", "可以", "能够", "一个"}
    core_kw = {kw for kw in query_keywords if len(kw) >= 2 and kw not in stop_words}

    keyword_results = []
    for pid, page in vault_index.pages.items():
        if any(kw in page.get("title", "").lower() for kw in core_kw):
            keyword_results.append({"id": pid, "keyword_score": 1.0})

    combined: Dict[str, Dict] = {}
    max_vector = max((r["score"] for r in vector_results), default=1.0)

    for r in vector_results:
        vid = r["id"]
        combined[vid] = {
            "id": vid,
            "vector_score": r["score"] / max_vector,
            "keyword_score": 0,
            "final_score": vector_weight * (r["score"] / max_vector),
        }

    for r in keyword_results:
        kid = r["id"]
        if kid in combined:
            combined[kid]["keyword_score"] = r["keyword_score"]
            combined[kid]["final_score"] += keyword_weight * r["keyword_score"]
        else:
            combined[kid] = {
                "id": kid,
                "vector_score": 0,
                "keyword_score": r["keyword_score"],
                "final_score": keyword_weight * r["keyword_score"],
            }

    paths_cfg = config.get("paths", {})
    wiki_dir = Path(paths_cfg.get("wiki_dir", "wiki"))

    results = sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)[:top_k]

    for r in results:
        md_path = wiki_dir / f"{r['id']}.md"
        content = ""
        if md_path.exists():
            content = md_path.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                content = parts[2] if len(parts) >= 3 else content
        r["content"] = content[:2000]
        r["metadata"] = {
            "page_name": r["id"],
            "title": vault_index.pages.get(r["id"], {}).get("title", r["id"]),
            "type": vault_index.pages.get(r["id"], {}).get("type", ""),
        }

    return results


if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "什么是RAG"
    print(f"Searching: {query}")
    results = hybrid_search_bge(query, top_k=5)
    for i, r in enumerate(results):
        print(f"  {i+1}. [{r['final_score']:.3f}] {r['id']}")
