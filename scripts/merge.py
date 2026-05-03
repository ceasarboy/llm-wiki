#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实体/概念融合模块
功能：
  1. 识别新生成的实体/概念是否与知识库中已有的重复
  2. 根据融合规则合并内容
"""

import re
import sys
from pathlib import Path


def atomic_write(path: Path, content: str, encoding: str = 'utf-8'):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(content, encoding=encoding)
    tmp.replace(path)
from typing import Tuple, Optional, Dict, List
from difflib import SequenceMatcher
from datetime import datetime

from config_loader import get_paths_config

sys.path.insert(0, str(Path(__file__).parent))
from agent_g import call_llm

PATHS = get_paths_config()
WIKI_DIR = Path(PATHS["wiki_dir"])
ENTITIES_DIR = WIKI_DIR / "entities"
CONCEPTS_DIR = WIKI_DIR / "concepts"
RAW_DIR = Path(PATHS["raw_dir"])
MERGE_LOG_FILE = WIKI_DIR / "merge_decisions.log"


def extract_english_name(title: str) -> str:
    """从标题中提取英文名称用于匹配"""
    if "-" in title:
        en = title.split("-", 1)[-1].strip()
    elif "（" in title and "）" in title:
        m = re.search(r'（(.+?)）', title)
        en = m.group(1).strip() if m else title
    elif "(" in title and ")" in title:
        m = re.search(r'\((.+?)\)', title)
        en = m.group(1).strip() if m else title
    else:
        en = title
    return en.lower().strip()


def extract_chinese_name(title: str) -> str:
    """从标题中提取中文名称"""
    if "-" in title:
        cn = title.split("-", 1)[0].strip()
    elif "（" in title:
        cn = title.split("（")[0].strip()
    elif "(" in title:
        cn = title.split("(")[0].strip()
    else:
        cn = title
    return cn.strip()


def load_existing_pages(content_type: str) -> Dict[str, Path]:
    """
    加载知识库中已有的实体/概念页面
    返回: {英文名小写: 文件路径}
    """
    if content_type == "entity":
        target_dir = ENTITIES_DIR
    else:
        target_dir = CONCEPTS_DIR
    
    if not target_dir.exists():
        return {}
    
    pages = {}
    for f in target_dir.glob("*.md"):
        try:
            content = f.read_text(encoding='utf-8')
        except Exception:
            continue
        
        title_match = re.search(r'^title:\s*"([^"]+)"', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)
            en_name = extract_english_name(title)
            if en_name:
                pages[en_name] = f
    
    return pages


def find_matching_page(title: str, content_type: str) -> Optional[Tuple[Path, str]]:
    """
    查找知识库中与给定标题匹配的已有页面
    返回: (文件路径, 匹配方式) 或 None
    """
    en_name = extract_english_name(title)
    cn_name = extract_chinese_name(title)
    
    if content_type == "entity":
        target_dir = ENTITIES_DIR
    else:
        target_dir = CONCEPTS_DIR
    
    if not target_dir.exists():
        return None
    
    for f in target_dir.glob("*.md"):
        try:
            content = f.read_text(encoding='utf-8')
        except Exception:
            continue
        
        title_match = re.search(r'^title:\s*"([^"]+)"', content, re.MULTILINE)
        if not title_match:
            continue
        
        existing_title = title_match.group(1)
        existing_en = extract_english_name(existing_title)
        existing_cn = extract_chinese_name(existing_title)
        
        if en_name and existing_en and en_name == existing_en:
            return (f, "english_exact")
        
        if cn_name and existing_cn and cn_name == existing_cn:
            return (f, "chinese_exact")
        
        if en_name and existing_en:
            en_clean = re.sub(r'[^a-z0-9]', '', en_name)
            existing_en_clean = re.sub(r'[^a-z0-9]', '', existing_en)
            if en_clean and existing_en_clean and en_clean == existing_en_clean:
                return (f, "english_normalized")
        
        if en_name and existing_en and len(en_name) > 4 and len(existing_en) > 4:
            ratio = SequenceMatcher(None, en_name, existing_en).ratio()
            if ratio >= 0.85:
                return (f, "fuzzy")
    
    return None


def extract_source_paper(content: str) -> Optional[str]:
    """从页面内容中提取来源论文"""
    source_match = re.search(r'source:\s*\[\[raw/papers/markdown/([^\]]+)\]\]', content)
    if source_match:
        return source_match.group(1).replace('.md', '')
    return None


def extract_related_papers(content: str) -> List[str]:
    """从页面内容中提取相关论文列表"""
    papers = []
    for m in re.finditer(r'\[\[papers/([^\]|]+)', content):
        papers.append(m.group(1))
    return papers


def add_paper_to_related(content: str, paper_stem: str) -> str:
    """在相关论文部分追加一篇论文"""
    related_papers = extract_related_papers(content)
    if paper_stem in related_papers:
        return content
    
    related_section_match = re.search(r'(## 相关论文\n)', content)
    if related_section_match:
        insert_pos = related_section_match.end()
        content = content[:insert_pos] + f"- [[papers/{paper_stem}]]\n" + content[insert_pos:]
    else:
        content = content.rstrip() + f"\n\n## 相关论文\n- [[papers/{paper_stem}]]\n"
    
    return content


def add_source_to_content(content: str, source_title: str) -> str:
    """在引用来源部分追加一个来源"""
    if f"[Source: {source_title}]" in content:
        return content
    
    source_section_match = re.search(r'(## 引用来源\n)', content)
    if source_section_match:
        insert_pos = source_section_match.end()
        existing_sources = re.findall(r'- \[([^\]]+)\]\(论文链接\)', content)
        if existing_sources:
            last_source_pos = content.rfind('(论文链接)')
            if last_source_pos != -1:
                end_of_line = content.find('\n', last_source_pos)
                if end_of_line != -1:
                    content = content[:end_of_line+1] + f"- [{source_title}](论文链接) - 该论文提及此实体。\n" + content[end_of_line+1:]
        else:
            content = content[:insert_pos] + f"- [{source_title}](论文链接) - 该论文提及此实体。\n" + content[insert_pos:]
    
    return content


def resolve_raw_doc_path(source_paper_stem: str) -> Optional[Path]:
    stem = source_paper_stem.replace("_论文", "")
    
    candidates = [
        RAW_DIR / f"{stem}.md",
        RAW_DIR / f"{stem}_论文.md",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    for f in RAW_DIR.glob("*.md"):
        if f.stem.startswith(stem):
            return f
    
    return None


def extract_context_from_raw(entity_name: str, raw_doc_path: Path, max_chars: int = 1500) -> str:
    if not raw_doc_path.exists():
        return ""
    
    try:
        content = raw_doc_path.read_text(encoding='utf-8')
    except Exception:
        return ""
    
    en_name = extract_english_name(entity_name)
    cn_name = extract_chinese_name(entity_name)
    
    search_terms = []
    if en_name and len(en_name) > 1:
        search_terms.append(en_name)
    if cn_name and len(cn_name) > 1:
        search_terms.append(cn_name)
    
    if not search_terms:
        return ""
    
    contexts = []
    total_chars = 0
    window = 200
    
    for term in search_terms:
        start = 0
        while total_chars < max_chars:
            pos = content.find(term, start)
            if pos == -1:
                break
            
            ctx_start = max(0, pos - window)
            ctx_end = min(len(content), pos + len(term) + window)
            snippet = content[ctx_start:ctx_end].strip()
            
            if snippet and snippet not in contexts:
                contexts.append(snippet)
                total_chars += len(snippet)
            
            start = pos + len(term)
    
    if not contexts:
        return ""
    
    return "\n...\n".join(contexts)


def compute_content_similarity(content1: str, content2: str) -> float:
    """计算两个内容的相似度"""
    text1 = re.sub(r'---[\s\S]*?---', '', content1, count=1)
    text2 = re.sub(r'---[\s\S]*?---', '', content2, count=1)
    text1 = re.sub(r'\[Source:[^\]]*\]', '', text1)
    text2 = re.sub(r'\[Source:[^\]]*\]', '', text2)
    text1 = re.sub(r'\s+', ' ', text1).strip()
    text2 = re.sub(r'\s+', ' ', text2).strip()
    
    if not text1 or not text2:
        return 0.0
    
    return SequenceMatcher(None, text1, text2).ratio()


def llm_judge_merge(
    title_new: str,
    content_new: str,
    title_existing: str,
    content_existing: str,
    content_type: str,
    match_method: str,
    context_new: str,
    context_existing: str,
) -> dict:
    type_label = "实体" if content_type == "entity" else "概念"
    
    prompt = f"""你是一个知识库融合判断专家。请判断以下两个{type_label}是否为同一个{type_label}，应该融合还是分开保存。

