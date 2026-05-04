"""知识图谱 API"""

import re
import traceback
from datetime import datetime
from typing import List, Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dependencies import WIKI_PATH

router = APIRouter(prefix="/graph", tags=["graph"])


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    tags: List[str] = []
    path: str


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str


class GraphData(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    metadata: dict


async def _build_graph_data(node_type_filter: str = "all") -> GraphData:
    nodes = []
    edges = []
    edge_set = set()
    node_set = set()
    node_contents = {}

    for subdir in ["papers", "entities", "concepts", "summaries"]:
        dir_path = WIKI_PATH / subdir
        if not dir_path.exists():
            continue

        for md_file in dir_path.glob("*.md"):
            try:
                node_id = f"{subdir}/{md_file.stem}"
                if subdir == "papers":
                    node_type = "paper"
                elif subdir == "summaries":
                    node_type = "synthesis"
                else:
                    node_type = subdir[:-1]

                content = md_file.read_text(encoding="utf-8")
                title = md_file.stem
                tags = []

                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            fm = yaml.safe_load(parts[1]) or {}
                            title = fm.get("title", md_file.stem)
                            raw_tags = fm.get("tags", [])
                            if isinstance(raw_tags, list):
                                tags = [str(t) for t in raw_tags]
                            elif raw_tags:
                                tags = [str(raw_tags)]
                        except Exception:
                            pass

                type_map = {
                    "paper": "paper",
                    "entity": "entity",
                    "concept": "concept",
                    "synthesis": "synthesis",
                }
                if (
                    node_type_filter != "all"
                    and node_type != type_map.get(node_type_filter, node_type_filter)
                ):
                    continue

                nodes.append(
                    GraphNode(
                        id=node_id,
                        label=str(title),
                        type=node_type,
                        tags=tags,
                        path=str(md_file),
                    )
                )
                node_set.add(node_id)
                node_contents[node_id] = content

            except Exception as e:
                print(f"Error processing file {md_file}: {e}")
                continue

    for node_id, content in node_contents.items():
        links = re.findall(r"\[\[([^\]]+)\]\]", content)
        for link in links:
            target_id = link.replace(".md", "")
            if "|" in target_id:
                target_id = target_id.split("|")[0]
            if "/" not in target_id:
                for t in ["papers", "entities", "concepts", "summaries"]:
                    candidate = f"{t}/{target_id}"
                    if candidate in node_set:
                        target_id = candidate
                        break

            if target_id in node_set:
                edge_key = f"{node_id}->{target_id}"
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    edges.append(
                        GraphEdge(
                            id=f"e_{len(edges)}",
                            source=node_id,
                            target=target_id,
                            type="relate",
                        )
                    )

    return GraphData(
        nodes=nodes,
        edges=edges,
        metadata={
            "totalNodes": len(nodes),
            "totalEdges": len(edges),
            "lastUpdated": datetime.now().isoformat(),
        },
    )


@router.get("/data", response_model=GraphData)
async def get_graph_data(type: str = "all"):
    try:
        return await _build_graph_data(type)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Graph data error: {str(e)}")


@router.get("/neighbors/{node_id:path}")
async def get_graph_neighbors(node_id: str, depth: int = 1):
    try:
        full_graph = await _build_graph_data("all")
        all_nodes = {n.id: n for n in full_graph.nodes}
        all_edges = full_graph.edges

        if node_id not in all_nodes:
            for candidate in [
                f"papers/{node_id}",
                f"entities/{node_id}",
                f"concepts/{node_id}",
            ]:
                if candidate in all_nodes:
                    node_id = candidate
                    break

        if node_id not in all_nodes:
            return GraphData(
                nodes=[], edges=[], metadata={"totalNodes": 0, "totalEdges": 0}
            )

        visited_nodes = {node_id}
        current_layer = {node_id}

        for _ in range(depth):
            next_layer = set()
            for edge in all_edges:
                if edge.source in current_layer and edge.target not in visited_nodes:
                    next_layer.add(edge.target)
                if edge.target in current_layer and edge.source not in visited_nodes:
                    next_layer.add(edge.source)
            visited_nodes.update(next_layer)
            current_layer = next_layer

        sub_nodes = [all_nodes[nid] for nid in visited_nodes if nid in all_nodes]
        sub_edges = [
            e
            for e in all_edges
            if e.source in visited_nodes and e.target in visited_nodes
        ]

        return GraphData(
            nodes=sub_nodes,
            edges=sub_edges,
            metadata={
                "totalNodes": len(sub_nodes),
                "totalEdges": len(sub_edges),
                "centerNode": node_id,
            },
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Graph neighbors error: {str(e)}")


@router.get("/stats")
async def get_graph_stats():
    graph_data = await _build_graph_data()
    type_counts = {}
    for node in graph_data.nodes:
        type_counts[node.type] = type_counts.get(node.type, 0) + 1

    return {
        "totalNodes": graph_data.metadata["totalNodes"],
        "totalEdges": graph_data.metadata["totalEdges"],
        "nodeTypes": type_counts,
        "lastUpdated": graph_data.metadata["lastUpdated"],
    }
