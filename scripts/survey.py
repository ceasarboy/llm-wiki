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

SURVEY_SYSTEM_PROMPT = """你是一位行业专家，严谨、细致。请根据用户的提示词和提供的文档内容撰写报告。

【格式要求】
1. 标题：使用 # 一级标题
2. 章节：使用 ## 二级标题组织内容
3. 参考文献：文末必须列出参考文献章节，格式如下：
   ## 参考文献
   - [1] 文档标题
   - [2] 文档标题
4. 引用标注：引用文档内容时标注 [Source: 文档标题] 或 [Source: 文档标题, 章节/页码]
5. 内容长度：建议大于等于2000字，小于等于5000字
6. 使用中文撰写，语言自然流畅，避免生硬的模板化表达
7. 逻辑清晰，章节结构合理，保持学术严谨性的同时，让文章可读性强

【自评机制】
完成报告后，请进行自我审核并评分（满分10分）：

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 完整性 | 30% | 内容充实，覆盖主题各方面 |
| 准确性 | 30% | Source 标注覆盖率≥80% |
| 结构性 | 20% | 有标题、章节、参考文献 |
| 可读性 | 20% | 语言流畅，逻辑清晰 |

在报告末尾添加自评结果：
---
**自评得分：X.X/10**
- 完整性：X/10
- 准确性：X/10
- 结构性：X/10
- 可读性：X/10
---

如果综合得分低于7.5，请重新优化报告后再输出。"""


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
    """生成综述（关键词模式，保留兼容）"""
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

    return _generate_from_collected(papers, keyword)


def generate_survey_from_items(items: List[Dict], topic: str = "", user_prompt: str = "") -> Optional[str]:
    """从选中的项目生成综述"""
    print(f"\n{'='*60}")
    print(f"Agent-S: 开始生成综述 — 选中 {len(items)} 个项目")
    print(f"{'='*60}")

    if not items:
        print("  未选中任何项目")
        return None

    type_counts = {}
    for item in items:
        t = item.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  项目类型分布: {type_counts}")

    return _generate_from_collected(items, topic, user_prompt)


def _generate_from_collected(items: List[Dict], topic: str = "", user_prompt: str = "") -> Optional[str]:
    """从收集的内容生成综述（内部共用）"""
    print(f"\n[2/3] 构建综述 Prompt...")
    
    doc_titles = [item['title'] for item in items]
    items_content = ""
    for i, item in enumerate(items, 1):
        type_label = {"paper": "论文", "entity": "实体", "concept": "概念", "raw": "原文", "synthesis": "综合"}.get(item.get("type", ""), "文档")
        items_content += f"\n---\n### {type_label} {i}: {item['title']}\n\n{item['content']}\n"

    doc_list = "\n".join([f"- {title}" for title in doc_titles])
    
    if user_prompt:
        prompt = f"""{user_prompt}

【参考文档】
{items_content}

【文档列表】
{doc_list}
"""
    else:
        display_topic = topic or "选定主题"
        prompt = f"""请根据以下 {len(items)} 篇文档，撰写关于「{display_topic}」的综述报告。

【文档内容】
{items_content}

【文档列表】
{doc_list}
"""

    print(f"\n[3/3] 调用 LLM 生成综述...")
    result = call_llm(
        prompt=prompt,
        system_prompt=SURVEY_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=10000
    )

    if not result:
        print("  LLM 生成失败")
        return None

    print(f"  综述生成完成: {len(result)} 字符")
    return result


def _extract_title_from_content(content: str) -> str:
    m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def save_survey(keyword: str, content: str) -> Path:
    """保存综述到 wiki/syntheses/ 目录"""
    syntheses_dir = WIKI_DIR / "syntheses"
    syntheses_dir.mkdir(parents=True, exist_ok=True)

    display_title = _extract_title_from_content(content) or keyword or "综述分析"
    safe_name = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', display_title)[:80]
    filename = f"{safe_name}_综述.md"
    filepath = syntheses_dir / filename

    now = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"""---
title: "{display_title}"
type: synthesis
tags: [survey, "{display_title}"]
source: []
created: "{now}"
updated: "{now}"
status: draft
synthesis_date: "{now}"
source_docs: []
query_origin: "{display_title}"
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
