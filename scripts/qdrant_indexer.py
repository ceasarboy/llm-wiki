"""Qdrant 本地模式向量索引器 — 用 BGE-M3 建立全量 Wiki 索引"""
import os
import sys
import yaml
import json
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from embedding_bge import encode, get_embedding_dim

RAGTEST_DIR = Path(__file__).parent.parent
CONFIG_PATH = RAGTEST_DIR / "config.yaml"
INDEX_DIR = RAGTEST_DIR / "index"
QDRANT_STORAGE = INDEX_DIR / "qdrant_data"
QDRANT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
EXCLUDE_IDS = {"log", "index"}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_qdrant_index(
    wiki_dir: Path,
    collection_name: str = "llm_wiki_bge",
    batch_size: int = 32,
):
    QDRANT_STORAGE.mkdir(parents=True, exist_ok=True)
    print(f"Qdrant storage: {QDRANT_STORAGE}")
    client = QdrantClient(path=str(QDRANT_STORAGE))

    dim = get_embedding_dim()

    try:
        client.delete_collection(collection_name)
        print(f"Dropped existing collection: {collection_name}")
    except Exception:
        pass

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    print(f"Created collection: {collection_name} (dim={dim})")

    md_files = list(wiki_dir.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files")

    points = []
    total = 0
    start = time.time()

    for i, md_file in enumerate(md_files):
        try:
            content = md_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                body = parts[2] if len(parts) >= 3 else content
            else:
                body = content
            body = body[:6000]
            page_id = str(md_file.relative_to(wiki_dir).with_suffix(""))
            if page_id in EXCLUDE_IDS:
                continue
        except Exception:
            continue

        points.append((page_id, body))

        if len(points) >= batch_size:
            texts = [p[1] for p in points]
            ids = [p[0] for p in points]
            embeddings = encode(texts, batch_size=batch_size)
            qdrant_points = [
                PointStruct(
                    id=str(uuid.uuid5(QDRANT_NAMESPACE, ids[j])),
                    vector=embeddings[j].tolist(),
                    payload={"page_id": ids[j]}
                )
                for j in range(len(ids))
            ]
            client.upsert(collection_name=collection_name, points=qdrant_points)
            total += len(points)
            elapsed = time.time() - start
            speed = total / elapsed if elapsed > 0 else 0
            print(f"  Indexed {total}/{len(md_files)} pages ({speed:.1f} docs/s)")
            points = []

    if points:
        texts = [p[1] for p in points]
        ids = [p[0] for p in points]
        embeddings = encode(texts, batch_size=batch_size)
        qdrant_points = [
            PointStruct(
                id=str(uuid.uuid5(QDRANT_NAMESPACE, ids[j])),
                vector=embeddings[j].tolist(),
                payload={"page_id": ids[j]}
            )
            for j in range(len(ids))
        ]
        client.upsert(collection_name=collection_name, points=qdrant_points)
        total += len(points)

    elapsed = time.time() - start
    print(f"\nDone! {total} pages indexed in {elapsed:.1f}s")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_DIR / "qmd_index.json", "w", encoding="utf-8") as f:
        json.dump({"collection": collection_name, "count": total, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, f)

    client.close()


if __name__ == "__main__":
    config = load_config()
    paths = config.get("paths", {})
    qdrant_cfg = config.get("qdrant", {})

    wiki_dir = Path(paths.get("wiki_dir", "wiki"))
    collection = qdrant_cfg.get("collection_name", "llm_wiki_bge")

    build_qdrant_index(wiki_dir, collection)
