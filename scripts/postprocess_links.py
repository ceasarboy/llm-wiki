#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后处理脚本：将论文中的关键术语分类并转换为wiki链接格式
功能：
  1. 解析论文中的"关键术语"部分
  2. 根据规则自动分类为实体或概念
  3. 检查对应的wiki文件是否存在，不存在则创建
  4. 将列表项转换为wiki链接格式
"""

import os
import sys
import re
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_paths_config

PATHS = get_paths_config()
WIKI_DIR = Path(PATHS["wiki_dir"])
ENTITIES_DIR = WIKI_DIR / "entities"
CONCEPTS_DIR = WIKI_DIR / "concepts"


# 实体关键词（机构、公司、人物、具体产品）
ENTITY_KEYWORDS = [
    'university', 'institute', 'laboratory', 'lab', 'college', 'school',
    'company', 'corporation', 'corp', 'inc', 'ltd', 'llc',
    'dataset', 'benchmark', 'database',
    'framework', 'platform', 'toolkit', 'library',
    '大学', '研究院', '研究所', '实验室', '学院',
    '公司', '集团', '企业',
    '数据集', '基准', '平台', '框架',
]

# 概念关键词（方法、理论、技术）
CONCEPT_KEYWORDS = [
    'learning', 'training', 'inference', 'optimization', 'algorithm',
    'model', 'network', 'transformer', 'attention', 'embedding',
    'reinforcement', 'supervised', 'unsupervised', 'semi-supervised',
    'generation', 'retrieval', 'encoding', 'decoding',
    'fine-tuning', 'finetuning', 'pre-training', 'pretraining',
    'simulation', 'differentiable', 'neural', 'deep',
    '学习', '训练', '推理', '优化', '算法',
    '模型', '网络', '注意力', '嵌入',
    '强化', '监督', '无监督', '生成', '检索',
    '微调', '预训练', '仿真', '神经', '深度',
]


def slugify(text: str) -> str:
    """将文本转换为文件名友好的格式"""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', '', text)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.lower()


def extract_key_terms(content: str) -> List[str]:
    """从内容中提取关键术语（支持新旧两种格式）"""
    items = []
    
    # 新格式：## 关键术语
    in_section = False
    lines = content.split('\n')
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith('## 关键术语'):
            in_section = True
            continue
        
        if in_section:
            if stripped.startswith('## '):
                break
            if stripped.startswith('- ') or stripped.startswith('• '):
                item = stripped[2:].strip()
                if item and not item.startswith('[[') and not item.startswith('格式') and not item.startswith('示例'):
                    items.append(item)
            elif stripped.startswith('- 格式') or stripped.startswith('- 示例'):
                continue
    
    if items:
        return items
    
    # 旧格式：## 提取的实体 + ## 涉及的概念
    in_entities = False
    in_concepts = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith('## 提取的实体'):
            in_entities = True
            in_concepts = False
            continue
        
        if stripped.startswith('## 涉及的概念'):
            in_entities = False
            in_concepts = True
            continue
        
        if stripped.startswith('## '):
            in_entities = False
            in_concepts = False
            continue
        
        if in_entities or in_concepts:
            if stripped.startswith('- ') or stripped.startswith('• '):
                item = stripped[2:].strip()
                if item and not item.startswith('[['):
                    items.append(item)
    
    return items


def parse_item(item: str) -> Tuple[str, str]:
    """解析列表项，返回(名称, 显示文本)"""
    item = item.strip()
    
    if '（' in item and '）' in item:
        match = re.match(r'(.+?)（(.+?)）', item)
        if match:
            name = match.group(1).strip()
            eng = match.group(2).strip()
            display = f"{name}（{eng}）"
            return name, display
    
    if '(' in item and ')' in item:
        match = re.match(r'(.+?)\s*\((.+?)\)', item)
        if match:
            name = match.group(1).strip()
            eng = match.group(2).strip()
            display = f"{name}（{eng}）"
            return name, display
    
    return item, item


def classify_term(name: str, display: str) -> str:
    """根据规则分类术语为 entity 或 concept"""
    text_lower = (name + ' ' + display).lower()
    
    for kw in ENTITY_KEYWORDS:
        if kw.lower() in text_lower:
            return 'entity'
    
    for kw in CONCEPT_KEYWORDS:
        if kw.lower() in text_lower:
            return 'concept'
    
    words = name.split()
    if len(words) >= 2:
        if all(w[0].isupper() for w in words if w):
            return 'entity'
    
    if re.match(r'^[A-Z][a-z]+\s+[A-Z]', name):
        return 'entity'
    
    if re.match(r'^[A-Z]{2,}$', name):
        return 'entity'
    
    if re.search(r'[一-龥]', name):
        if any(kw in name for kw in ['方法', '算法', '模型', '技术', '学习', '训练']):
            return 'concept'
        if any(kw in name for kw in ['大学', '公司', '研究院', '研究所', '实验室']):
            return 'entity'
    
    return 'concept'


def check_file_exists(name: str, term_type: str) -> Optional[Path]:
    """检查文件是否存在（支持LLM生成的entity_N_标题.md格式）"""
    slug = slugify(name)
    
    if term_type == 'entity':
        dir_path = ENTITIES_DIR
    else:
        dir_path = CONCEPTS_DIR
    
    candidates = [
        dir_path / f"{slug}.md",
        dir_path / f"{name}.md",
    ]
    
    for path in candidates:
        if path.exists():
            return path
    
    en_name = ""
    if "-" in name:
        en_name = name.split("-", 1)[-1].strip().lower()
    
    if en_name:
        for f in dir_path.glob("*.md"):
            fname = f.stem.lower()
            if en_name in fname or en_name.replace(" ", "-") in fname:
                return f
    
    return None


def create_entity_file(name: str, display: str) -> Path:
    """创建实体文件"""
    ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
    
    slug = slugify(name)
    file_path = ENTITIES_DIR / f"{slug}.md"
    
    if file_path.exists():
        return file_path
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    content = f"""---
title: "{display}"
type: entity
tags: []
source: []
created: "{today}"
updated: "{today}"
status: generated
entity_type: ""
center_idea: ""
key_terms: []
related_fields: []
---

