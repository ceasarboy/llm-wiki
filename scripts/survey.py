#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-S: 综述生成模块
从知识库中检索相关论文，生成结构化综述
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_llm_config, get_paths_config
from agent_g import call_llm

PATHS = get_paths_config()
LLM_CONFIG = get_llm_config()

WIKI_DIR = Path(PATHS["wiki_dir"])
RAW_DIR = Path(PATHS["raw_dir"])
INDEX_DIR = Path(PATHS.get("index_dir", "E:/ragtest/index"))
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"
COLLECTION_NAME = "llm_wiki"

SURVEY_SYSTEM_PROMPT = """你是一位资深学术综述撰写专家。你的任务是根据提供的多篇论文内容，生成一份结构化的学术综述。

【输出格式要求】
你必须严格按照以下结构输出，每个章节都必须包含：

# {主题} - 综述分析

## 时间线
该方向的演进历史，标注关键论文和时间节点。每条事实后标注 [Source: 论文标题]

## 关键突破
里程碑论文及其贡献，含数据支撑。每条事实后标注 [Source: 论文标题]

## 当前 SOTA
目前最先进的方法和结果。每条事实后标注 [Source: 论文标题]

## 开放问题
尚未解决的挑战和未来方向。每条事实后标注 [Source: 论文标题]

## 相关实体
该方向的关键人物、机构、技术，用列表形式

## 参考文献
带 Source ID 的引用列表

【重要规则】
1. 每条事实性陈述必须标注 [Source: 论文标题]
2. 信息保留率 ≥80%，不要过度摘要
3. 时间线按时间顺序排列
4. 关键突破需要包含具体数据
5. 开放问题需要跨论文综合分析"""


def collect_related_papers(keyword: str, max_papers: int = 20) -> List[Dict]:
    """从 ChromaDB 语义检索 + VaultIndex 关键词匹配收集相关论文"""
    papers = []
    seen_ids = set()

    try:
        import chromadb
        from qmd_search_simple import SentenceTransformerEmbedding

        client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
        collection = client.get_collection(name=COLLECTION_NAME)
        embedder = SentenceTransformerEmbedding.get_model()
        query_embedding = embedder.encode([keyword], normalize_embeddings=True).tolist()

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=max_papers * 2,
            include=["documents", "metadatas", "distances"]
        )

        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                content = results["documents"][0][i] if results["documents"] else ""
                papers.append({
                    "id": doc_id,
                    "title": meta.get("title", doc_id),
                    "content": content[:8000],
                    "relevance": 1.0 - (results["distances"][0][i] if results["distances"] else 0),
                    "type": meta.get("type", "unknown"),
                })
    except Exception as e:
        print(f"  ChromaDB 检索失败: {e}")

    try:
        from api.dependencies import vault_index
        keyword_lower = keyword.lower()
        for page_id, page_info in vault_index.pages.items():
            if page_id in seen_ids:
                continue
            title = page_info.get("title", "").lower()
            tags = [t.lower() for t in page_info.get("tags", [])]
            if keyword_lower in title or any(keyword_lower in t for t in tags):
                seen_ids.add(page_id)
                file_path = Path(page_info["file_path"])
                content = ""
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")[:8000]
                papers.append({
                    "id": page_id,
                    "title": page_info.get("title", page_id),
                    "content": content,
                    "relevance": 0.8,
                    "type": page_info.get("type", "unknown"),
                })
    except Exception as e:
        print(f"  VaultIndex 检索失败: {e}")

    papers.sort(key=lambda x: x["relevance"], reverse=True)
    return papers[:max_papers]


def generate_survey(keyword: str, max_papers: int = 20) -> Optional[str]:
    """生成综述"""
    print(f"\n{'='*60}")
    print(f"Agent-S: 开始生成综述 — 关键词: {keyword}")
    print(f"{'='*60}")

    print(f"\n[1/3] 收集相关论文 (max={max_papers})...")
    papers = collect_related_papers(keyword, max_papers)

    if not papers:
        print("  未找到相关论文，无法生成综述")
        return None

    paper_count = len([p for p in papers if p["type"] == "paper"])
    print(f"  找到 {len(papers)} 个相关文档 (其中 {paper_count} 篇论文)")

    print(f"\n[2/3] 构建综述 Prompt...")
    papers_content = ""
    for i, paper in enumerate(papers, 1):
        papers_content += f"\n---\n### 文档 {i}: {paper['title']} (ID: {paper['id']})\n\n{paper['content']}\n"

    prompt = f"""请根据以下 {len(papers)} 篇相关论文，生成关于「{keyword}」的学术综述。

【论文内容】
{papers_content}

【要求】
1. 严格按照指定格式输出
2. 每条事实后标注 [Source: 论文标题]
3. 综合多篇论文的观点，不要只依赖单篇
4. 信息保留率 ≥80%
"""

    print(f"\n[3/3] 调用 LLM 生成综述...")
    result = call_llm(
        prompt=prompt,
        system_prompt=SURVEY_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=8000
    )

    if not result:
        print("  LLM 生成失败")
        return None

    print(f"  综述生成完成: {len(result)} 字符")
    return result


def save_survey(keyword: str, content: str) -> Path:
    """保存综述到 wiki/syntheses/ 目录"""
    syntheses_dir = WIKI_DIR / "syntheses"
    syntheses_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', keyword)
    filename = f"{safe_name}_综述.md"
    filepath = syntheses_dir / filename

    now = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"""---
title: "{keyword} - 综述分析"
type: synthesis
tags: [survey, "{keyword}"]
source: []
created: "{now}"
updated: "{now}"
status: draft
synthesis_date: "{now}"
source_docs: []
query_origin: "{keyword}"
confidence: medium
---

"""

    filepath.write_text(frontmatter + content, encoding="utf-8")
    print(f"  综述已保存: {filepath}")
    return filepath


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent-S: 综述生成")
    parser.add_argument("keyword", help="综述关键词")
    parser.add_argument("--max-papers", type=int, default=20, help="最大论文数")
    args = parser.parse_args()

    result = generate_survey(args.keyword, args.max_papers)
    if result:
        save_survey(args.keyword, result)
