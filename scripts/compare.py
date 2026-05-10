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

COMPARE_SYSTEM_PROMPT = """你是一位行业专家，严谨、细致。请根据用户的提示词和提供的文档内容撰写对比分析报告。

【格式要求】
1. 标题：使用 # 一级标题
2. 对比矩阵：使用表格形式对比各方案的多个维度
3. 方案详述：每个方案单独章节，说明原理、优势、局限
4. 场景建议：根据不同场景给出选型建议
5. 参考文献：文末必须列出参考文献章节，格式如下：
   ## 参考文献
   - [1] 文档标题
   - [2] 文档标题
6. 引用标注：引用文档内容时标注 [Source: 文档标题] 或 [Source: 文档标题, 章节/页码]
7. 内容长度：建议大于等于2000字，小于等于5000字
8. 使用中文撰写，语言自然流畅，避免生硬的模板化表达
9. 逻辑清晰，客观呈现，不要偏向任何一方

【自评机制】
完成报告后，请进行自我审核并评分（满分10分）：

| 维度 | 权重 | 评分标准 |
|------|------|---------|
| 完整性 | 30% | 对比维度全面，覆盖各方案特点 |
| 准确性 | 30% | Source 标注覆盖率≥80% |
| 结构性 | 20% | 有标题、对比矩阵、参考文献 |
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
    """生成对比分析（保留兼容）"""
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

    return _generate_from_collected(papers, "")


def generate_compare_from_items(items: List[Dict], topic: str = "", user_prompt: str = "") -> Optional[str]:
    """从选中的项目生成对比分析"""
    print(f"\n{'='*60}")
    print(f"Agent-C: 开始生成对比分析 — 选中 {len(items)} 个项目")
    print(f"{'='*60}")

    if len(items) < 2:
        print(f"  错误: 至少需要 2 个项目进行对比，当前只有 {len(items)} 个")
        return None

    type_counts = {}
    for item in items:
        t = item.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  项目类型分布: {type_counts}")

    return _generate_from_collected(items, topic, user_prompt)


def _generate_from_collected(items: List[Dict], topic: str = "", user_prompt: str = "") -> Optional[str]:
    """从收集的内容生成对比分析（内部共用）"""
    print(f"  找到 {len(items)} 个项目用于对比")

    print(f"\n[2/3] 构建对比 Prompt...")
    
    doc_titles = [item['title'] for item in items]
    items_content = ""
    for i, item in enumerate(items, 1):
        type_label = {"paper": "论文", "entity": "实体", "concept": "概念", "raw": "原文", "synthesis": "综合"}.get(item.get("type", ""), "方案")
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
        display_topic = topic or " vs ".join([item["title"][:20] for item in items[:4]])
        prompt = f"""请对以下 {len(items)} 个方案进行对比分析。

【方案内容】
{items_content}

【对比主题】
{display_topic}

【文档列表】
{doc_list}
"""

    print(f"\n[3/3] 调用 LLM 生成对比分析...")
    result = call_llm(
        prompt=prompt,
        system_prompt=COMPARE_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=10000
    )

    if not result:
        print("  LLM 生成失败")
        return None

    print(f"  对比分析生成完成: {len(result)} 字符")
    return result


def _extract_title_from_content(content: str) -> str:
    m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def save_compare(topic: str, content: str) -> Path:
    """保存对比分析到 wiki/syntheses/ 目录"""
    syntheses_dir = WIKI_DIR / "syntheses"
    syntheses_dir.mkdir(parents=True, exist_ok=True)

    display_title = _extract_title_from_content(content) or topic or "对比分析"
    safe_name = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', display_title)[:80]
    filename = f"{safe_name}_对比.md"
    filepath = syntheses_dir / filename

    now = datetime.now().strftime("%Y-%m-%d")
    frontmatter = f"""---
title: "{display_title}"
type: synthesis
tags: [comparison, "{display_title}"]
source: []
created: "{now}"
updated: "{now}"
status: draft
synthesis_date: "{now}"
source_docs: []
query_origin: "compare:{display_title}"
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
