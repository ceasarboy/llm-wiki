#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-RC: 对比审核模块
按5维度评分标准审核对比分析页面
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_scoring_config
from agent_g import call_llm

SCORING = get_scoring_config()

COMPARE_RUBRIC = {
    "completeness": {"weight": 0.30, "name": "完整性"},
    "accuracy": {"weight": 0.30, "name": "准确性"},
    "structure": {"weight": 0.20, "name": "结构规范性"},
    "discoverability": {"weight": 0.10, "name": "可发现性"},
    "conflict_handling": {"weight": 0.10, "name": "矛盾标注"},
}

PASS_THRESHOLD = 7.5
MAX_FIX_ITERATIONS = 3


@dataclass
class CompareReviewResult:
    page_path: str
    scores: Dict[str, float]
    overall_score: float
    passed: bool
    issues: List[str]
    suggestions: List[str]
    reviewed_at: str


def score_compare_completeness(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    required_sections = ["对比矩阵", "方案详述", "场景化建议"]
    for section in required_sections:
        if section not in body:
            issues.append(f"缺失章节: {section}")
            score -= 2.0

    matrix_match = re.search(r'## 对比矩阵\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
    if matrix_match:
        matrix_text = matrix_match.group(1)
        data_rows = [line for line in matrix_text.split('\n') if line.strip().startswith('|') and not re.match(r'^\|[\s\-|]+\|$', line.strip())]
        if len(data_rows) < 5:
            issues.append(f"对比矩阵维度不足 ({len(data_rows)}行数据)，建议≥5个维度")
            score -= 1.5
    else:
        issues.append("未找到对比矩阵表格")
        score -= 2.0

    if len(body) < 2000:
        issues.append(f"内容过短 ({len(body)} 字符)")
        score -= 1.5

    return max(0, score), issues


def score_compare_accuracy(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    source_count = len(re.findall(r'\[Source:', body))
    if source_count < 5:
        issues.append(f"Source 标注过少 ({source_count}个)，对比数据应有出处")
        score -= 3.0
    elif source_count < 10:
        issues.append(f"Source 标注偏少 ({source_count}个)，建议补充")
        score -= 1.0

    return max(0, score), issues


def score_compare_structure(frontmatter: Dict, body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    if not frontmatter:
        issues.append("缺少 Frontmatter")
        score -= 3.0
    else:
        for field in ["title", "type", "tags"]:
            if field not in frontmatter:
                issues.append(f"Frontmatter 缺少字段: {field}")
                score -= 0.5

    if "## 对比矩阵" not in body:
        issues.append("未使用标准章节格式")
        score -= 1.0

    table_lines = [l for l in body.split('\n') if '|' in l]
    if len(table_lines) < 3:
        issues.append("对比矩阵表格格式不完整")
        score -= 1.5

    return max(0, score), issues


def score_compare_discoverability(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    links = re.findall(r'\[\[([^\]]+)\]\]', body)
    if len(links) < 2:
        issues.append(f"关联论文链接过少 ({len(links)}个)")
        score -= 2.0

    return max(0, score), issues


def score_compare_conflict(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    conflict_markers = re.findall(r'\[Conflict:', body)
    contradictory_words = re.findall(r'然而|但是|相反|矛盾|冲突|不一致', body)

    if contradictory_words and not conflict_markers:
        issues.append(f"检测到 {len(contradictory_words)} 处矛盾表述，但未标记 [Conflict:]")
        score -= 2.0

    return max(0, score), issues


def review_compare(content: str, page_path: str = "") -> CompareReviewResult:
    from review import parse_frontmatter

    frontmatter, body = parse_frontmatter(content)

    scores = {}
    all_issues = []
    all_suggestions = []

    scoring_funcs = {
        "completeness": lambda: score_compare_completeness(body),
        "accuracy": lambda: score_compare_accuracy(body),
        "structure": lambda: score_compare_structure(frontmatter, body),
        "discoverability": lambda: score_compare_discoverability(body),
        "conflict_handling": lambda: score_compare_conflict(body),
    }

    for dim, func in scoring_funcs.items():
        dim_score, dim_issues = func()
        scores[dim] = dim_score
        all_issues.extend(dim_issues)

    overall = sum(
        scores[dim] * COMPARE_RUBRIC[dim]["weight"]
        for dim in scores
    )

    if overall < PASS_THRESHOLD:
        all_suggestions.append(f"综合评分 {overall:.1f} < {PASS_THRESHOLD}，建议补充内容")

    return CompareReviewResult(
        page_path=page_path,
        scores=scores,
        overall_score=overall,
        passed=overall >= PASS_THRESHOLD,
        issues=all_issues,
        suggestions=all_suggestions,
        reviewed_at=datetime.now().isoformat(),
    )


def fix_compare(content: str, review_result: CompareReviewResult) -> str:
    issues_text = "\n".join(f"- {issue}" for issue in review_result.issues)
    prompt = f"""请修复以下对比分析中的问题：

【当前问题】
{issues_text}

【对比分析内容】
{content}

【要求】
1. 修复上述所有问题
2. 保持原有结构和内容不变，只修复问题
3. 确保数据标注 [Source: ...]
4. 不要删除已有内容"""

    result = call_llm(prompt=prompt, system_prompt="你是技术对比分析修复专家。", temperature=0.2, max_tokens=8000)
    return result if result else content


def review_compare_with_fix_cycle(content: str, page_path: str = "", max_iterations: int = MAX_FIX_ITERATIONS):
    current = content

    for iteration in range(max_iterations + 1):
        result = review_compare(current, page_path)
        print(f"  审核轮次 {iteration + 1}: 综合分={result.overall_score:.1f}, 通过={result.passed}")

        if result.passed:
            return result, current

        if iteration < max_iterations:
            print(f"  自动修复 (第 {iteration + 1} 轮)...")
            current = fix_compare(current, result)

    return result, current


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent-RC: 对比审核")
    parser.add_argument("file", help="对比分析文件路径")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"文件不存在: {filepath}")
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")
    result, fixed_content = review_compare_with_fix_cycle(content, str(filepath))

    print(f"\n审核结果: {'通过' if result.passed else '未通过'}")
    print(f"综合分: {result.overall_score:.1f}")
    for dim, score in result.scores.items():
        print(f"  {COMPARE_RUBRIC[dim]['name']}: {score:.1f}")
    if result.issues:
        print("问题:")
        for issue in result.issues:
            print(f"  - {issue}")

    if result.passed and fixed_content != content:
        filepath.write_text(fixed_content, encoding="utf-8")
        print(f"\n修复后的内容已保存")