## 匹配信息
- 匹配方式: {match_method}
- 新{type_label}标题: {title_new}
- 已有{type_label}标题: {title_existing}

## 新{type_label}在来源论文中的上下文
{context_new if context_new else "（未找到上下文）"}

## 已有{type_label}在来源论文中的上下文
{context_existing if context_existing else "（未找到上下文）"}

## 新{type_label}的完整内容
{content_new[:2000]}

## 已有{type_label}的完整内容
{content_existing[:2000]}

## 判断要求
1. 如果两个{type_label}指的是同一个事物（即使中文译名不同、描述角度不同），则应该融合
2. 如果两个{type_label}虽然名称相似但指代不同事物，则不应融合
3. 融合时，保留已有页面中更完整的信息，补充新{type_label}中的独特信息
4. 融合后的标题应选择更准确、更常见的译名

## 输出格式（严格遵守）
如果应该融合:
MERGE: yes
TITLE: 融合后的标题
REASON: 简要说明为什么是同一个{type_label}
CONTENT:
（融合后的完整内容，包括 frontmatter 和正文，保留两个来源的信息）

如果不应融合:
MERGE: no
REASON: 简要说明为什么不是同一个{type_label}"""

    result = call_llm(prompt, temperature=0.1, max_tokens=4000)
    
    if not result:
        return {
            "should_merge": True,
            "reason": "LLM调用失败，默认融合",
            "merged_content": None,
        }
    
    should_merge = "MERGE: yes" in result.lower() or "MERGE:yes" in result.lower().replace(" ", "")
    
    if should_merge:
        merged_content = None
        content_match = re.search(r'CONTENT:\s*\n([\s\S]+)', result)
        if content_match:
            merged_content = content_match.group(1).strip()
        
        title_match = re.search(r'TITLE:\s*(.+)', result)
        new_title = title_match.group(1).strip() if title_match else title_existing
        
        if merged_content and new_title != title_existing:
            merged_content = re.sub(
                r'^title:\s*"[^"]*"',
                f'title: "{new_title}"',
                merged_content,
                count=1,
                flags=re.MULTILINE
            )
        
        reason_match = re.search(r'REASON:\s*(.+?)(?:\n|TITLE:|CONTENT:)', result, re.DOTALL)
        reason = reason_match.group(1).strip() if reason_match else "LLM判断为同一实体"
        
        return {
            "should_merge": True,
            "reason": reason,
            "merged_content": merged_content,
        }
    else:
        reason_match = re.search(r'REASON:\s*(.+?)(?:\n|$)', result, re.DOTALL)
        reason = reason_match.group(1).strip() if reason_match else "LLM判断为不同实体"
        
        return {
            "should_merge": False,
            "reason": reason,
            "merged_content": None,
        }


def process_merge(
    title: str,
    new_content: str,
    content_type: str,
    source_paper_stem: str = "",
    source_title: str = "",
    doc_path: Optional[Path] = None,
) -> Tuple[bool, Optional[str], Optional[Path]]:
    """
    处理实体/概念融合
    
    参数:
        title: 新生成的实体/概念标题
        new_content: 新生成的完整内容（含frontmatter）
        content_type: "entity" 或 "concept"
        source_paper_stem: 来源论文的文件名stem（如 "2604.27415"）
        source_title: 来源论文的标题（用于Source ID）
        doc_path: 原始论文路径（用于提取上下文）
    
    返回:
        (should_save, merged_content, existing_path)
        - should_save: 是否需要保存
        - merged_content: 融合后的内容（None表示不需要保存）
        - existing_path: 已有文件的路径（None表示新建）
    """
    match_result = find_matching_page(title, content_type)
    
    if match_result is None:
        return (True, new_content, None)
    
    existing_path, match_method = match_result
    print(f"    [Merge] 发现匹配: {title} <-> {existing_path.name} (方式: {match_method})")
    
    existing_content = existing_path.read_text(encoding='utf-8')
    
    similarity = compute_content_similarity(existing_content, new_content)
    print(f"    [Merge] 内容相似度: {similarity:.2f}")
    
    if similarity >= 0.9:
        print(f"    [Merge] 内容高度相似，仅追加相关论文")
        merged = existing_content
        if source_paper_stem:
            merged = add_paper_to_related(merged, source_paper_stem)
        existing_path.write_text(merged, encoding='utf-8')
        return (False, None, existing_path)
    
    existing_title_match = re.search(r'^title:\s*"([^"]+)"', existing_content, re.MULTILINE)
    existing_title = existing_title_match.group(1) if existing_title_match else existing_path.stem
    
    context_new = ""
    context_existing = ""
    if doc_path and doc_path.exists():
        context_new = extract_context_from_raw(title, doc_path)
    
    existing_source = extract_source_paper(existing_content)
    if existing_source:
        existing_raw_path = resolve_raw_doc_path(existing_source)
        if existing_raw_path:
            context_existing = extract_context_from_raw(existing_title, existing_raw_path)
    
    print(f"    [Merge] 调用 LLM 判断是否融合...")
    judgment = llm_judge_merge(
        title_new=title,
        content_new=new_content,
        title_existing=existing_title,
        content_existing=existing_content,
        content_type=content_type,
        match_method=match_method,
        context_new=context_new,
        context_existing=context_existing,
    )
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if judgment["should_merge"]:
        print(f"    [Merge] LLM判断: 应融合 - {judgment['reason']}")
        
        if judgment["merged_content"]:
            merged = judgment["merged_content"]
        else:
            merged = existing_content
        
        if source_title:
            merged = add_source_to_content(merged, source_title)
        if source_paper_stem:
            merged = add_paper_to_related(merged, source_paper_stem)
        
        existing_path.write_text(merged, encoding='utf-8')
        
        with open(MERGE_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n[{timestamp}] MERGE | {title} <-> {existing_path.name}\n")
            f.write(f"  匹配方式: {match_method} | 相似度: {similarity:.2f}\n")
            f.write(f"  判断: 融合 | 理由: {judgment['reason']}\n")
        
        return (False, None, existing_path)
    else:
        print(f"    [Merge] LLM判断: 不融合 - {judgment['reason']}")
        
        with open(MERGE_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n[{timestamp}] NO_MERGE | {title} <-> {existing_path.name}\n")
            f.write(f"  匹配方式: {match_method} | 相似度: {similarity:.2f}\n")
            f.write(f"  判断: 不融合 | 理由: {judgment['reason']}\n")
        
        return (True, new_content, existing_path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="实体/概念融合工具")
    parser.add_argument("--check", type=str, help="检查给定标题是否已存在")
    parser.add_argument("--type", type=str, choices=["entity", "concept"], default="entity")
    args = parser.parse_args()
    
    if args.check:
        result = find_matching_page(args.check, args.type)
        if result:
            path, method = result
            print(f"找到匹配: {path.name} (方式: {method})")
        else:
            print("未找到匹配")
    
    print(f"\n知识库统计:")
    entities = load_existing_pages("entity")
    concepts = load_existing_pages("concept")
    print(f"  实体: {len(entities)} 个")
    print(f"  概念: {len(concepts)} 个")


if __name__ == "__main__":
    main()
