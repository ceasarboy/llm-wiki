#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质量审核脚本 (Agent-R)
按评分标准审核生成的 wiki 页面
支持修正循环：审核不通过→LLM修正→重新审核→循环直到通过
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_scoring_config, get_llm_config

# =============================================================================
# 配置
# =============================================================================

SCORING_CONFIG = get_scoring_config()
LLM_CONFIG = get_llm_config()

SCORING_RUBRIC = {
    "completeness": {"weight": SCORING_CONFIG["weights"]["completeness"], "name": "完整性"},
    "accuracy": {"weight": SCORING_CONFIG["weights"]["accuracy"], "name": "准确性"},
    "structure": {"weight": SCORING_CONFIG["weights"]["structure"], "name": "结构规范性"},
    "discoverability": {"weight": SCORING_CONFIG["weights"]["discoverability"], "name": "可发现性"},
    "conflict_handling": {"weight": SCORING_CONFIG["weights"]["conflict_handling"], "name": "冲突处理"},
}

PASS_THRESHOLD = SCORING_CONFIG["pass_threshold"]
MAX_FIX_ITERATIONS = 3

# =============================================================================
# 数据类
# =============================================================================

@dataclass
class ReviewResult:
    page_path: str
    scores: Dict[str, float]
    overall_score: float
    passed: bool
    issues: List[str]
    suggestions: List[str]
    reviewed_at: str


# =============================================================================
# 评分函数
# =============================================================================

def parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """解析 YAML Frontmatter"""
    # 去除开头的空白字符
    content = content.lstrip()
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            import yaml
            try:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return frontmatter or {}, body
            except Exception:
                pass
    return {}, content


