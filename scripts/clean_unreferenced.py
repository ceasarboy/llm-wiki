#!/usr/bin/env python3
"""检查孤立实体/概念 — 没有被任何论文引用的页面"""

import os
import re
import yaml
from pathlib import Path
from collections import defaultdict

WIKI_PATH = Path("C:/Users/Administrator/Documents/Obsidian Vault/wiki")
PAPERS_DIR = WIKI_PATH / "papers"
ENTITIES_DIR = WIKI_PATH / "entities"
CONCEPTS_DIR = WIKI_PATH / "concepts"

def get_all_page_names(directory):
    """获取目录下所有页面名称"""
    names = set()
    if directory.exists():
        for f in directory.glob("*.md"):
            names.add(f.stem)
    return names

def extract_linked_pages(content):
    """从论文内容提取引用的实体/概念"""
    linked = set()
    
    # 提取 [[entities/xxx]] 和 [[concepts/xxx]] (论文中用的格式)
    for m in re.finditer(r'\[\[(entities|concepts)/([^\]|]+)', content):
        name = m.group(2).replace(".md", "")
        linked.add(name)
    
    # 提取 [[wiki/entities/xxx]] 和 [[wiki/concepts/xxx]]
    for m in re.finditer(r'\[\[wiki/(entities|concepts)/([^\]|]+)', content):
        name = m.group(2).replace(".md", "")
        linked.add(name)
    
    # 提取 [[xxx]] 格式的内部链接
    for m in re.finditer(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content):
        link = m.group(1)
        if not link.startswith("raw/") and not link.startswith("wiki/") and not link.startswith("entities/") and not link.startswith("concepts/"):
            linked.add(link.replace(".md", ""))
    
    return linked

def main():
    print("=" * 60)
    print("孤立页面检查（未被任何论文引用）")
    print("=" * 60)
    
    # 1. 获取所有实体和概念名称
    entity_names = get_all_page_names(ENTITIES_DIR)
    concept_names = get_all_page_names(CONCEPTS_DIR)
    
    print(f"\n实体总数: {len(entity_names)}")
    print(f"概念总数: {len(concept_names)}")
    
    # 2. 扫描所有论文，收集被引用的实体/概念
    referenced_entities = set()
    referenced_concepts = set()
    
    if PAPERS_DIR.exists():
        for f in PAPERS_DIR.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                linked = extract_linked_pages(content)
                
                for name in linked:
                    if name in entity_names:
                        referenced_entities.add(name)
                    elif name in concept_names:
                        referenced_concepts.add(name)
            except Exception as e:
                print(f"  ERROR reading {f}: {e}")
    
    print(f"\n被引用的实体: {len(referenced_entities)}")
    print(f"被引用的概念: {len(referenced_concepts)}")
    
    # 3. 找出未被引用的
    orphan_entities = entity_names - referenced_entities
    orphan_concepts = concept_names - referenced_concepts
    
    print(f"\n未被引用的实体: {len(orphan_entities)}")
    print(f"未被引用的概念: {len(orphan_concepts)}")
    
    if orphan_entities:
        print("\n未引用实体列表:")
        for name in sorted(orphan_entities)[:30]:
            print(f"  [entity] {name}")
        if len(orphan_entities) > 30:
            print(f"  ... 还有 {len(orphan_entities) - 30} 个")
    
    if orphan_concepts:
        print("\n未引用概念列表:")
        for name in sorted(orphan_concepts)[:30]:
            print(f"  [concept] {name}")
        if len(orphan_concepts) > 30:
            print(f"  ... 还有 {len(orphan_concepts) - 30} 个")
    
    # 4. 询问是否删除
    total_orphans = len(orphan_entities) + len(orphan_concepts)
    if total_orphans == 0:
        print("\n没有孤立页面")
        return
    
    confirm = input(f"\n确认删除 {total_orphans} 个孤立页面? (yes/no): ")
    if confirm.lower() != "yes":
        print("取消删除")
        return
    
    # 5. 执行删除
    deleted = 0
    for name in orphan_entities:
        f = ENTITIES_DIR / f"{name}.md"
        if f.exists():
            f.unlink()
            deleted += 1
    
    for name in orphan_concepts:
        f = CONCEPTS_DIR / f"{name}.md"
        if f.exists():
            f.unlink()
            deleted += 1
    
    print(f"\n已删除: {deleted} 个页面")

if __name__ == "__main__":
    main()
