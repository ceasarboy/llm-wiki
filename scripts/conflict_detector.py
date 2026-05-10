#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-D: 冲突检测模块
自动发现知识库中同主题页面之间的矛盾，生成冲突报告。
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_llm_config, get_paths_config
from agent_g import call_llm

LLM_CONFIG = get_llm_config()
PATHS = get_paths_config()

WIKI_DIR = Path(PATHS["wiki_dir"])

CONFLICT_SYSTEM_PROMPT = """你是一位严谨的学术审核者。你的任务是：

1. 仔细阅读两篇知识库页面（A 和 B）
2. 判断它们是否在同一个主题上存在矛盾（不一致的主张、冲突的数据、相反的结论等）
3. 如果存在矛盾，明确指出矛盾点并用 [Conflict: ...] 格式标记

【判定标准】
- 真正矛盾：两篇页面在同一事实上给出不可调和的不同信息
- 非矛盾：不同角度的补充、不同实验条件下的不同结果、不同时间点的合理演进
- 疑似矛盾：无法确定是否矛盾的情况，标记为 [Conflict-疑似: ...]

【输出格式】
如果存在矛盾，输出 JSON：

{
  "has_conflict": true,
  "page_a": "页面A标题",
  "page_b": "页面B标题",
  "conflicts": [
    {
      "topic": "矛盾主题",
      "claim_a": "页面A的主张",
      "claim_b": "页面B的主张",
      "severity": "high|medium|low",
      "conflict_tag": "[Conflict: 具体矛盾描述]"
    }
  ]
}

如果没有矛盾，输出：
{
  "has_conflict": false
}

只输出 JSON，不要输出任何其他内容。"""


def load_frontmatter(filepath: Path) -> Dict:
    """解析页面的 YAML frontmatter"""
    try:
        text = filepath.read_text(encoding='utf-8')
        if text.startswith('---'):
            end = text.find('---', 3)
            if end > 0:
                yaml_text = text[3:end].strip()
                fm = {}
                for line in yaml_text.split('\n'):
                    line = line.strip()
                    if ':' in line and not line.startswith('#'):
                        key, _, val = line.partition(':')
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        fm[key] = val
                return fm
    except Exception:
        pass
    return {}


def parse_tags_and_fields(fm: Dict) -> Tuple[Set[str], Set[str]]:
    """从 frontmatter 提取 tags 和 related fields"""
    tags = set()
    fields = set()

    raw_tags = fm.get('tags', '')
    if isinstance(raw_tags, str):
        tags = {t.strip().strip('"').strip("'") for t in raw_tags.strip('[]').split(',') if t.strip()}
    elif isinstance(raw_tags, list):
        tags = set(raw_tags)

    raw_fields = fm.get('related_fields', '')
    if isinstance(raw_fields, str):
        fields = {f.strip().strip('"').strip("'") for f in raw_fields.strip('[]').split(',') if f.strip()}
    elif isinstance(raw_fields, list):
        fields = set(raw_fields)

    return tags, fields


def extract_main_points(text: str, max_length: int = 3000) -> str:
    """提取页面核心内容（去除 frontmatter 后的正文摘要）"""
    if text.startswith('---'):
        end = text.find('---', 3)
        if end > 0:
            text = text[end + 3:]
    text = re.sub(r'\[Conflict:.*?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Conflict-疑似:.*?\]', '', text, flags=re.DOTALL)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    result = '\n'.join(lines)
    if len(result) > max_length:
        result = result[:max_length] + '\n... [内容截断]'
    return result


def find_candidate_pairs(wiki_dir: Path, min_overlap: int = 1, max_pairs: int = 50) -> List[Tuple[Path, Path, int]]:
    """查找可能矛盾的页面对（共享 tags 或 related_fields）"""
    pages = []
    for md_file in wiki_dir.rglob('*.md'):
        fm = load_frontmatter(md_file)
        tags, fields = parse_tags_and_fields(fm)
        if tags or fields:
            pages.append((md_file, fm, tags, fields))

    pairs = []
    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            f1, _, t1, r1 = pages[i]
            f2, _, t2, r2 = pages[j]
            overlap = len(t1 & t2) + len(r1 & r2)
            if overlap >= min_overlap:
                pairs.append((f1, f2, overlap))

    pairs.sort(key=lambda x: -x[2])
    return pairs[:max_pairs]