# {display}

## 概述
{display} 是从论文中提取的实体。

## 详细描述
[待补充]

## 相关链接
- 相关论文：[待补充]
"""
    
    file_path.write_text(content, encoding='utf-8')
    print(f"  创建实体: {file_path.name}")
    return file_path


def create_concept_file(name: str, display: str) -> Path:
    """创建概念文件"""
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    slug = slugify(name)
    file_path = CONCEPTS_DIR / f"{slug}.md"
    
    if file_path.exists():
        return file_path
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    content = f"""---
title: "{display}"
type: concept
tags: []
source: []
created: "{today}"
updated: "{today}"
status: generated
definition: ""
related_concepts: []
related_entities: []
---

# {display}

## 定义
{display} 是从论文中提取的概念。

## 核心要点
- [待补充]

## 原理/机制
[待补充]

## 应用场景
[待补充]

## 相关链接
- 相关论文：[待补充]
"""
    
    file_path.write_text(content, encoding='utf-8')
    print(f"  创建概念: {file_path.name}")
    return file_path


def process_term(item: str) -> Tuple[str, str, str]:
    """处理单个术语，返回(类型, slug, 显示文本)"""
    name, display = parse_item(item)
    term_type = classify_term(name, display)
    
    existing = check_file_exists(name, term_type)
    
    if existing:
        slug = existing.stem
    else:
        if term_type == 'entity':
            create_entity_file(name, display)
        else:
            create_concept_file(name, display)
        slug = slugify(name)
    
    return term_type, slug, display


def process_paper(paper_path: Path) -> bool:
    """处理单个论文文件"""
    print(f"\n处理: {paper_path.name}")
    
    content = paper_path.read_text(encoding='utf-8')
    
    if '[[entities/' in content or '[[concepts/' in content:
        print("  已是链接格式，跳过")
        return False
    
    key_terms = extract_key_terms(content)
    
    if not key_terms:
        print("  未找到关键术语")
        return False
    
    print(f"  关键术语: {len(key_terms)}")
    
    entities = []
    concepts = []
    
    for term in key_terms:
        term_type, slug, display = process_term(term)
        if term_type == 'entity':
            entities.append(f"- [[entities/{slug}|{display}]]")
        else:
            concepts.append(f"- [[concepts/{slug}|{display}]]")
    
    print(f"  分类结果: 实体 {len(entities)}, 概念 {len(concepts)}")
    
    lines = content.split('\n')
    new_lines = []
    skip_until_next_section = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if stripped.startswith('## 关键术语'):
            skip_until_next_section = True
            
            if entities:
                new_lines.append('## 提取的实体')
                for e in entities:
                    new_lines.append(e)
                new_lines.append('')
            
            if concepts:
                new_lines.append('## 涉及的概念')
                for c in concepts:
                    new_lines.append(c)
                new_lines.append('')
            continue
        
        if stripped.startswith('## ') and skip_until_next_section:
            skip_until_next_section = False
            new_lines.append(line)
            continue
        
        if skip_until_next_section:
            continue
        
        if stripped.startswith('## 提取的实体') or stripped.startswith('## 涉及的概念'):
            skip_until_next_section = True
            continue
        
        new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    paper_path.write_text(new_content, encoding='utf-8')
    print(f"  已更新: {paper_path.name}")
    
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="后处理：分类关键术语并转换为wiki链接")
    parser.add_argument("--file", type=str, help="处理单个文件")
    parser.add_argument("--dir", type=str, help="处理目录下所有论文")
    args = parser.parse_args()
    
    print("=" * 60)
    print("后处理：关键术语分类与链接转换")
    print("=" * 60)
    
    if args.file:
        paper_path = Path(args.file)
        if paper_path.exists():
            process_paper(paper_path)
    elif args.dir:
        papers_dir = Path(args.dir)
        for paper in papers_dir.glob("*.md"):
            process_paper(paper)
    else:
        for paper in (WIKI_DIR / "papers").glob("*.md"):
            process_paper(paper)
    
    print("\n" + "=" * 60)
    print("处理完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