def score_completeness(_frontmatter: Dict, body: str, _original_doc: str = None, content_type: str = "paper") -> Tuple[float, List[str]]:
    """
    完整性评分
    检查关键章节是否存在及内容质量
    """
    issues = []
    score = 10.0
    
    if content_type == "paper":
        required_sections = ["问题定义", "方法", "实验", "结论"]
        for section in required_sections:
            if section not in body:
                issues.append(f"缺失章节: {section}")
                score -= 1.5
        
        if len(body) < 2000:
            issues.append(f"内容过短 ({len(body)} 字符)，可能过度摘要")
            score -= 2.0
        elif len(body) < 3000:
            issues.append(f"内容偏短 ({len(body)} 字符)，建议补充细节")
            score -= 0.5
        
        method_match = re.search(r'## 方法\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if method_match:
            method_text = method_match.group(1).strip()
            method_chars = len(method_text)
            if method_chars < 300:
                issues.append(f"方法章节过短 ({method_chars} 字符)，缺少技术细节")
                score -= 2.0
            elif method_chars < 500:
                issues.append(f"方法章节偏短 ({method_chars} 字符)，建议补充子方法描述")
                score -= 1.0
            
            if '•' not in method_text and '-' not in method_text and '1.' not in method_text and '2.' not in method_text:
                issues.append("方法章节缺少结构化描述（无列表/编号）")
                score -= 0.5
        else:
            issues.append("未找到方法章节内容")
            score -= 1.0
        
        experiment_match = re.search(r'## 实验验证\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if experiment_match:
            exp_text = experiment_match.group(1).strip()
            has_numbers = bool(re.search(r'\d+\.?\d*%|\d+\.?\d*\s*(倍|个|次|GB|MB|ms|秒|epoch|layer)', exp_text))
            if not has_numbers:
                issues.append("实验章节缺少具体数值结果")
                score -= 1.5
        else:
            issues.append("未找到实验章节内容")
            score -= 1.0
    
    elif content_type == "entity":
        if "## 概述" not in body and "## Overview" not in body:
            issues.append("缺失概述章节")
            score -= 2.0
        if "## 关键信息" not in body and "## Key Information" not in body:
            issues.append("缺失关键信息章节")
            score -= 2.0
        if "## 引用来源" not in body and "## References" not in body:
            issues.append("缺失引用来源章节")
            score -= 1.5
        if len(body) < 200:
            issues.append(f"实体内容过短 ({len(body)} 字符)")
            score -= 2.0
        
        overview_match = re.search(r'## 概述\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if overview_match:
            overview_text = overview_match.group(1).strip()
            if len(overview_text) < 20:
                issues.append("概述内容过短，缺少有效描述")
                score -= 1.0
    
    elif content_type == "concept":
        has_definition = any(s in body for s in ["## 定义", "## Definition", "## 概述", "## Overview"])
        if not has_definition:
            issues.append("缺失定义/概述章节")
            score -= 2.0
        
        has_features = any(s in body for s in ["## 核心特征", "## Core Features", "## 技术特点", "## Technical Features", "## 特点"])
        if not has_features:
            issues.append("缺失核心特征/技术特点章节")
            score -= 1.5
        
        if len(body) < 300:
            issues.append(f"概念内容过短 ({len(body)} 字符)")
            score -= 2.0
        
        overview_match = re.search(r'## 概述\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if overview_match:
            overview_text = overview_match.group(1).strip()
            if len(overview_text) < 30:
                issues.append("概述内容过短，缺少有效定义")
                score -= 1.0
    
    placeholder_patterns = [r'\[待.*?补充\]', r'\[待提取\]', r'\[待关联\]']
    placeholder_count = 0
    for pattern in placeholder_patterns:
        placeholder_count += len(re.findall(pattern, body))
    
    if placeholder_count > 5:
        issues.append(f"占位符过多 ({placeholder_count} 处)，内容不完整")
        score -= 2.0
    elif placeholder_count > 0:
        issues.append(f"存在占位符 ({placeholder_count} 处)")
        score -= 0.5
    
    return max(0, score), issues


def score_accuracy(frontmatter: Dict, body: str, content_type: str = "paper") -> Tuple[float, List[str]]:
    """
    准确性评分
    检查 Source ID 标注比例（仅对实体和概念检查，论文不需要 Source ID）
    
    否决项：
    - Entity/Concept: 无 source 链接且无 Source ID
    """
    issues = []
    score = 10.0
    is_veto = False
    
    # 论文不需要 Source ID，直接返回满分
    if content_type == "paper":
        issues.append("论文类型无需 Source ID 标注，跳过准确性检查")
        return score, issues
    
    # 根据类型设置不同的阈值
    if content_type == "entity":
        min_ratio = 0.1
        good_ratio = 0.3
    elif content_type == "concept":
        min_ratio = 0.1
        good_ratio = 0.3
    else:
        min_ratio = 0.5
        good_ratio = 0.8
    
    # 统计 Source ID（支持多种格式）
    source_pattern = r'\[Source:\s*[^\]]+\]'
    source_matches = re.findall(source_pattern, body)
    
    # 统计陈述句（简单估计）
    statement_pattern = r'[^.!?。！？\n]+[.!?。！？]'
    statements = re.findall(statement_pattern, body)
    
    # 统计不同类型的引用
    title_refs = re.findall(r'\[Source:\s*[^\]]+\]', body)
    title_refs = [r for r in title_refs if 'paragraph_' not in r]
    
    # 检查 source 链接（优先检查 frontmatter，其次检查 body）
    has_source_link = False
    if frontmatter:
        source_field = frontmatter.get("source", "")
        if source_field and "[[" in str(source_field):
            has_source_link = True
    
    # 如果 frontmatter 中没有，检查 body 中
    if not has_source_link:
        source_link_pattern = r'source:\s*\[\[[^\]]+\]\]'
        has_source_link = re.search(source_link_pattern, body) is not None
    
    # 对于entity和concept，检查否决项
    if content_type in ["entity", "concept"]:
        if len(source_matches) == 0 and not has_source_link:
            issues.append("【否决项】实体/概念缺少 source 链接且无 Source ID 标注")
            is_veto = True
            score = 0.0
            return score, issues
        elif len(source_matches) == 0 and has_source_link:
            issues.append("【否决项】实体/概念缺少段落级 Source ID 标注")
            is_veto = True
            score = 0.0
            return score, issues
    
    if len(statements) > 0:
        source_ratio = len(source_matches) / len(statements)
        if source_ratio < min_ratio:
            issues.append(f"Source ID 比例过低 ({source_ratio:.1%}, {len(source_matches)}/{len(statements)})")
            score -= 5.0
        elif source_ratio < good_ratio:
            issues.append(f"Source ID 比例不足 ({source_ratio:.1%}，建议 ≥{good_ratio:.0%})")
            score -= 2.0
        else:
            issues.append(f"Source ID 比例良好 ({source_ratio:.1%})")
    else:
        issues.append("未检测到陈述句")
        score -= 3.0
    
    # 检查 Source ID 格式（使用论文标题）
    if title_refs:
        issues.append(f"使用标题引用: {len(title_refs)} 处")
    
    # 检查是否有旧格式的 paragraph 引用
    old_format_refs = [r for r in source_matches if 'paragraph_' in r]
    if old_format_refs:
        issues.append(f"使用旧格式引用: {len(old_format_refs)} 处 (建议改用论文标题)")
        score -= 1.0
    
    return max(0, score), issues


def score_structure(frontmatter: Dict, _body: str, content_type: str = "paper") -> Tuple[float, List[str]]:
    """
    结构规范性评分
    检查 Frontmatter 和命名
    根据内容类型检查不同的必填字段
    """
    issues = []
    score = 10.0
    
    # 检查 frontmatter 是否成功解析
    if not frontmatter:
        issues.append("Frontmatter 解析失败或为空")
        score -= 5.0
        return max(0, score), issues
    
    # 根据类型设置不同的必填字段
    base_fields = ["title", "type", "source", "created", "updated", "status"]
    
    if content_type == "paper":
        type_specific_fields = ["arxiv_id"]
    elif content_type == "entity":
        type_specific_fields = ["entity_type"]
    elif content_type == "concept":
        type_specific_fields = ["concept_type"]
    else:
        type_specific_fields = []
    
    required_fields = base_fields + type_specific_fields
    
    for field in required_fields:
        value = frontmatter.get(field)
        if value is None or value == "" or value == []:
            issues.append(f"Frontmatter 缺失必填字段: {field}")
            score -= 1.0
    
    # 检查 type 字段值
    valid_types = ["entity", "concept", "paper", "summary", "synthesis"]
    page_type = frontmatter.get("type")
    if page_type not in valid_types:
        issues.append(f"type 字段值无效: {page_type} (应为: {', '.join(valid_types)})")
        score -= 1.0
    
    # 检查 status 字段值
    valid_status = ["draft", "generated", "reviewed", "stable", "requires_manual_review"]
    page_status = frontmatter.get("status")
    if page_status not in valid_status:
        issues.append(f"status 字段值无效: {page_status} (应为: {', '.join(valid_status)})")
        score -= 0.5
    
    # 检查 title 是否有效
    title = frontmatter.get("title", "")
    if not title or title in ["Untitled", "", None]:
        issues.append("title 字段为空或无效")
        score -= 1.0
    elif len(str(title)) > 200:
        issues.append(f"title 过长 ({len(str(title))} 字符)")
        score -= 0.5
    
    # 检查 entity_type 或 concept_type 是否有效
    if content_type == "entity":
        entity_type = frontmatter.get("entity_type", "")
        valid_entity_types = ["person", "organization", "location", "device", "dataset", "project", "technology"]
        if entity_type and entity_type not in valid_entity_types:
            issues.append(f"entity_type 值可能不规范: {entity_type}")
            score -= 0.5
    
    if content_type == "concept":
        concept_type = frontmatter.get("concept_type", "")
        valid_concept_types = ["algorithm", "methodology", "learning-paradigm", "technical-idea", "framework", "paper"]
        if concept_type and concept_type not in valid_concept_types:
            issues.append(f"concept_type 值可能不规范: {concept_type}")
            score -= 0.5
    
    return max(0, score), issues


def score_discoverability(frontmatter: Dict, body: str, content_type: str = "paper") -> Tuple[float, List[str]]:
    """
    可发现性评分
    检查交叉引用
    根据内容类型调整链接数量要求
    
    否决项：
    - 完全没有任何链接（包括 source 链接和交叉引用）
    """
    issues = []
    score = 10.0
    
    # 根据类型设置不同的链接数量要求
    if content_type == "paper":
        min_links = 3
    elif content_type == "entity":
        min_links = 1
    elif content_type == "concept":
        min_links = 2
    else:
        min_links = 3
    
    # 检查 body 中的链接
    link_pattern = r'\[\[([^\]]+)\]\]'
    body_links = re.findall(link_pattern, body)
    
    # 检查 frontmatter 中的 source 字段
    frontmatter_links = []
    if frontmatter:
        source_field = frontmatter.get("source", "")
        if source_field:
            # 提取 source 字段中的链接
            fm_links = re.findall(link_pattern, str(source_field))
            frontmatter_links.extend(fm_links)
    
    # 合并所有链接
    all_links = body_links + frontmatter_links
    
    # 检查否决项：完全没有任何链接
    if len(all_links) == 0:
        issues.append("【否决项】完全没有任何链接，无法溯源或关联")
        return 0.0, issues
    
    # 检查是否有返回链接或来源链接
    source_links = [l for l in all_links if 'raw/' in l or 'wiki/' in l]
    
    # 对于 entity/concept，必须有 source 链接
    if content_type in ["entity", "concept"]:
        if len(source_links) == 0:
            issues.append("【否决项】实体/概念缺少 source 来源链接")
            return 0.0, issues
    
    if len(all_links) < min_links:
        issues.append(f"交叉引用过少 ({len(all_links)} 个，建议 ≥{min_links})")
        score -= 2.0
    
    if len(source_links) < 1:
        issues.append("缺少来源或相关页面链接")
        score -= 2.0
    
    return max(0, score), issues


def score_conflict_handling(frontmatter: Dict, body: str) -> Tuple[float, List[str]]:
    """
    冲突处理评分
    检查 Conflict 标记
    """
    issues = []
    score = 10.0
    
    # 检查是否有 Conflict 标记
    conflict_pattern = r'\[Conflict:[^\]]+\]'
    conflicts = re.findall(conflict_pattern, body)
    
    # 注意：没有冲突是正常情况，不扣分
    # 但如果检测到潜在的矛盾数据而未标记，应该扣分
    # 这里简化处理：假设如果没有 Conflict 标记就是无冲突
    
    # 检查 Conflict 格式
    for conflict in conflicts:
        if 'vs' not in conflict and '来源' not in conflict:
            issues.append(f"Conflict 标记格式不规范: {conflict}")
            score -= 1.0
    
    return max(0, score), issues


def calculate_overall_score(scores: Dict[str, float]) -> float:
    """计算综合分"""
    overall = 0.0
    for dimension, config in SCORING_RUBRIC.items():
        overall += scores.get(dimension, 0) * config["weight"]
    return round(overall, 2)


# =============================================================================
# 审核报告生成
# =============================================================================

def generate_review_report(result: ReviewResult) -> str:
    """生成审核报告 Markdown"""
    
    report = f"""# 审核报告

## 基本信息
- **页面**: {result.page_path}
- **审核时间**: {result.reviewed_at}
- **审核者**: Agent-R

## 评分详情

| 维度 | 得分 | 权重 | 加权分 | 说明 |
|------|------|------|--------|------|
"""
    
    for dimension, config in SCORING_RUBRIC.items():
        score = result.scores.get(dimension, 0)
        weight = config["weight"]
        weighted = round(score * weight, 2)
        name = config["name"]
        report += f"| {name} | {score} | {weight*100:.0f}% | {weighted} | - |\n"
    
    report += f"| **综合分** | - | - | **{result.overall_score}** | - |\n"
    
    report += f"\n## 结论\n\n"
    if result.passed:
        report += f"✅ **通过**（综合分 ≥ {PASS_THRESHOLD}）\n"
    else:
        report += f"❌ **打回重写**（综合分 < {PASS_THRESHOLD}）\n"
    
    if result.issues:
        report += f"\n## 问题列表\n\n"
        for i, issue in enumerate(result.issues, 1):
            report += f"{i}. {issue}\n"
    
    if result.suggestions:
        report += f"\n## 修改建议\n\n"
        for i, suggestion in enumerate(result.suggestions, 1):
            report += f"{i}. {suggestion}\n"
    
    return report


# =============================================================================
# 主函数
# =============================================================================

def review_page(page_path: Path, content_type: str = None) -> ReviewResult:
    """审核单个页面"""
    
    with open(page_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    frontmatter, body = parse_frontmatter(content)
    
    if content_type is None:
        content_type = frontmatter.get("type", "paper")
    
    scores = {}
    all_issues = []
    all_suggestions = []
    
    score, issues = score_completeness(frontmatter, body, content_type=content_type)
    scores["completeness"] = score
    all_issues.extend(issues)
    
    score, issues = score_accuracy(frontmatter, body, content_type=content_type)
    scores["accuracy"] = score
    all_issues.extend(issues)
    
    score, issues = score_structure(frontmatter, body, content_type=content_type)
    scores["structure"] = score
    all_issues.extend(issues)
    
    score, issues = score_discoverability(frontmatter, body, content_type=content_type)
    scores["discoverability"] = score
    all_issues.extend(issues)
    
    score, issues = score_conflict_handling(frontmatter, body)
    scores["conflict_handling"] = score
    all_issues.extend(issues)
    
    # 计算综合分
    overall = calculate_overall_score(scores)
    
    # 根据类型生成不同的建议
    if overall < PASS_THRESHOLD:
        if content_type == "paper":
            all_suggestions.append("补充缺失的关键章节（问题定义、方法、实验、结论）")
            if scores["completeness"] < 7:
                all_suggestions.append("参考原始文档，补充技术细节，避免过度摘要")
        elif content_type == "entity":
            all_suggestions.append("补充概述和关键信息章节")
            all_suggestions.append("确保source链接正确指向原始文档")
            all_suggestions.append("为每个段落添加 [Source: 论文标题] 标注")
            if scores["completeness"] < 7:
                all_suggestions.append("增加实体的详细描述信息")
        elif content_type == "concept":
            all_suggestions.append("补充定义和核心特征章节")
            all_suggestions.append("确保source链接正确指向原始文档")
            if scores["completeness"] < 7:
                all_suggestions.append("增加概念的应用场景和原理说明")
    
    return ReviewResult(
        page_path=str(page_path),
        scores=scores,
        overall_score=overall,
        passed=overall >= PASS_THRESHOLD,
        issues=all_issues,
        suggestions=all_suggestions,
        reviewed_at=datetime.now().isoformat()
    )


def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki 质量审核脚本 (Agent-R)")
    parser.add_argument("--file", type=str, help="审核单个文件")
    parser.add_argument("--batch", type=str, help="批量审核，传入目录路径")
    parser.add_argument("--output-dir", type=str, default="E:/ragtest/reviewed",
                        help="审核报告输出目录")
    args = parser.parse_args()
    
    print("=" * 60)
    print("LLM-Wiki Review 脚本 v3.0 (Agent-R)")
    print("=" * 60)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pages_to_review = []
    
    if args.file:
        pages_to_review.append(Path(args.file))
    elif args.batch:
        batch_dir = Path(args.batch)
        pages_to_review.extend(batch_dir.glob("**/*.md"))
    else:
        print("错误: 请指定 --file 或 --batch")
        return 1
    
    print(f"\n待审核页面: {len(pages_to_review)} 个")
    
    results = []
    passed_count = 0
    failed_count = 0
    
    for i, page_path in enumerate(pages_to_review, 1):
        print(f"\n[{i}/{len(pages_to_review)}] 审核: {page_path.name}")
        
        try:
            result = review_page(page_path)
            
            # 打印评分摘要
            print(f"      综合分: {result.overall_score}/10", end="")
            if result.passed:
                print(" [PASS]")
                passed_count += 1
            else:
                print(" [FAIL]")
                failed_count += 1
            
            print(f"      各维度: ", end="")
            for dim, score in result.scores.items():
                print(f"{dim[:3]}={score}", end=" ")
            print()
            
            if result.issues:
                print(f"      问题: {len(result.issues)} 个")
            
            # 保存审核报告
            report_file = output_dir / f"{page_path.stem}_review.md"
            report_content = generate_review_report(result)
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            results.append({
                "page": str(page_path),
                "overall_score": result.overall_score,
                "passed": result.passed,
                "scores": result.scores,
                "issue_count": len(result.issues)
            })
            
        except Exception as e:
            print(f"      错误: {e}")
            results.append({
                "page": str(page_path),
                "status": "error",
                "error": str(e)
            })
    
    # 保存汇总结果
    summary_file = output_dir / "review_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump({
            "reviewed_at": datetime.now().isoformat(),
            "total": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "pass_rate": round(passed_count / len(results) * 100, 1) if results else 0,
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"审核完成: {passed_count} 通过, {failed_count} 打回")
    print(f"通过率: {passed_count / len(results) * 100:.1f}%" if results else "N/A")
    print(f"报告保存: {output_dir}")
    print(f"{'=' * 60}")
    
    return 0


# =============================================================================
# LLM 修正功能
# =============================================================================

def call_llm(prompt: str, temperature: float = 0.2) -> str:
    """调用 LLM"""
    import requests
    
    api_url = LLM_CONFIG.get("api_url", "http://127.0.0.1:28789/v1/chat/completions")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", "default")
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        response = requests.post(
            api_url,
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是知识库内容修正专家。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": 8000
            },
            timeout=300
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    LLM调用失败: {e}")
        return None


def fix_content_with_llm(content: str, issues: List[str], suggestions: List[str], content_type: str) -> Optional[str]:
    """
    使用 LLM 修正内容
    
    参数:
        content: 原始内容
        issues: 问题列表
        suggestions: 修改建议
        content_type: 内容类型 (paper/entity/concept)
    
    返回:
        修正后的内容，失败返回 None
    """
    if content_type == "entity":
        format_requirements = """[实体格式要求]
title: "中文名-英文名"（如：李飞飞-Li Fei-Fei）
type: entity
entity_type: person|organization|dataset|device

## 概述
[中文描述] [Source: 来源文章标题]

## 关键信息
- **属性**: 值 [Source: 来源文章标题]

## 引用来源
- [文章标题](链接) - 该文章如何提及此实体"""
    elif content_type == "concept":
        format_requirements = """[概念格式要求]
title: "中文名-英文名"（如：组合泛化-Compositional Generalization）
type: concept
concept_type: algorithm|methodology|learning-paradigm|technical-idea

## 概述
[中文定义] [Source: 来源文章标题]

## 技术特点
[特点描述] [Source: 来源文章标题]

## 引用来源
- [文章标题](链接) - 该文章提出或涉及此概念"""
    else:
        format_requirements = """[论文格式要求]
## 基本信息
- **arXiv ID**: xxx
- **作者**: [从原文提取]

## 核心观点
[中文，一句话概括]

## 摘要
[中文，完整技术摘要]

## 问题定义
[中文，论文解决的核心问题]

## 方法
[中文，详细技术方法]

## 实验验证
[中文，实验设置、数据集、结果]

## 结论与展望
[中文，主要结论和未来方向]"""

    prompt = f"""你是知识库内容修正专家。

[待修正内容]
{content[:4000]}

[审核发现的问题]
{chr(10).join(f'- {issue}' for issue in issues[:10])}

[修改建议]
{chr(10).join(f'- {suggestion}' for suggestion in suggestions[:5])}

{format_requirements}

[修正要求]
1. 根据问题列表修正内容
2. 所有内容使用中文
3. 保持原有格式，只修正问题
4. 不要删除已有的正确内容
5. 论文内容不要添加 [Source: ...] 标记，只有实体和概念才需要

请输出修正后的完整内容（YAML + Markdown格式）：
"""

    print("    调用LLM修正内容...")
    response = call_llm(prompt, temperature=0.2)
    
    if not response:
        return None
    
    # 清理响应
    fixed = response
    if not fixed.startswith('---'):
        match = re.search(r'\n---\s*\n', fixed)
        if match:
            fixed = fixed[match.start():]
    
    fixed = re.sub(r'^```yaml\s*\n', '', fixed, flags=re.MULTILINE)
    fixed = re.sub(r'^```markdown\s*\n', '', fixed, flags=re.MULTILINE)
    fixed = re.sub(r'\n```\s*$', '', fixed)
    
    return fixed.strip()


def review_with_fix_cycle(page_path: Path, content_type: str = None, max_iterations: int = MAX_FIX_ITERATIONS) -> Tuple[ReviewResult, int]:
    """
    带修正循环的审核
    
    参数:
        page_path: 页面路径
        content_type: 内容类型
        max_iterations: 最大修正次数
    
    返回:
        (最终审核结果, 修正次数)
    """
    iteration = 0
    current_content = None
    
    while iteration <= max_iterations:
        # 读取内容
        if iteration == 0:
            with open(page_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        else:
            # 使用修正后的内容
            current_content = fixed_content
        
        # 临时写入文件用于审核
        temp_path = page_path.parent / f"{page_path.stem}_temp.md"
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(current_content)
        
        # 审核
        result = review_page(temp_path, content_type)
        
        # 删除临时文件
        if temp_path.exists():
            temp_path.unlink()
        
        if result.passed:
            # 审核通过，更新原文件
            if iteration > 0:
                with open(page_path, 'w', encoding='utf-8') as f:
                    f.write(current_content)
            print(f"    审核通过 (第{iteration + 1}轮)")
            return result, iteration
        
        # 审核不通过
        if iteration >= max_iterations:
            print(f"    达到最大修正次数 ({max_iterations})，审核仍未通过")
            return result, iteration
        
        print(f"    审核不通过 (第{iteration + 1}轮)，分数: {result.overall_score}/10")
        print(f"    问题: {len(result.issues)} 个")
        
        # 调用 LLM 修正
        fixed_content = fix_content_with_llm(
            current_content,
            result.issues,
            result.suggestions,
            content_type or "paper"
        )
        
        if not fixed_content:
            print("    LLM修正失败")
            return result, iteration
        
        iteration += 1
    
    return result, iteration


if __name__ == "__main__":
    exit(main())
