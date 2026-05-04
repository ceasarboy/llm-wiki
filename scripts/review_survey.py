#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-RS: 综述审核模块
按5维度评分标准审核综述页面
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

SURVEY_RUBRIC = {
    "completeness": {"weight": 0.30, "name": "完整性"},
    "accuracy": {"weight": 0.30, "name": "准确性"},
    "structure": {"weight": 0.20, "name": "结构性"},
    "readability": {"weight": 0.20, "name": "可读性"},
}

PASS_THRESHOLD = 7.5
MAX_FIX_ITERATIONS = 3


@dataclass
class SurveyReviewResult:
    page_path: str
    scores: Dict[str, float]
    overall_score: float
    passed: bool
    issues: List[str]
    suggestions: List[str]
    reviewed_at: str


def score_survey_completeness(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    if len(body) < 2000:
        issues.append(f"内容过短 ({len(body)} 字符)，建议≥2000字")
        score -= 2.0

    if "## 参考文献" not in body and "##参考文献" not in body:
        issues.append("缺少参考文献章节")
        score -= 2.0

    return max(0, score), issues


def score_survey_accuracy(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    source_count = len(re.findall(r'\[Source:', body))
    fact_sentences = len(re.findall(r'[。！？]', body))

    if fact_sentences > 0:
        coverage = source_count / fact_sentences
        if coverage < 0.5:
            issues.append(f"Source ID 覆盖率过低 ({coverage:.0%})，应≥80%")
            score -= 3.0
        elif coverage < 0.8:
            issues.append(f"Source ID 覆盖率偏低 ({coverage:.0%})，建议补充")
            score -= 1.0
    else:
        issues.append("未检测到事实性陈述")
        score -= 2.0

    return max(0, score), issues


def score_survey_structure(frontmatter: Dict, body: str) -> Tuple[float, List[str]]:
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

    return max(0, score), issues


def score_survey_readability(body: str) -> Tuple[float, List[str]]:
    issues = []
    score = 10.0

    paragraphs = [p for p in body.split('\n\n') if p.strip() and not p.startswith('#')]
    if len(paragraphs) < 3:
        issues.append("段落过少，建议增加内容分段")
        score -= 2.0

    return max(0, score), issues


def review_survey(content: str, page_path: str = "") -> SurveyReviewResult:
    from review import parse_frontmatter

    frontmatter, body = parse_frontmatter(content)

    scores = {}
    all_issues = []
    all_suggestions = []

    scoring_funcs = {
        "completeness": lambda: score_survey_completeness(body),
        "accuracy": lambda: score_survey_accuracy(body),
        "structure": lambda: score_survey_structure(frontmatter, body),
        "readability": lambda: score_survey_readability(body),
    }

    for dim, func in scoring_funcs.items():
        dim_score, dim_issues = func()
        scores[dim] = dim_score
        all_issues.extend(dim_issues)

    overall = sum(
        scores[dim] * SURVEY_RUBRIC[dim]["weight"]
        for dim in scores
    )

    if overall < PASS_THRESHOLD:
        all_suggestions.append(f"综合评分 {overall:.1f} < {PASS_THRESHOLD}，建议补充内容")

    return SurveyReviewResult(
        page_path=page_path,
        scores=scores,
        overall_score=overall,
        passed=overall >= PASS_THRESHOLD,
        issues=all_issues,
        suggestions=all_suggestions,
        reviewed_at=datetime.now().isoformat(),
    )


def fix_survey(content: str, review_result: SurveyReviewResult) -> str:
    issues_text = "\n".join(f"- {issue}" for issue in review_result.issues)
    prompt = f"""请修复以下综述中的问题：

【当前问题】
{issues_text}

【综述内容】
{content}

【要求】
1. 修复上述所有问题
2. 保持原有结构和内容不变，只修复问题
3. 确保每条事实标注 [Source: ...]
4. 不要删除已有内容"""

    result = call_llm(prompt=prompt, system_prompt="你是学术综述修复专家。", temperature=0.2, max_tokens=8000)
    return result if result else content


def review_survey_with_fix_cycle(content: str, page_path: str = "", max_iterations: int = MAX_FIX_ITERATIONS):
    current = content

    for iteration in range(max_iterations + 1):
        result = review_survey(current, page_path)
        print(f"  审核轮次 {iteration + 1}: 综合分={result.overall_score:.1f}, 通过={result.passed}")

        if result.passed:
            return result, current

        if iteration < max_iterations:
            print(f"  自动修复 (第 {iteration + 1} 轮)...")
            current = fix_survey(current, result)

    return result, current


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent-RS: 综述审核")
    parser.add_argument("file", help="综述文件路径")
    args = parser.parse_args()

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"文件不存在: {filepath}")
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")
    result, fixed_content = review_survey_with_fix_cycle(content, str(filepath))

    print(f"\n审核结果: {'通过' if result.passed else '未通过'}")
    print(f"综合分: {result.overall_score:.1f}")
    for dim, score in result.scores.items():
        print(f"  {SURVEY_RUBRIC[dim]['name']}: {score:.1f}")
    if result.issues:
        print("问题:")
        for issue in result.issues:
            print(f"  - {issue}")

    if result.passed and fixed_content != content:
        filepath.write_text(fixed_content, encoding="utf-8")
        print(f"\n修复后的内容已保存")
