#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-C: 对比分析模块
对多篇论文或多个概念进行对比分析，生成对比矩阵
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

COMPARE_SYSTEM_PROMPT = """你是一位技术对比分析专家。你的任务是根据提供的多篇论文内容，生成结构化的对比分析报告。

【输出格式要求】

# {主题} - 对比分析

## 对比矩阵
| 维度 | 方案A | 方案B | ... |
|------|-------|-------|-----|
| 准确性 | ... | ... | ... |
| 速度 | ... | ... | ... |
| ... | ... | ... | ... |

## 方案详述
### 方案A: {名称}
- 原理简述
- 独特优势
- 已知局限性

### 方案B: {名称}
- 原理简述
- 独特优势
- 已知局限性

## 场景化建议
- "场景A（需要X）→ 选 Y"
- "场景B（需要Z）→ 选 W"

## Source 溯源
{每条数据的出处}

【重要规则】
1. 对比矩阵至少包含 5 个维度
2. 矩阵中每个单元格需要具体数据或评价，不能为空
3. 每条数据必须标注 [Source: 论文标题]
4. 场景化建议要具体，说明为什么选该方案
5. 客观呈现，不要偏向任何一方"""


def collect_papers_by_ids(paper_ids: List[str]) -> List[Dict]:
    """根据论文 ID 列表收集论文内容"""
    papers = []
    for pid in paper_ids:
        paper_file = WIKI_DIR / "papers" / f"{pid}_论文.md"
        if not paper_file.exists():
            paper_file = WIKI_DIR / "papers" / f"{pid}.md"
        if not paper_file.exists():
            try:
                from api.dependencies import vault_index
                for vid, vinfo in vault_index.pages.items():
                    if pid in vid or pid in vinfo.get("title", ""):
                        paper_file = Path(vinfo["file_path"])
                        break
            except Exception:
                pass

        if paper_file.exists():
            content = paper_file.read_text(encoding="utf-8")
            title = paper_file.stem.replace("_论文", "")
            papers.append({"id": pid, "title": title, "content": content[:8000]})
        else:
            print(f"  警告: 未找到论文 {pid}")

    return papers


def collect_papers_by_concepts(concepts: List[str], max_per_concept: int = 5) -> List[Dict]:
    """根据概念关键词收集相关论文"""
    all_papers = []
    seen_ids = set()

    for concept in concepts:
        try:
            from survey import collect_related_papers
            papers = collect_related_papers(concept, max_per_concept)
            for p in papers:
                if p["id"] not in seen_ids and p["type"] == "paper":
                    seen_ids.add(p["id"])
                    all_papers.append(p)
        except Exception as e:
            print(f"  概念 '{concept}' 检索失败: {e}")

    return all_papers


def generate_compare(
    mode: str = "papers",
    paper_ids: List[str] = None,
    concepts: List[str] = None,
    max_per_concept: int = 5
) -> Optional[str]:
    """生成对比分析"""
    print(f"\n{'='*60}")
    print(f"Agent-C: 开始生成对比分析 — 模式: {mode}")
    print(f"{'='*60}")

    print(f"\n[1/3] 收集论文...")
    if mode == "papers" and paper_ids:
        papers = collect_papers_by_ids(paper_ids)
    elif mode == "concepts" and concepts:
        papers = collect_papers_by_concepts(concepts, max_per_concept)
    else:
        print("  错误: 需要指定 paper_ids 或 concepts")
        return None

    if len(papers) < 2:
        print(f"  错误: 至少需要 2 篇论文进行对比，当前只有 {len(papers)} 篇")
        return None

    print(f"  找到 {len(papers)} 篇论文用于对比")

    print(f"\n[2/3] 构建对比 Prompt...")
    papers_content = ""
    for i, paper in enumerate(papers, 1):
        papers_content += f"\n---\n### 方案 {i}: {paper['title']}\n\n{paper['content']}\n"

    topic = " vs ".join([p["title"] for p in papers])
    prompt = f"""请对以下 {len(papers)} 个方案进行对比分析。

【方案内容】
{papers_content}

【对比主题】
{topic}

【要求】
1. 对比矩阵至少 5 个维度
2. 每个单元格有具体数据或评价
3. 每条数据标注 [Source: 论文标题]
4. 场景化建议要具体
"""

    print(f"\n[3/3] 调用 LLM 生成对比分析...")
    result = call_llm(
        prompt=prompt,
        system_prompt=COMPARE_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=8000
    )

    if not result:
        print("  LLM 生成失败")
        return None

    print(f"  对比分析生成完成: {len(result)} 字符")
    return result


def save_compare(topic: str, content: str) -> Path:
    """保存对比分析到 wiki/syntheses/ 目录"""
    syntheses_dir = WIKI_DIR / "syntheses"
    syntheses_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', topic)
    filename = f"{safe_name}_对比.md"
    filepath = syntheses_dir / filename

    now = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"""---
title: "{topic} - 对比分析"
type: synthesis
tags: [comparison, "{topic}"]
source: []
created: "{now}"
updated: "{now}"
status: draft
synthesis_date: "{now}"
source_docs: []
query_origin: "compare:{topic}"
confidence: medium
---

"""

    filepath.write_text(frontmatter + content, encoding="utf-8")
    print(f"  对比分析已保存: {filepath}")
    return filepath


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent-C: 对比分析")
    parser.add_argument("--mode", choices=["papers", "concepts"], required=True)
    parser.add_argument("--ids", nargs="+", help="论文ID列表 (papers模式)")
    parser.add_argument("--concepts", nargs="+", help="概念关键词列表 (concepts模式)")
    parser.add_argument("--max-per-concept", type=int, default=5)
    args = parser.parse_args()

    result = generate_compare(
        mode=args.mode,
        paper_ids=args.ids,
        concepts=args.concepts,
        max_per_concept=args.max_per_concept
    )
    if result:
        topic = " vs ".join(args.ids or args.concepts)
        save_compare(topic, result)
