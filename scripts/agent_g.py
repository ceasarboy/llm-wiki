#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-G: Wiki 页面生成器 (Phase 3)
使用 LLM 从原始文档生成完整的 wiki 页面
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import re
import requests
import yaml

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_llm_config, get_paths_config, get_generation_config

# =============================================================================
# 配置
# =============================================================================

LLM_CONFIG = get_llm_config()
PATHS_CONFIG = get_paths_config()
GEN_CONFIG = get_generation_config()

RAW_DIR = Path(PATHS_CONFIG["raw_dir"])
OUTPUT_DIR = Path(PATHS_CONFIG["output_dir"])

# =============================================================================
# LLM 调用
# =============================================================================

def call_llm(prompt: str, system_prompt: str = None, temperature: float = None, max_tokens: int = None) -> str:
    """调用 LLM"""
    
    api_url = LLM_CONFIG.get("api_url", "http://127.0.0.1:28789/v1/chat/completions")
    api_key = LLM_CONFIG.get("api_key", "")
    model = LLM_CONFIG.get("model", "default")
    
    if temperature is None:
        temperature = LLM_CONFIG.get("temperature", 0.3)
    if max_tokens is None:
        max_tokens = LLM_CONFIG.get("max_tokens", 4000)
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    timeout = LLM_CONFIG.get("timeout", 300)
    print(f"  调用 LLM (timeout={timeout}s)...")
    
    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        response = requests.post(
            api_url,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            timeout=timeout
        )
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"]
        print(f"  LLM 返回 {len(result)} 字符")
        return result
    except requests.exceptions.Timeout:
        print(f"  LLM 调用超时 (>{timeout}s)")
        return None
    except Exception as e:
        print(f"  LLM 调用失败: {e}")
        return None


# =============================================================================
# 工具函数
# =============================================================================

