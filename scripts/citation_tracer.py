#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Citation Tracer: 引用追溯模块
从知识库页面提取引用关系，构建引用图，支持追溯和可视化。
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
from config_loader import get_paths_config

PATHS = get_paths_config()
WIKI_DIR = Path(PATHS["wiki_dir"])


def extract_citations(text: str) -> List[str]:
    """从文本中提取 [Source: ...] 引用"""
    pattern = r'\[Source:\s*([^\]]+)\]'
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches]


def extract_wikilinks(text: str) -> List[str]:
    """从文本中提取 [[...]] 双向链接"""
    pattern = r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches]


def extract_references_section(text: str) -> List[str]:
    """从页面底部参考文献章节提取条目"""
    refs = []
    lines = text.split('\n')
    in_refs = False
    for line in lines:
        line = line.strip()
        if re.match(r'^#+\s*(参考|引用|来源|文献|References?)', line, re.IGNORECASE):
            in_refs = True
            continue
        if in_refs and re.match(r'^#+\s', line):
            in_refs = False
            continue
        if in_refs and line:
            refs.append(line)
    return refs


def build_citation_graph(wiki_dir: Path, include_wikilinks: bool = True) -> Dict:
    """构建引用关系图"""

    nodes = []
    edges = []
    node_map = {}

    for md_file in wiki_dir.rglob('*.md'):
        node_id = md_file.stem
        node_path = str(md_file.relative_to(wiki_dir))

        try:
            text = md_file.read_text(encoding='utf-8')
        except Exception:
            continue

        fm = {}
        if text.startswith('---'):
            end = text.find('---', 3)
            if end > 0:
                for line in text[3:end].strip().split('\n'):
                    if ':' in line:
                        k, _, v = line.partition(':')
                        fm[k.strip()] = v.strip().strip('"').strip("'")

        page_type = fm.get('type', 'unknown')
        tags = []
        raw_tags = fm.get('tags', '')
        if isinstance(raw_tags, str):
            tags = [t.strip().strip('"').strip("'") for t in raw_tags.strip('[]').split(',') if t.strip()]
        elif isinstance(raw_tags, list):
            tags = raw_tags

        sources = extract_citations(text)
        wikilinks = extract_wikilinks(text) if include_wikilinks else []
        references = extract_references_section(text)

        node_info = {
            "id": node_id,
            "path": node_path,
            "type": page_type,
            "tags": tags,
            "citation_count": len(sources),
            "wikilink_count": len(wikilinks),
            "reference_count": len(references),
        }
        nodes.append(node_info)
        node_map[node_id] = node_info

        for source in sources:
            edges.append({
                "source": node_id,
                "target": source,
                "type": "source_citation",
            })

        for link in wikilinks:
            edges.append({
                "source": node_id,
                "target": link,
                "type": "wikilink",
            })

    result = {
        "generated": datetime.now().isoformat(),
        "wiki_dir": str(wiki_dir),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }

    return result


def trace_citation_chain(graph: Dict, target: str, direction: str = "backward", max_depth: int = 5) -> List[Dict]:
    """追溯引用链：找到引用或被引用目标的所有页面"""

    edges = graph["edges"]
    node_map = {n["id"]: n for n in graph["nodes"]}
    visited = set()
    chain = []

    def trace(current: str, depth: int):
        if depth > max_depth or current in visited:
            return
        visited.add(current)

        for edge in edges:
            if direction == "backward" and edge["target"] == current:
                next_node = edge["source"]
            elif direction == "forward" and edge["source"] == current:
                next_node = edge["target"]
            else:
                continue

            if next_node in node_map:
                chain.append({
                    "from": edge["source"],
                    "to": edge["target"],
                    "type": edge["type"],
                    "depth": depth,
                    "from_info": node_map.get(edge["source"], {}),
                })
            trace(next_node, depth + 1)

    trace(target, 1)
    return chain


def find_most_cited(graph: Dict, top_n: int = 10) -> List[Dict]:
    """找出被引用最多的页面"""

    cite_count = defaultdict(int)
    for edge in graph["edges"]:
        if edge["type"] == "source_citation":
            cite_count[edge["target"]] += 1

    sorted_cites = sorted(cite_count.items(), key=lambda x: -x[1])[:top_n]
    node_map = {n["id"]: n for n in graph["nodes"]}

    return [
        {
            "id": target,
            "citation_count": count,
            "info": node_map.get(target, {}),
        }
        for target, count in sorted_cites
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Citation Tracer: 引用图构建与追溯")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    build_parser = subparsers.add_parser("build", help="构建引用图")
    build_parser.add_argument("--output", type=str, default=None, help="输出 JSON 文件")
    build_parser.add_argument("--no-wikilinks", action="store_true", help="不包含 [[wiki链接]]")

    trace_parser = subparsers.add_parser("trace", help="追溯引用链")
    trace_parser.add_argument("target", type=str, help="目标页面名称")
    trace_parser.add_argument("--direction", type=str, default="backward", choices=["backward", "forward"])
    trace_parser.add_argument("--max-depth", type=int, default=5)
    trace_parser.add_argument("--graph-file", type=str, default=None, help="引用图 JSON 文件")

    top_parser = subparsers.add_parser("top", help="被引用最多的页面")
    top_parser.add_argument("--n", type=int, default=10)
    top_parser.add_argument("--graph-file", type=str, default=None)

    args = parser.parse_args()

    if args.command == "build":
        graph = build_citation_graph(WIKI_DIR, include_wikilinks=not args.no_wikilinks)
        output = args.output or str(WIKI_DIR.parent / "citation_graph.json")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
        print(f"引用图已保存: {output}")
        print(f"节点: {graph['node_count']}, 边: {graph['edge_count']}")

    elif args.command == "trace":
        graph_file = args.graph_file or str(WIKI_DIR.parent / "citation_graph.json")
        if not Path(graph_file).exists():
            print(f"引用图不存在，请先运行 build: {graph_file}")
            sys.exit(1)
        with open(graph_file, 'r', encoding='utf-8') as f:
            graph = json.load(f)
        chain = trace_citation_chain(graph, args.target, args.direction, args.max_depth)
        print(json.dumps(chain, ensure_ascii=False, indent=2))

    elif args.command == "top":
        graph_file = args.graph_file or str(WIKI_DIR.parent / "citation_graph.json")
        if not Path(graph_file).exists():
            print(f"引用图不存在，请先运行 build: {graph_file}")
            sys.exit(1)
        with open(graph_file, 'r', encoding='utf-8') as f:
            graph = json.load(f)
        top = find_most_cited(graph, args.n)
        print(json.dumps(top, ensure_ascii=False, indent=2))

    else:
        parser.print_help()