def detect_conflicts(
    wiki_dir: Path = None,
    output_file: Path = None,
    min_overlap: int = 1,
    max_pairs: int = 30,
) -> Dict:
    """主函数：检测知识库中的矛盾"""

    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    if output_file is None:
        output_file = wiki_dir.parent / "conflict_report.json"

    print(f"扫描目录: {wiki_dir}")
    print(f"最小重叠度: {min_overlap} | 最大比对对: {max_pairs}")
    print()

    pairs = find_candidate_pairs(wiki_dir, min_overlap, max_pairs)
    print(f"找到 {len(pairs)} 对候选页面")

    results = {
        "scan_date": datetime.now().isoformat(),
        "wiki_dir": str(wiki_dir),
        "total_pairs_scanned": len(pairs),
        "conflicts_found": [],
        "summary": {"high": 0, "medium": 0, "low": 0, "suspected": 0},
    }

    for idx, (file_a, file_b, overlap) in enumerate(pairs, 1):
        title_a = file_a.stem
        title_b = file_b.stem
        print(f"\n[{idx}/{len(pairs)}] {title_a}  vs  {title_b}  (重叠度: {overlap})")

        text_a = extract_main_points(file_a.read_text(encoding='utf-8'), 2500)
        text_b = extract_main_points(file_b.read_text(encoding='utf-8'), 2500)

        prompt = f"""请分析以下两篇知识库页面是否存在矛盾：

【页面 A】{title_a}
{text_a}

【页面 B】{title_b}
{text_b}"""

        response = call_llm(prompt, CONFLICT_SYSTEM_PROMPT, temperature=0.2, max_tokens=3000)
        if response is None:
            print("  LLM 调用失败，跳过")
            continue

        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)
        except json.JSONDecodeError:
            print(f"  JSON 解析失败，原始响应: {response[:200]}")
            continue

        if result.get("has_conflict"):
            page_pair = {
                "page_a": str(file_a),
                "page_b": str(file_b),
                "conflicts": result["conflicts"],
            }
            results["conflicts_found"].append(page_pair)

            for c in result["conflicts"]:
                sev = c.get("severity", "low")
                results["summary"][sev] = results["summary"].get(sev, 0) + 1
                print(f"  发现矛盾 [{sev}]: {c.get('topic', 'unknown')}")

                conflict_tag = c.get("conflict_tag", "")
                if conflict_tag:
                    for target_file in [file_a, file_b]:
                        content = target_file.read_text(encoding='utf-8')
                        if conflict_tag not in content:
                            marker_line = f"\n{conflict_tag}\n"
                            with open(target_file, 'a', encoding='utf-8') as f:
                                f.write(marker_line)
                            print(f"    已标记: {target_file.name}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {output_file}")

    total = sum(results["summary"].values())
    print(f"\n总结: 发现 {total} 个矛盾点")
    print(f"  high={results['summary']['high']}, medium={results['summary']['medium']}, low={results['summary']['low']}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent-D: 知识库冲突检测")
    parser.add_argument("--wiki-dir", type=str, default=None, help="Wiki 目录路径")
    parser.add_argument("--output", type=str, default=None, help="冲突报告输出文件")
    parser.add_argument("--min-overlap", type=int, default=1, help="最小标签/领域重叠数")
    parser.add_argument("--max-pairs", type=int, default=30, help="最大比对页面对数")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir) if args.wiki_dir else WIKI_DIR
    output_file = Path(args.output) if args.output else wiki_dir.parent / "conflict_report.json"

    detect_conflicts(
        wiki_dir=wiki_dir,
        output_file=output_file,
        min_overlap=args.min_overlap,
        max_pairs=args.max_pairs,
    )