def read_raw_doc(doc_path: Path) -> str:
    """读取原始文档"""
    with open(doc_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_arxiv_id(filename: str) -> Optional[str]:
    """提取 arXiv ID"""
    match = re.match(r'(\d{4}\.\d{4,5})', filename)
    return match.group(1) if match else None


def sanitize_yaml_string(s: str) -> str:
    """
    清理 YAML 字符串，处理特殊字符
    """
    if not s:
        return ""
    
    # 首先移除任何 Source ID（不应该出现在 Frontmatter 中）
    s = re.sub(r'\s*\[Source:[^\]]*\]', '', s)
    
    # 移除控制字符
    s = ''.join(char for char in s if ord(char) >= 32 or char in '\n\r\t')
    
    # 转义双引号
    s = s.replace('"', '\\"')
    
    # 移除可能导致 YAML 解析问题的字符
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    
    # 截断过长的字符串
    if len(s) > 200:
        s = s[:197] + "..."
    
    return s


def _clean_title(title: str) -> str:
    """清理标题中混入的作者信息（marker-pdf转换常见问题）"""
    # 模式1：标题后跟 "FirstName LastName, ..." 格式的作者列表
    # 检测连续两个大写首字母的单词（人名模式）
    author_start = re.search(
        r'\s+[A-Z][a-z]+\s+[A-Z][a-z]+(?:,|\s+(?:Member|Fellow|Student|and))',
        title
    )
    if author_start:
        title = title[:author_start.start()].strip()
    # 模式2：email
    email_match = re.search(r'\s+\S+@\S+', title)
    if email_match:
        title = title[:email_match.start()].strip()
    # 模式3：IEEE标识
    ieee_match = re.search(r'\s+Member,\s*IEEE|\s+Fellow,\s*IEEE', title)
    if ieee_match:
        title = title[:ieee_match.start()].strip()
    # 去掉末尾不完整的单词或标点
    if title and not title[-1].isalnum() and title[-1] not in ')]}':
        title = title.rstrip(' ,:;-')
    return title


def extract_title_from_meta(doc_path: Path) -> Optional[str]:
    if doc_path is None:
        return None
    meta_path = doc_path.parent / f"{doc_path.stem}_meta.json"
    if not meta_path.exists():
        return None
    try:
        import json
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        toc = meta.get("table_of_contents", [])
        if toc and toc[0].get("title"):
            title = toc[0]["title"].replace('\n', ' ').strip()
            if len(title) > 5:
                return title
    except Exception:
        pass
    return None


def extract_title(content: str, doc_path: Path = None) -> str:
    """提取标题 - 优先从 meta.json，再从正文提取"""
    meta_title = extract_title_from_meta(doc_path)
    if meta_title:
        return sanitize_yaml_string(_clean_title(meta_title))
    
    lines = content.split('\n')
    
    # 期刊名特征模式
    journal_patterns = [
        r'^Published in',
        r'^Transactions on',
        r'^Journal of',
        r'^Proceedings of',
        r'^Conference on',
        r'\(\d{2}/\d{4}\)$',
        r'arXiv:\d{4}\.\d{4,5}',
    ]
    
    section_headers = {
        'abstract', 'introduction', 'conclusion', 'conclusions',
        'summary', 'keywords', 'key words', 'references', 'bibliography',
        'acknowledgements', 'acknowledgments', 'related work',
        'background', 'preliminaries', 'discussion', 'appendix',
        'method', 'methods', 'methodology', 'approach',
        'experiments', 'experimental', 'evaluation', 'results',
        'implementation', 'architecture', 'overview',
    }
    
    def is_journal_title(title: str) -> bool:
        for pattern in journal_patterns:
            if re.search(pattern, title, re.IGNORECASE):
                return True
        if len(title) > 200:
            return True
        if title.strip().lower() in section_headers:
            return True
        if title.strip().lower().startswith(('abstract', 'introduction', 'conclusion', 'summary', 'keywords')):
            return True
        return False
    
    def extract_from_body(lines: List[str]) -> str:
        """从正文中提取论文标题"""
        # 查找 # 开头的标题
        for i, line in enumerate(lines[:50]):
            line = line.strip()
            if line.startswith('# '):
                title = line[2:].strip()
                if not is_journal_title(title) and len(title) > 5:
                    return title
            if line.startswith('## '):
                title = line[3:].strip()
                if not is_journal_title(title) and len(title) > 5:
                    return title
        
        # 查找多行标题（通常在第一页）
        # 模式: 短标题行后跟副标题
        title_lines = []
        in_title = False
        for i, line in enumerate(lines[:60]):
            stripped = line.strip()
            # 跳过 frontmatter
            if stripped == '---':
                if in_title:
                    break
                continue
            # 跳过空行
            if not stripped:
                if in_title and len(title_lines) > 0:
                    break
                continue
            # 跳过页码、邮箱、URL
            if stripped.isdigit() or '@' in stripped or stripped.startswith('http'):
                if in_title:
                    break
                continue
            # 跳过 Abstract, Keywords 等
            if stripped.lower().startswith(('abstract', 'keywords', 'introduction', 'summary')):
                break
            # 跳过 markdown 标题行（## 开头的是章节标题，不是论文标题）
            if stripped.startswith('#'):
                if in_title:
                    break
                continue
            # 跳过作者行（包含多个邮箱或机构）
            if '@' in stripped or 'university' in stripped.lower() or 'department' in stripped.lower():
                if in_title:
                    break
                continue
            
            # 可能是标题行
            if len(stripped) > 5 and len(stripped) < 150:
                if not is_journal_title(stripped):
                    # 跳过纯小写长句（通常是正文而非标题）
                    words = stripped.split()
                    if len(words) > 15 and stripped[0].islower():
                        if in_title:
                            break
                        continue
                    title_lines.append(stripped)
                    in_title = True
            elif in_title:
                break
        
        if title_lines:
            # 合并标题行
            title = ' '.join(title_lines)
            # 清理多余空格
            title = re.sub(r'\s+', ' ', title)
            return title
        
        return ""
    
    # 1. 先从正文 # 标题行提取（marker-pdf转换后的标题最干净）
    for line in lines[:50]:
        stripped = line.strip()
        if stripped.startswith('# ') and not stripped.startswith('## '):
            title = stripped[2:].strip()
            title = _clean_title(title)
            if not is_journal_title(title) and len(title) > 5:
                return sanitize_yaml_string(title)
        if stripped.startswith('## '):
            title = stripped[3:].strip()
            title = _clean_title(title)
            if not is_journal_title(title) and len(title) > 5:
                return sanitize_yaml_string(title)
    
    # 2. 尝试从 frontmatter 提取
    in_frontmatter = False
    for line in lines[:20]:
        if line.strip() == '---':
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter and line.strip().lower().startswith('title:'):
            title_match = re.match(r'^title:\s*"?(.+?)"?\s*$', line.strip(), re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip().strip('"').strip("'")
                title = _clean_title(title)
                if not is_journal_title(title) and len(title) > 5:
                    return sanitize_yaml_string(title)
    
    # 3. 从正文提取（粗粒度匹配）
    body_title = extract_from_body(lines)
    if body_title and len(body_title) > 5:
        return sanitize_yaml_string(body_title)
    
    return "Untitled"


def extract_abstract(content: str) -> str:
    """提取摘要"""
    patterns = [
        r'Abstract[:\s]*(.+?)(?=\n\n|\n#|Keywords|1\.|Introduction|I\.)',
        r'摘要[:\s]*(.+?)(?=\n\n|\n#|关键词|一、|1\.|引言)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            abstract = match.group(1).strip()
            abstract = re.sub(r'\s+', ' ', abstract)
            return abstract[:500]
    
    return ""


def extract_keywords(content: str) -> List[str]:
    """提取关键词"""
    keywords = []
    patterns = [
        r'Keywords?[:\s]*(.+?)(?=\n|\n\n|Abstract)',
        r'关键词[:\s]*(.+?)(?=\n|\n\n|摘要)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            kw_text = match.group(1)
            # 分割关键词
            kw_list = re.split(r'[,;，；]', kw_text)
            for kw in kw_list:
                kw = kw.strip()
                if kw and len(kw) > 1 and len(kw) < 50:
                    keywords.append(sanitize_yaml_string(kw))
            break
    
    return keywords[:8]  # 最多 8 个关键词


def chunk_content(content: str, chunk_size: int = 3000) -> List[str]:
    """将内容分块，用于 LLM 处理"""
    chunks = []
    start = 0
    
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        
        # 尽量在段落边界分割
        if end < len(content):
            last_newline = chunk.rfind('\n\n')
            if last_newline > chunk_size * 0.7:
                chunk = chunk[:last_newline]
                end = start + last_newline
        
        chunks.append(chunk)
        start = end
    
    return chunks


# =============================================================================
# 页面生成
# =============================================================================

def generate_all_in_one(doc_path: Path, content: str) -> Dict:
    """
    合并生成论文、实体、概念 - 增强版：先分析结构再生成内容
    返回: {"paper": (content, metadata), "entities": [...], "concepts": [...]}
    """
    arxiv_id = extract_arxiv_id(doc_path.name) or doc_path.stem
    
    title = extract_title(content, doc_path)
    abstract = extract_abstract(content)
    keywords = extract_keywords(content)
    today = datetime.now().strftime("%Y-%m-%d")
    
    source_title = title
    if len(source_title) > 80:
        source_title = arxiv_id if arxiv_id else title[:80]
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    numbered_content = ""
    for i, para in enumerate(paragraphs, 1):
        numbered_content += f"\n--- 段落 {i} ---\n{para[:2000]}\n"
    
    prompt = f"""你是 LLM-Wiki 的高级文档分析系统。你必须严格按照以下步骤执行任务。

【文档信息】
- 文件名: {doc_path.name}
- arXiv ID: {arxiv_id}
- 标题: {title}

【原始内容】
{numbered_content}

================================================================================
第一步：结构分析（必须先完成此步骤再进行生成）
================================================================================

请先分析这篇论文的完整结构，输出以下内容：

---STRUCTURE_START---
【论文类型】常规论文 / 综述文章 / 技术报告
【章节列表】
1. [章节名]：[核心内容概述，50字以内]
2. [章节名]：[核心内容概述，50字以内]
...
【核心推理链】
起点：[论文要解决什么问题]
→ 关键步骤1：[提出了什么方法/思路]
→ 关键步骤2：[方法如何实现]
→ 关键步骤3：[如何验证]
→ 终点：[得出什么结论]
【必须覆盖的内容】
- [列出原文中不可遗漏的核心技术点，至少5个]
- [列出原文中不可遗漏的关键实验结果，至少3个]
- [列出原文中不可遗漏的对比分析，如有]
---STRUCTURE_END---

================================================================================
第二步：内容生成（基于第一步的结构分析）
================================================================================

---PAPER_START---
## 基本信息
- **arXiv ID**: {arxiv_id}
- **PDF 链接**: https://arxiv.org/pdf/{arxiv_id}.pdf
- **原始文档链接**: https://arxiv.org/abs/{arxiv_id}
- **作者**: [从原文提取，格式：中文音译-英文原名]
- **机构**: [从原文提取，格式：中文名-英文名]

## 核心观点
[中文，一句话概括，不超过50字]

## 摘要
[中文，完整技术摘要，300-600字，必须覆盖论文的核心贡献和技术路线]

## 问题定义
[中文，论文解决的核心问题，100-300字，必须说明问题背景和挑战]

## 方法
[中文，详细技术方法，500-1200字。要求：
1. 按照原文的方法章节结构组织
2. 每个子方法/子模块都要介绍
3. 保留关键公式
4. 如果原文有"为什么选择该方法"的对比分析，必须包含]

## 实验验证
[中文，实验设置、数据集、结果。要求：
1. 列出所有实验任务和数据集
2. 保留关键数值结果
3. 如果原文有消融实验，必须列出具体发现
4. 如果原文有对比实验，必须包含对比结果]

## 结论与展望
[中文，主要结论和未来方向，100-300字]

## 关键术语
[用 • 开头列出关键技术术语，至少5个]
---PAPER_END---

---ENTITIES_START---
[提取论文中的实体，每个实体用 === 分隔]

【实体标题格式要求 - 必须严格遵守】
- 人名：必须翻译成中文，格式为"中文音译-英文原名"，如：凯文·史密斯-Kevin Smith
- 机构：必须翻译成中文，格式为"中文名-英文名"，如：麻省理工学院-MIT
- 数据集：格式为"中文名-英文名"

【去重要求 - 必须严格遵守】
- 同一人物/机构/数据集只提取一次，不要重复
- 如果同一实体有多种译名，选择最常见的一种

实体格式示例：
===
title: 凯文·史密斯-Kevin Smith
type: entity
entity_type: person
概述: 麻省理工学院脑与认知科学系研究员，本文第一作者。
关键信息: 
- 所属机构: 麻省理工学院
- 研究领域: 认知科学
- 论文贡献: 模型设计与实验
===
---ENTITIES_END---

---CONCEPTS_START---
[提取论文中的概念，每个概念用 === 分隔。必须至少提取3个概念！]

【去重要求 - 必须严格遵守】
- 同一概念只提取一次，不要重复
- 如果概念之间有包含关系，保留更具体的那个

概念格式示例：
===
title: 缩放点积注意力-Scaled Dot-Product Attention
type: concept
concept_type: technical-idea
概述: 通过查询与键的点积除以缩放因子后经softmax获得权重的注意力机制。
技术特点: 缩放因子1/√d_k防止点积过大导致梯度消失，可高效矩阵并行计算。
应用场景: Transformer架构的核心组件，广泛用于序列建模任务。
===
---CONCEPTS_END---

================================================================================
第三步：覆盖完整性自检
================================================================================

---REVIEW_START---
【覆盖检查】
1. 第一步中"必须覆盖的内容"是否全部覆盖？[逐项检查]
2. 方法章节是否包含所有子方法？[列出已覆盖的子方法]
3. 实验章节是否包含所有关键结果？[列出已覆盖的实验]
4. 概念数量：X个（必须≥3个）
5. 实体数量：X个

【评分】
- 内容覆盖完整性：X/10
- 方法细节完整性：X/10
- 实验结果完整性：X/10
- 概念提取质量：X/10
- 综合分：X/10

【是否通过】[通过/打回]
---REVIEW_END---

【硬性要求】
1. 所有内容必须使用中文
2. 必须先完成第一步结构分析，再进行第二步生成
3. 概念提取数量必须≥3个
4. 方法章节必须覆盖原文所有子方法
5. 实验章节必须包含具体数值结果
6. 如果原文有对比分析（如方法对比表），必须包含
7. 实体标题格式：中文-英文
8. 概念标题格式：中文-英文
9. 不要添加 [Source: ...] 标记
10. 必须输出所有标记（STRUCTURE_START/END, PAPER_START/END, ENTITIES_START/END, CONCEPTS_START/END, REVIEW_START/END）
11. 同一实体/概念不要重复提取

现在开始输出："""

    print("  调用 LLM 增强版生成论文+实体+概念...")
    llm_response = call_llm(prompt, temperature=0.3, max_tokens=10000)
    
    if not llm_response:
        return {"paper": (None, None), "entities": [], "concepts": []}
    
    # 解析各部分内容
    result = {
        "paper": (None, None),
        "entities": [],
        "concepts": [],
        "llm_review": "",
        "llm_score": 0,
        "llm_passed": False,
        "structure_analysis": ""
    }
    
    # 0. 提取结构分析
    structure_match = re.search(r'---STRUCTURE_START---\s*\n(.*?)\n---STRUCTURE_END---', llm_response, re.DOTALL)
    if structure_match:
        result["structure_analysis"] = structure_match.group(1).strip()
        print("  结构分析: 已提取")
    
    # 1. 提取论文内容
    paper_match = re.search(r'---PAPER_START---\s*\n(.*?)\n---PAPER_END---', llm_response, re.DOTALL)
    if not paper_match:
        print(f"  [WARN] 论文标记未匹配! 检查LLM输出格式...")
        start_idx = llm_response.find("---PAPER_START---")
        if start_idx >= 0:
            print(f"  PAPER_START存在于位置 {start_idx}, 但正则不匹配")
            after_start = llm_response[start_idx:start_idx+100]
            print(f"  PAPER_START后100字: {repr(after_start)}")
            end_idx = llm_response.find("---PAPER_END---", start_idx)
            if end_idx < 0:
                print(f"  PAPER_END未找到!")
        else:
            print(f"  PAPER_START完全不存在!")
    
    # 2. 提取实体内容（需要在构建论文之前，因为需要传递实体列表）
    related_entity_titles = []
    entities_match = re.search(r'---ENTITIES_START---\s*\n(.*?)\n---ENTITIES_END---', llm_response, re.DOTALL)
    if entities_match:
        entities_text = entities_match.group(1).strip()
        result["entities"] = _parse_entities(entities_text, doc_path, source_title, today)
        for _, e_meta in result["entities"]:
            if "title" in e_meta:
                related_entity_titles.append(e_meta["title"])
    
    # 3. 提取概念内容（需要在构建论文之前，因为需要传递概念列表）
    related_concepts = []
    concepts_match = re.search(r'---CONCEPTS_START---\s*\n(.*?)\n---CONCEPTS_END---', llm_response, re.DOTALL)
    if concepts_match:
        concepts_text = concepts_match.group(1).strip()
        concepts_list = _parse_concepts(concepts_text, doc_path, source_title, today)
        result["concepts"] = concepts_list
        for _, meta in concepts_list:
            if "title" in meta:
                related_concepts.append(meta["title"])
    
    # 4. 构建论文内容
    if paper_match:
        paper_content = paper_match.group(1).strip()
        paper_md, paper_meta = _build_paper_content(doc_path, paper_content, title, abstract, keywords, arxiv_id, source_title, today, related_concepts, related_entity_titles)
        result["paper"] = (paper_md, paper_meta)
    
    # 5. 提取审核内容
    review_match = re.search(r'---REVIEW_START---\s*\n(.*?)\n---REVIEW_END---', llm_response, re.DOTALL)
    if review_match:
        result["llm_review"] = review_match.group(1).strip()
        
        # 解析评分
        score_match = re.search(r'综合分[：:]\s*(\d+(?:\.\d+)?)', result["llm_review"])
        if score_match:
            result["llm_score"] = float(score_match.group(1))
        
        # 解析是否通过
        pass_match = re.search(r'【是否通过】[：:]?\s*(通过|打回)', result["llm_review"])
        if pass_match:
            result["llm_passed"] = pass_match.group(1) == '通过'
    
    print(f"  LLM 自评分数: {result['llm_score']}/10, 自评结果: {'通过' if result['llm_passed'] else '打回'}")
    print(f"  生成: 论文1篇, 实体{len(result['entities'])}个, 概念{len(result['concepts'])}个")
    
    return result


def _build_paper_content(doc_path, paper_content, title, abstract, keywords, arxiv_id, source_title, today, related_concepts=None, related_entities=None):
    """构建论文页面内容"""
    if related_concepts is None:
        related_concepts = []
    if related_entities is None:
        related_entities = []
    
    body_content = paper_content
    body_content = re.sub(r'\s*\[Source:[^\]]*\]', '', body_content)
    body_content = re.sub(r'\n{3,}', '\n\n', body_content)
    
    if not body_content.startswith('##'):
        body_content = "## 基本信息\n\n" + body_content
    
    body_content = re.sub(
        r'## 关键术语\n.*?(?=\n## |\Z)',
        '',
        body_content,
        flags=re.DOTALL
    )
    
    safe_title = sanitize_yaml_string(title)
    safe_abstract = sanitize_yaml_string(abstract[:150])
    
    concepts_yaml = json.dumps(related_concepts, ensure_ascii=False)
    
    frontmatter = f"""---
title: "{safe_title}"
type: paper
tags: {json.dumps(keywords, ensure_ascii=False)}
source: [[raw/papers/markdown/{doc_path.name}]]
created: "{today}"
updated: "{today}"
status: generated
arxiv_id: "{arxiv_id}"
authors: []
venue: ""
publish_date: ""
keywords: {json.dumps(keywords, ensure_ascii=False)}
confidence: medium
llm_enhanced: true
center_idea: "{safe_abstract}"
related_concepts: {concepts_yaml}
---

"""
    
    entities_section = ""
    if related_entities:
        entities_lines = ["\n## 提取的实体\n"]
        for entity_title in related_entities:
            safe_entity = entity_title.replace('/', '_').replace('\\', '_')[:50]
            entities_lines.append(f"- [[entities/{safe_entity}|{entity_title}]]")
        entities_section = "\n".join(entities_lines)
    
    concepts_section = ""
    if related_concepts:
        concepts_lines = ["\n## 涉及的概念\n"]
        for concept_title in related_concepts:
            safe_concept = concept_title.replace('/', '_').replace('\\', '_')[:50]
            concepts_lines.append(f"- [[concepts/{safe_concept}|{concept_title}]]")
        concepts_section = "\n".join(concepts_lines)
    
    full_content = frontmatter + body_content + entities_section + concepts_section
    
    metadata = {
        "filename": doc_path.name,
        "arxiv_id": arxiv_id,
        "title": title,
        "generated_at": datetime.now().isoformat(),
        "related_concepts": related_concepts,
        "related_entities": related_entities,
    }
    
    return full_content, metadata


def _parse_entities(entities_text, doc_path, source_title, today):
    """解析实体列表（含去重）"""
    entities = []
    seen_english = {}
    parts = re.split(r'===+', entities_text)
    
    for part in parts:
        part = part.strip()
        if not part or len(part) < 20:
            continue
        
        title_match = re.search(r'title:\s*(.+)', part)
        type_match = re.search(r'entity_type:\s*(\w+)', part)
        overview_match = re.search(r'概述:\s*(.+?)(?=\n关键信息:|\n---|\n===|$)', part, re.DOTALL)
        key_info_match = re.search(r'关键信息:\s*\n(.+?)$', part, re.DOTALL)
        
        if title_match:
            entity_title = title_match.group(1).strip()
            
            en_name = ""
            if "-" in entity_title:
                en_name = entity_title.split("-", 1)[-1].strip().lower()
            if not en_name:
                en_name = entity_title.lower()
            
            if en_name in seen_english:
                continue
            seen_english[en_name] = entity_title
            
            entity_type = type_match.group(1) if type_match else "unknown"
            overview = overview_match.group(1).strip() if overview_match else ""
            
            key_info = ""
            if key_info_match:
                key_info = key_info_match.group(1).strip()
            
            if not key_info or '[从原文提取' in key_info or '待补充' in key_info:
                key_info = f"- 实体类型: {entity_type}\n- 来源论文: {source_title}"
            
            entity_content = f"""---
title: "{entity_title}"
type: entity
entity_type: {entity_type}
tags: []
source: [[raw/papers/markdown/{doc_path.name}]]
created: "{today}"
updated: "{today}"
status: generated
confidence: medium
---

# {entity_title}

## 概述
{overview} [Source: {source_title}]

## 关键信息
{key_info} [Source: {source_title}]

## 引用来源
- [{source_title}](论文链接) - 该论文提及此实体。

## 相关论文
- [[papers/{doc_path.stem}_论文]]
"""
            entities.append((entity_content, {"title": entity_title, "type": "entity"}))
    
    return entities


def _parse_concepts(concepts_text, doc_path, source_title, today):
    """解析概念列表（含去重）"""
    concepts = []
    seen_english = {}
    parts = re.split(r'===+', concepts_text)
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        title_match = re.search(r'title:\s*(.+)', part)
        type_match = re.search(r'concept_type:\s*([\w-]+)', part)
        overview_match = re.search(r'概述:\s*(.+?)(?=\n技术特点:|\n应用场景:|\n---|\n===|$)', part, re.DOTALL)
        features_match = re.search(r'技术特点:\s*(.+?)(?=\n应用场景:|\n引用来源:|\n---|\n===|$)', part, re.DOTALL)
        scenario_match = re.search(r'应用场景:\s*(.+?)(?=\n---|\n===|\n引用来源|$)', part, re.DOTALL)
        
        if title_match:
            concept_title = title_match.group(1).strip()
            
            en_name = ""
            if "-" in concept_title:
                en_name = concept_title.split("-", 1)[-1].strip().lower()
            if not en_name:
                en_name = concept_title.lower()
            
            if en_name in seen_english:
                continue
            seen_english[en_name] = concept_title
            
            concept_type = type_match.group(1) if type_match else "methodology"
            overview = overview_match.group(1).strip() if overview_match else ""
            features = features_match.group(1).strip() if features_match else ""
            scenario = scenario_match.group(1).strip() if scenario_match else ""
            
            if not features or '待补充' in features or '[特点描述]' in features:
                features = f"概念类型: {concept_type}"
            
            concept_content = f"""---
title: "{concept_title}"
type: concept
concept_type: {concept_type}
tags: []
source: [[raw/papers/markdown/{doc_path.name}]]
created: "{today}"
updated: "{today}"
status: generated
confidence: medium
---

# {concept_title}

## 概述
{overview} [Source: {source_title}]

## 技术特点
{features} [Source: {source_title}]

## 应用场景
{scenario} [Source: {source_title}]

## 引用来源
- [{source_title}](论文链接) - 该论文提出或涉及此概念。

## 相关论文
- [[papers/{doc_path.stem}_论文]]
"""
            concepts.append((concept_content, {"title": concept_title, "type": "concept"}))
    
    return concepts


def generate_paper_page(doc_path: Path, content: str) -> Tuple[str, Dict]:
    """
    生成论文页（使用 LLM）- 增强版：先分析结构再生成内容
    """
    arxiv_id = extract_arxiv_id(doc_path.name) or doc_path.stem
    
    title = extract_title(content, doc_path)
    abstract = extract_abstract(content)
    keywords = extract_keywords(content)
    today = datetime.now().strftime("%Y-%m-%d")
    
    source_title = title
    if len(source_title) > 80:
        source_title = arxiv_id if arxiv_id else title[:80]
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    numbered_content = ""
    for i, para in enumerate(paragraphs, 1):
        numbered_content += f"\n--- 段落 {i} ---\n{para[:2000]}\n"
    
    prompt = f"""你是 LLM-Wiki 的高级文档分析系统。你必须严格按照以下步骤执行任务。

【文档信息】
- 文件名: {doc_path.name}
- arXiv ID: {arxiv_id}
- 标题: {title}

【原始内容】
{numbered_content}

================================================================================
第一步：结构分析（必须先完成此步骤再进行生成）
================================================================================

请先分析这篇论文的完整结构，输出以下内容：

---STRUCTURE_START---
【论文类型】常规论文 / 综述文章 / 技术报告
【章节列表】
1. [章节名]：[核心内容概述，50字以内]
...
【核心推理链】
起点：[论文要解决什么问题]
→ 关键步骤1：[提出了什么方法/思路]
→ 关键步骤2：[方法如何实现]
→ 关键步骤3：[如何验证]
→ 终点：[得出什么结论]
【必须覆盖的内容】
- [列出原文中不可遗漏的核心技术点，至少5个]
- [列出原文中不可遗漏的关键实验结果，至少3个]
---STRUCTURE_END---

================================================================================
第二步：内容生成（基于第一步的结构分析）
================================================================================

---PAPER_START---
## 基本信息
- **arXiv ID**: {arxiv_id}
- **PDF 链接**: https://arxiv.org/pdf/{arxiv_id}.pdf
- **原始文档链接**: https://arxiv.org/abs/{arxiv_id}
- **作者**: [从原文提取，格式：中文音译-英文原名]
- **机构**: [从原文提取，格式：中文名-英文名]

## 核心观点
[中文，一句话概括，不超过50字]

## 摘要
[中文，完整技术摘要，300-600字，必须覆盖论文的核心贡献和技术路线]

## 问题定义
[中文，论文解决的核心问题，100-300字，必须说明问题背景和挑战]

## 方法
[中文，详细技术方法，500-1200字。要求：
1. 按照原文的方法章节结构组织
2. 每个子方法/子模块都要介绍
3. 保留关键公式
4. 如果原文有"为什么选择该方法"的对比分析，必须包含]

## 实验验证
[中文，实验设置、数据集、结果。要求：
1. 列出所有实验任务和数据集
2. 保留关键数值结果
3. 如果原文有消融实验，必须列出具体发现
4. 如果原文有对比实验，必须包含对比结果]

## 结论与展望
[中文，主要结论和未来方向，100-300字]
---PAPER_END---

================================================================================
第三步：覆盖完整性自检
================================================================================

---REVIEW_START---
【覆盖检查】
1. 第一步中"必须覆盖的内容"是否全部覆盖？[逐项检查]
2. 方法章节是否包含所有子方法？[列出已覆盖的子方法]
3. 实验章节是否包含所有关键结果？[列出已覆盖的实验]

【评分】
- 内容覆盖完整性：X/10
- 方法细节完整性：X/10
- 实验结果完整性：X/10
- 综合分：X/10

【是否通过】[通过/打回]
---REVIEW_END---

【硬性要求】
1. 所有内容必须使用中文
2. 必须先完成第一步结构分析，再进行第二步生成
3. 方法章节必须覆盖原文所有子方法
4. 实验章节必须包含具体数值结果
5. 不要添加 [Source: ...] 标记
6. 必须输出所有标记（STRUCTURE_START/END, PAPER_START/END, REVIEW_START/END）

现在开始输出："""

    print("  调用 LLM 增强版生成论文...")
    llm_response = call_llm(prompt, temperature=0.3, max_tokens=10000)
    
    if not llm_response:
        return None, None
    
    generated_content = ""
    review_content = ""
    llm_score = 0
    llm_passed = False
    
    paper_match = re.search(r'---PAPER_START---\s*\n(.*?)\n---PAPER_END---', llm_response, re.DOTALL)
    if paper_match:
        generated_content = paper_match.group(1).strip()
    else:
        if '## 基本信息' in llm_response:
            start = llm_response.find('## 基本信息')
            end = llm_response.find('---REVIEW_START---')
            if end > start:
                generated_content = llm_response[start:end].strip()
            else:
                generated_content = llm_response[start:].strip()
    
    review_match = re.search(r'---REVIEW_START---\s*\n(.*?)\n---REVIEW_END---', llm_response, re.DOTALL)
    if review_match:
        review_content = review_match.group(1).strip()
    
    score_match = re.search(r'综合分[：:]\s*(\d+(?:\.\d+)?)', review_content)
    if score_match:
        llm_score = float(score_match.group(1))
    
    if '【是否通过】' in review_content:
        pass_section = re.search(r'【是否通过】[：:]?\s*(通过|打回)', review_content)
        if pass_section:
            llm_passed = pass_section.group(1) == '通过'
    
    print(f"  LLM 自评分数: {llm_score}/10, 自评结果: {'通过' if llm_passed else '打回'}")
    
    if not generated_content:
        print("  警告: 无法解析生成内容")
        return None, None
    
    body_content = generated_content
    body_content = re.sub(r'\s*\[Source:[^\]]*\]', '', body_content)
    body_content = re.sub(r'\n{3,}', '\n\n', body_content)
    body_content = re.sub(r'## 关键术语\n.*?(?=\n## |\Z)', '', body_content, flags=re.DOTALL)
    
    if not body_content.startswith('##'):
        body_content = "## 基本信息\n\n" + body_content
    
    safe_title = sanitize_yaml_string(title)
    safe_abstract = sanitize_yaml_string(abstract[:150])
    
    frontmatter = f"""---
title: "{safe_title}"
type: paper
tags: {json.dumps(keywords, ensure_ascii=False)}
source: [[raw/papers/markdown/{doc_path.name}]]
created: "{today}"
updated: "{today}"
status: generated
arxiv_id: "{arxiv_id}"
authors: []
venue: ""
publish_date: ""
keywords: {json.dumps(keywords, ensure_ascii=False)}
confidence: medium
llm_enhanced: true
center_idea: "{safe_abstract}"
llm_self_score: {llm_score}
llm_self_passed: {str(llm_passed).lower()}
---

"""
    
    full_content = frontmatter + body_content
    
    metadata = {
        "filename": doc_path.name,
        "arxiv_id": arxiv_id,
        "title": title,
        "generated_at": datetime.now().isoformat(),
        "llm_enhanced": True,
        "source_doc": str(doc_path),
        "llm_self_score": llm_score,
        "llm_self_passed": llm_passed,
        "llm_review": review_content[:500] if review_content else ""
    }
    
    return full_content, metadata


# =============================================================================
# 实体和概念生成
# =============================================================================

ENTITY_CONCEPT_BOUNDARY = """
[边界判断示例表 - 仔细阅读并遵循]
| 术语 | 正确分类 | entity_type/concept_type | 原因 |
|------|----------|--------------------------|------|
| MAML | concept | algorithm | 算法名称，Model-Agnostic Meta-Learning |
| Franka Emika Panda | entity | device | 具体机器人设备 |
| RLBench | entity | dataset | 数据集/benchmark |
| Stanford | entity | organization | 具体机构 |
| Meta-Learning | concept | learning-paradigm | 学习范式 |
| Chelsea Finn | entity | person | 具体人物 |
| Object-Level Adaptation | concept | methodology | 方法论名称 |
| PR2 Robot | entity | device | 具体设备型号 |
| BERT | concept | algorithm | 算法名称 |
| Google DeepMind | entity | organization | 具体机构 |
| Few-Shot Learning | concept | learning-paradigm | 学习范式 |
| 7-DoF Robot | entity | device | 具体设备描述 |

[判断规则 - 必须遵循]
1. 算法/模型/方法论名称 → concept (concept_type: algorithm/methodology)
2. 具体设备/硬件平台型号 → entity (entity_type: device)
3. 人名/机构名/地名 → entity (entity_type: person/organization/location)
4. 数据集/benchmark → entity (entity_type: dataset)
5. 论文本身 → concept (concept_type: paper)
6. 学习范式/技术思想 → concept (concept_type: learning-paradigm/technical-idea)
7. 不确定时，优先判断为 concept
"""

TAGS_RULES = """
[Tags 命名规范 - 必须遵循]
1. 全部小写
2. 使用连字符分隔单词（如 "meta-learning" 而非 "metaLearning"）
3. 最多 5 个 tags
4. 优先使用标准领域术语
5. 不要使用驼峰命名
"""


def generate_entities(doc_path: Path, content: str, max_entities: int = 10, paper_title: str = None) -> List[Tuple[str, Dict]]:
    """
    生成实体页面列表
    返回: [(entity_content, entity_metadata), ...]
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 提取论文标题用于 Source ID
    if not paper_title:
        paper_title = extract_title(content, doc_path)
    if not paper_title:
        paper_title = doc_path.stem
    
    # 清理标题，用于 Source ID
    source_title = paper_title
    if len(source_title) > 80:
        arxiv_id = extract_arxiv_id(doc_path.name)
        source_title = arxiv_id if arxiv_id else paper_title[:80]
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    numbered_content = ""
    for i, para in enumerate(paragraphs[:25], 1):
        numbered_content += f"\n--- 段落 {i} ---\n{para[:1000]}\n"
    
    prompt = f"""你是专业的命名实体提取专家。从学术论文中提取所有命名实体。

{ENTITY_CONCEPT_BOUNDARY}

{TAGS_RULES}

[Entity 定义 - 严格]
Entity = 具体、可命名的现实世界对象：
- Person: 作者、研究者（如 "Chelsea Finn", "Sumita Mishra"）
- Organization: 大学、实验室、公司（如 "Stanford", "Google DeepMind"）
- Location: 有上下文的地名（如校园位置、会议地点）
- Device: 硬件平台、机器人（如 "Franka Emika Panda", "PR2 Robot"）
- Dataset: benchmark数据集（如 "D5RL", "RLBench"）

[NOT Entity - 这些是 Concept]
- 算法/模型（如 "MAML" → concept）
- 方法论/框架（如 "meta-learning" → concept）
- 论文本身（→ summary type）
- 抽象思想/理论

[输出格式]
每个实体用 "---SEPARATOR---" 分隔：

```yaml
---
title: 实体名称
type: entity
entity_type: person|organization|location|device|dataset
aliases: [别名1, 别名2]
tags: [tag1, tag2]
source: [[raw/papers/markdown/{doc_path.name}]]
created: "{today}"
updated: "{today}"
status: generated
confidence: high|medium|low
---
# 实体名称

## 概述
1-2句话定义该实体及其与论文的相关性。 [Source: {source_title}]

## 关键信息
- **属性1**: 值（必须来自原文） [Source: {source_title}]
- **属性2**: 值 [Source: {source_title}]

## 引用来源
- [{source_title}](论文链接) - 简要说明该论文如何提及此实体。

## 相关论文
- [[papers/{doc_path.stem}_论文]]
```

[提取规则]
1. 提取所有可识别的实体，最多 {max_entities} 个
2. 人物实体：只提取论文中明确提到的作者和研究者
3. 机构实体：提取所有提到的机构/实验室/公司
4. 所有数据必须与原文完全匹配 - 不要编造
5. 如果不确定是否为实体，包含它并设置 confidence: low
6. 同一人物/机构/数据集只提取一次，不要重复

[关键要求]
1. **每个段落/句子后面必须添加 [Source: {source_title}]**
2. 这样后续融合其他资料时，可以清楚知道每句话来自哪个资料
3. 必须包含 ## 引用来源 部分，列出论文链接

[原文内容]
{numbered_content}

现在生成实体条目。只输出 YAML + Markdown，用 "---SEPARATOR---" 分隔。最多 {max_entities} 个实体。
**重要：每个段落/句子后面必须添加 [Source: {source_title}]**
"""
    
    print("  调用 LLM 生成实体...")
    llm_response = call_llm(prompt, temperature=0.3, max_tokens=8000)
    
    if not llm_response:
        return []
    
    entities = []
    seen_english = {}
    parts = re.split(r'---SEPARATOR---', llm_response)
    
    for part in parts:
        part = part.strip()
        if not part or part == '---':
            continue
        
        if not part.startswith('---'):
            match = re.search(r'\n---\s*\n', part)
            if match:
                part = part[match.start():]
        
        title_match = re.search(r'^title:\s*"?([^"\n]+)"?', part, re.MULTILINE)
        if title_match:
            entity_title = title_match.group(1).strip()
            
            en_name = ""
            if "-" in entity_title:
                en_name = entity_title.split("-", 1)[-1].strip().lower()
            if not en_name:
                en_name = entity_title.lower()
            
            if en_name in seen_english:
                continue
            seen_english[en_name] = entity_title
            
            # 确保每个段落都有 Source ID
            lines = part.split('\n')
            result_lines = []
            in_frontmatter = True
            in_code_block = False
            
            for i, line in enumerate(lines):
                result_lines.append(line)
                
                # 检测 frontmatter 结束
                if in_frontmatter and line.strip() == '---' and i > 0:
                    in_frontmatter = False
                    continue
                
                # 检测代码块
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    continue
                
                # 跳过 frontmatter 和代码块
                if in_frontmatter or in_code_block:
                    continue
                
                # 跳过标题行
                if line.strip().startswith('#'):
                    continue
                
                # 对于正文段落，检查是否已有 Source ID
                if line.strip() and not line.strip().startswith('-') and not line.strip().startswith('*'):
                    next_line = lines[i + 1] if i + 1 < len(lines) else ''
                    if not next_line.strip() or next_line.strip().startswith('#'):
                        if '[Source:' not in line:
                            result_lines.append(f' [Source: {source_title}]')
            
            part = '\n'.join(result_lines)
            entities.append((part, {"title": entity_title, "type": "entity"}))
    
    print(f"  生成实体: {len(entities)} 个")
    return entities[:max_entities]


def generate_concepts(doc_path: Path, content: str, max_concepts: int = 10, paper_title: str = None) -> List[Tuple[str, Dict]]:
    """
    生成概念页面列表
    返回: [(concept_content, concept_metadata), ...]
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 提取论文标题用于 Source ID
    if not paper_title:
        paper_title = extract_title(content, doc_path)
    if not paper_title:
        paper_title = doc_path.stem
    
    # 清理标题，用于 Source ID
    source_title = paper_title
    if len(source_title) > 80:
        arxiv_id = extract_arxiv_id(doc_path.name)
        source_title = arxiv_id if arxiv_id else paper_title[:80]
    
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    numbered_content = ""
    for i, para in enumerate(paragraphs[:25], 1):
        numbered_content += f"\n--- 段落 {i} ---\n{para[:1000]}\n"
    
    prompt = f"""你是专业的学术概念提取专家。从论文中提取关键抽象概念。

{ENTITY_CONCEPT_BOUNDARY}

{TAGS_RULES}

[Concept 定义 - 严格]
Concept = 抽象、可复用的想法/方法/理论/贡献：
- 论文本身（作为研究贡献）
- 算法/模型（如 "MAML", "Object-Level Adaptation"）
- 方法论概念（如 "object-level adaptation", "online adaptation"）
- 学习范式（如 "meta-learning", "few-shot learning"）
- 技术思想（如 "domain randomization", "policy conditioning"）
- 评估指标（如 "sample efficiency", "generalization"）

[NOT Concept - 这些是 Entity]
- 作者名、机构名 → entity type
- 硬件平台、机器人 → entity type

[输出格式]
每个概念用 "---SEPARATOR---" 分隔：

```yaml
---
title: 概念名称
type: concept
concept_type: paper|algorithm|methodology|learning-paradigm|technical-idea|evaluation-metric
tags: [tag1, tag2]
source: [[raw/papers/markdown/{doc_path.name}]]
created: "{today}"
updated: "{today}"
status: generated
confidence: 0.8
related_papers: []
llm_enhanced: true
---
# 概念名称

## 概述
一段精确的定义段落。 [Source: {source_title}]

## 技术特点
- **特点1**: 详细说明 [Source: {source_title}]
- **特点2**: 详细说明 [Source: {source_title}]

## 应用场景
- 场景1 [Source: {source_title}]
- 场景2 [Source: {source_title}]

## 引用来源
- [{source_title}](论文链接) - 简要说明该论文对本概念的贡献。

## 相关论文
- [[papers/论文ID_论文|论文标题]]
```

[关键要求]
1. **每个段落/句子后面必须添加 [Source: {source_title}]**
2. 这样后续融合其他资料时，可以清楚知道每句话来自哪个资料
3. 提取 3-{max_concepts} 个最重要的概念
4. 优先级：论文本身 > 核心算法 > 关键方法论 > 技术创新
5. 使用标准领域术语
6. 不要提取作者、机构或硬件（那些是 entity）
7. 同一概念只提取一次，不要重复

[原文内容]
{numbered_content}

现在生成概念条目。只输出 YAML + Markdown，用 "---SEPARATOR---" 分隔。最多 {max_concepts} 个概念。
**重要：每个段落/句子后面必须添加 [Source: {source_title}]**
"""
    
    print("  调用 LLM 生成概念...")
    llm_response = call_llm(prompt, temperature=0.3, max_tokens=8000)
    
    if not llm_response:
        return []
    
    concepts = []
    seen_english = {}
    parts = re.split(r'---SEPARATOR---', llm_response)
    
    for part in parts:
        part = part.strip()
        if not part or part == '---':
            continue
        
        if not part.startswith('---'):
            match = re.search(r'\n---\s*\n', part)
            if match:
                part = part[match.start():]
        
        title_match = re.search(r'^title:\s*"?([^"\n]+)"?', part, re.MULTILINE)
        if title_match:
            concept_title = title_match.group(1).strip()
            
            en_name = ""
            if "-" in concept_title:
                en_name = concept_title.split("-", 1)[-1].strip().lower()
            if not en_name:
                en_name = concept_title.lower()
            
            if en_name in seen_english:
                continue
            seen_english[en_name] = concept_title
            
            # 确保每个段落都有 Source ID
            lines = part.split('\n')
            result_lines = []
            in_frontmatter = True
            in_code_block = False
            
            for i, line in enumerate(lines):
                result_lines.append(line)
                
                # 检测 frontmatter 结束
                if in_frontmatter and line.strip() == '---' and i > 0:
                    in_frontmatter = False
                    continue
                
                # 检测代码块
                if line.strip().startswith('```'):
                    in_code_block = not in_code_block
                    continue
                
                # 跳过 frontmatter 和代码块
                if in_frontmatter or in_code_block:
                    continue
                
                # 跳过标题行
                if line.strip().startswith('#'):
                    continue
                
                # 对于正文段落，检查是否已有 Source ID
                # 如果是段落结束（空行或文件末尾），且上一行没有 Source ID，则添加
                if line.strip() and not line.strip().startswith('-') and not line.strip().startswith('*'):
                    # 检查下一行
                    next_line = lines[i + 1] if i + 1 < len(lines) else ''
                    if not next_line.strip() or next_line.strip().startswith('#'):
                        # 段落结束，检查是否有 Source ID
                        if '[Source:' not in line:
                            result_lines.append(f' [Source: {source_title}]')
            
            part = '\n'.join(result_lines)
            concepts.append((part, {"title": concept_title, "type": "concept"}))
    
    print(f"  生成概念: {len(concepts)} 个")
    return concepts[:max_concepts]


# =============================================================================
# 主函数
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Agent-G: Wiki 页面生成器")
    parser.add_argument("--file", type=str, help="处理单个文档")
    parser.add_argument("--batch", type=str, help="批量处理，传入 pending_docs.json 路径")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--types", type=str, default="paper,entity,concept", help="生成类型")
    parser.add_argument("--max-entities", type=int, default=10, help="最大实体数量")
    parser.add_argument("--max-concepts", type=int, default=10, help="最大概念数量")
    args = parser.parse_args()
    
    types_to_generate = [t.strip() for t in args.types.split(",")]
    
    print("=" * 60)
    print("Agent-G: Wiki 页面生成器 v4.0")
    print("=" * 60)
    
    if not LLM_CONFIG.get("api_key"):
        print("\n警告: LLM API Key 未配置")
        print("请设置环境变量 LLM_API_KEY 或修改 config.yaml")
        print("当前使用 Mock 模式（agent_g_mock.py）\n")
        import subprocess
        cmd = [sys.executable, str(Path(__file__).parent / "agent_g_mock.py")]
        if args.file:
            cmd.extend(["--file", args.file])
        if args.batch:
            cmd.extend(["--batch", args.batch])
        if args.output_dir:
            cmd.extend(["--output-dir", args.output_dir])
        subprocess.run(cmd)
        return 0
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if "paper" in types_to_generate:
        (output_dir / "papers").mkdir(exist_ok=True)
    if "entity" in types_to_generate:
        (output_dir / "entities").mkdir(exist_ok=True)
    if "concept" in types_to_generate:
        (output_dir / "concepts").mkdir(exist_ok=True)
    
    # 确定要处理的文档
    docs_to_process = []
    
    if args.file:
        doc_path = Path(args.file)
        if not doc_path.exists():
            doc_path = RAW_DIR / args.file
        docs_to_process.append(doc_path)
    elif args.batch:
        with open(args.batch, 'r', encoding='utf-8') as f:
            pending = json.load(f)
        for doc_info in pending.get("pending_docs", []):
            docs_to_process.append(Path(doc_info["path"]))
    else:
        print("错误: 请指定 --file 或 --batch")
        return 1
    
    print(f"\n待处理文档: {len(docs_to_process)} 个")
    print(f"生成类型: {types_to_generate}")
    print(f"LLM API: {LLM_CONFIG.get('api_url')}")
    print(f"Model: {LLM_CONFIG.get('model')}")
    
    results = []
    
    for i, doc_path in enumerate(docs_to_process, 1):
        print(f"\n[{i}/{len(docs_to_process)}] 处理: {doc_path.name}")
        
        try:
            content = read_raw_doc(doc_path)
            print(f"  文档大小: {len(content)} 字符")
            
            doc_result = {
                "source": doc_path.name,
                "paper": None,
                "entities": [],
                "concepts": [],
                "llm_score": 0,
                "llm_passed": False,
                "program_scores": {},
                "status": "success"
            }
            
            # 使用合并生成（论文+实体+概念+审核）
            result = generate_all_in_one(doc_path, content)
            
            doc_result["llm_score"] = result["llm_score"]
            doc_result["llm_passed"] = result["llm_passed"]
            
            # 保存论文
            if result["paper"][0]:
                paper_md, paper_meta = result["paper"]
                output_file = output_dir / "papers" / f"{doc_path.stem}_论文.md"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(paper_md)
                print(f"  已生成论文: {output_file.name}")
                doc_result["paper"] = str(output_file)
                
                # 程序审核论文
                from review import review_page
                review_result = review_page(output_file, content_type="paper")
                doc_result["program_scores"]["paper"] = review_result.overall_score
                print(f"  论文程序审核: {review_result.overall_score}/10 {'[PASS]' if review_result.passed else '[FAIL]'}")
            
            # 保存实体
            for idx, (entity_md, entity_meta) in enumerate(result["entities"], 1):
                entity_title = entity_meta.get("title", f"entity_{idx}")
                safe_name = re.sub(r'[^\w\-]', '_', entity_title)[:50]
                entity_file = output_dir / "entities" / f"{safe_name}.md"
                with open(entity_file, 'w', encoding='utf-8') as f:
                    f.write(entity_md)
                doc_result["entities"].append(str(entity_file))
                
                # 程序审核实体
                from review import review_page
                review_result = review_page(entity_file, content_type="entity")
                if "entities" not in doc_result["program_scores"]:
                    doc_result["program_scores"]["entities"] = []
                doc_result["program_scores"]["entities"].append({
                    "title": entity_title,
                    "score": review_result.overall_score,
                    "passed": review_result.passed
                })
            print(f"  已生成实体: {len(result['entities'])} 个")
            
            # 保存概念
            for idx, (concept_md, concept_meta) in enumerate(result["concepts"], 1):
                concept_title = concept_meta.get("title", f"concept_{idx}")
                safe_name = re.sub(r'[^\w\-]', '_', concept_title)[:50]
                concept_file = output_dir / "concepts" / f"{safe_name}.md"
                with open(concept_file, 'w', encoding='utf-8') as f:
                    f.write(concept_md)
                doc_result["concepts"].append(str(concept_file))
                
                # 程序审核概念
                from review import review_page
                review_result = review_page(concept_file, content_type="concept")
                if "concepts" not in doc_result["program_scores"]:
                    doc_result["program_scores"]["concepts"] = []
                doc_result["program_scores"]["concepts"].append({
                    "title": concept_title,
                    "score": review_result.overall_score,
                    "passed": review_result.passed
                })
            print(f"  已生成概念: {len(result['concepts'])} 个")
            
            # 汇总审核结果
            all_passed = True
            if doc_result["program_scores"].get("paper", 0) < 7.5:
                all_passed = False
            for e in doc_result["program_scores"].get("entities", []):
                if not e["passed"]:
                    all_passed = False
            for c in doc_result["program_scores"].get("concepts", []):
                if not c["passed"]:
                    all_passed = False
            
            if not all_passed:
                doc_result["status"] = "needs_review"
            
            results.append(doc_result)
            
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "source": doc_path.name,
                "status": "error",
                "error": str(e)
            })
    
    result_file = output_dir / "agent_g_result.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "count": len(results),
            "types": types_to_generate,
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    success_count = len([r for r in results if r.get("status") == "success"])
    error_count = len([r for r in results if r.get("status") == "error"])
    total_entities = sum(len(r.get("entities", [])) for r in results)
    total_concepts = sum(len(r.get("concepts", [])) for r in results)
    
    print(f"\n{'=' * 60}")
    print(f"生成完成: {success_count} 成功, {error_count} 失败")
    print(f"论文: {len([r for r in results if r.get('paper')])} 篇")
    print(f"实体: {total_entities} 个")
    print(f"概念: {total_concepts} 个")
    print(f"结果保存: {result_file}")
    print(f"{'=' * 60}")
    
    return 0


if __name__ == "__main__":
    exit(main())
