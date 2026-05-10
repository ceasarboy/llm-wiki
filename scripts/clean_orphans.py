#!/usr/bin/env python3
"""清理孤儿实体/概念页面 — 关联论文不存在的页面"""

import os
import re
import yaml
from pathlib import Path
from collections import defaultdict

WIKI_PATH = Path("C:/Users/Administrator/Documents/Obsidian Vault/wiki")
PAPERS_DIR = WIKI_PATH / "papers"
ENTITIES_DIR = WIKI_PATH / "entities"
CONCEPTS_DIR = WIKI_PATH / "concepts"

def get_paper_ids():
    """获取所有论文的 ID（文件名去掉 _论文.md 后缀）"""
    paper_ids = set()
    if PAPERS_DIR.exists():
        for f in PAPERS_DIR.glob("*.md"):
            name = f.stem
            if name.endswith("_论文"):
                name = name[:-3]
            paper_ids.add(name)
    return paper_ids

def extract_source_papers(content):
    """从页面内容提取 source 论文 ID"""
    sources = set()
    
    # 从 frontmatter 提取
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                source = fm.get("source", [])
                if isinstance(source, str):
                    source = [source]
                if isinstance(source, list):
                    for s in source:
                        if isinstance(s, str):
                            # 提取论文 ID
                            m = re.search(r'(\d{4}\.\d{4,5})', s)
                            if m:
                                sources.add(m.group(1))
            except:
                pass
    
    # 从正文提取 [Source: xxx] 标注
    for m in re.finditer(r'\[Source:\s*([^\]]+)\]', content):
        src = m.group(1)
        # 提取论文 ID
        m2 = re.search(r'(\d{4}\.\d{4,5})', src)
        if m2:
            sources.add(m2.group(1))
    
    # 从 [[wiki/papers/xxx]] 链接提取
    for m in re.finditer(r'\[\[wiki/papers/([^\]|]+)', content):
        src = m.group(1).replace("_论文", "").replace(".md", "")
        sources.add(src)
    
    return sources

def scan_pages(directory, page_type):
    """扫描目录下的所有页面"""
    pages = []
    if not directory.exists():
        return pages
    
    for f in directory.glob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
            sources = extract_source_papers(content)
            pages.append({
                "path": f,
                "name": f.stem,
                "type": page_type,
                "sources": sources,
            })
        except Exception as e:
            print(f"  ERROR reading {f}: {e}")
    
    return pages

def main():
    print("=" * 60)
    print("孤儿页面清理工具")
    print("=" * 60)
    
    # 1. 获取所有论文 ID
    paper_ids = get_paper_ids()
    print(f"\n论文总数: {len(paper_ids)}")
    
    # 2. 扫描实体和概念
    entities = scan_pages(ENTITIES_DIR, "entity")
    concepts = scan_pages(CONCEPTS_DIR, "concept")
    
    print(f"实体总数: {len(entities)}")
    print(f"概念总数: {len(concepts)}")
    
    # 3. 识别孤儿
    orphans = []
    for page in entities + concepts:
        if not page["sources"]:
            # 没有任何 source，可能是手动创建的
            continue
        
        # 检查所有 source 是否都不存在
        missing_sources = page["sources"] - paper_ids
        if len(missing_sources) == len(page["sources"]):
            # 所有 source 都不存在
            orphans.append(page)
    
    print(f"\n孤儿页面: {len(orphans)}")
    
    if not orphans:
        print("没有需要清理的页面")
        return
    
    # 4. 显示孤儿列表
    print("\n待删除页面:")
    for p in orphans[:20]:
        print(f"  [{p['type']}] {p['name']}")
        print(f"    missing sources: {p['sources']}")
    
    if len(orphans) > 20:
        print(f"  ... 还有 {len(orphans) - 20} 个")
    
    # 5. 确认删除
    confirm = input(f"\n确认删除 {len(orphans)} 个孤儿页面? (yes/no): ")
    if confirm.lower() != "yes":
        print("取消删除")
        return
    
    # 6. 执行删除
    deleted = 0
    for p in orphans:
        try:
            p["path"].unlink()
            deleted += 1
        except Exception as e:
            print(f"  ERROR deleting {p['path']}: {e}")
    
    print(f"\n已删除: {deleted} 个页面")

if __name__ == "__main__":
    main()
