#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChromaDB 索引脚本 (Phase 5)
为 wiki 页面创建向量索引，支持语义检索
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import hashlib

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_paths_config, get_index_config

# =============================================================================
# 配置
# =============================================================================

PATHS = get_paths_config()
INDEX_CFG = get_index_config()

WIKI_DIR = Path(PATHS["wiki_dir"])
RAW_DIR = Path(PATHS["raw_dir"])
INDEX_DIR = Path(PATHS["index_dir"])

# ChromaDB 配置
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"
COLLECTION_NAME = INDEX_CFG.get("collection_name", "llm_wiki")

# 嵌入模型配置
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"  # 中文优化

# 分块配置
CHUNK_SIZE = INDEX_CFG.get("chunk_size", 512)
CHUNK_OVERLAP = INDEX_CFG.get("chunk_overlap", 50)

# =============================================================================
# 工具函数
# =============================================================================

def parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """解析 YAML Frontmatter"""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                import yaml
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return frontmatter or {}, body
            except:
                pass
    return {}, content


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """将文本分块"""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # 尽量在句子边界分割
        if end < len(text):
            # 向后找句号、问号、感叹号
            for i in range(min(100, len(chunk)), 0, -1):
                if chunk[-i] in '。！？.!?\n':
                    chunk = chunk[:-i+1]
                    break
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return chunks


def get_doc_id(text: str) -> str:
    """生成文档唯一 ID"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:16]


# =============================================================================
# ChromaDB 操作
# =============================================================================

def get_chroma_client():
    """获取 ChromaDB 客户端"""
    try:
        import chromadb
        from chromadb.config import Settings
        
        client = chromadb.PersistentClient(
            path=str(CHROMA_PERSIST_DIR),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        return client
    except ImportError:
        print("错误: 未安装 chromadb。请运行: pip install chromadb")
        raise


def get_embedding_function():
    """获取嵌入函数"""
    from chromadb.utils import embedding_functions
    
    # 使用 ChromaDB 默认的 ONNX 嵌入函数（无需下载）
    print("  使用默认嵌入函数 (ONNX MiniLM-L6-V2)")
    return embedding_functions.DefaultEmbeddingFunction()


def create_collection(client, embedding_function=None):
    """创建或获取集合"""
    try:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_function,
            metadata={
                "hnsw:space": "cosine",
                "description": "LLM-Wiki 知识库向量索引"
            }
        )
        return collection
    except Exception as e:
        print(f"错误: 无法创建集合: {e}")
        raise


# =============================================================================
# 索引构建
# =============================================================================

def index_wiki_page(page_path: Path, collection) -> Dict:
    """索引单个 wiki 页面"""
    
    with open(page_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    frontmatter, body = parse_frontmatter(content)
    
    # 提取元数据
    doc_type = frontmatter.get('type', 'unknown')
    title = frontmatter.get('title', page_path.stem)
    tags = frontmatter.get('tags', [])
    source = frontmatter.get('source', '')
    
    # 分块
    chunks = chunk_text(body)
    
    # 准备 ChromaDB 数据
    ids = []
    documents = []
    metadatas = []
    
    for i, chunk in enumerate(chunks):
        chunk_id = f"{page_path.stem}_{i}"
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "page_path": str(page_path),
            "page_name": page_path.name,
            "title": title,
            "type": doc_type,
            "tags": json.dumps(tags, ensure_ascii=False),
            "source": source,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "indexed_at": datetime.now().isoformat()
        })
    
    # 添加到集合
    if documents:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    return {
        "page": str(page_path),
        "title": title,
        "type": doc_type,
        "chunks": len(chunks),
        "status": "indexed"
    }


def index_raw_doc(doc_path: Path, collection) -> Dict:
    """索引原始文档（用于全文检索）"""
    
    with open(doc_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分块
    chunks = chunk_text(content)
    
    # 准备 ChromaDB 数据
    ids = []
    documents = []
    metadatas = []
    
    for i, chunk in enumerate(chunks):
        chunk_id = f"raw_{doc_path.stem}_{i}"
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "page_path": str(doc_path),
            "page_name": doc_path.name,
            "title": doc_path.stem,
            "type": "raw",
            "tags": "[]",
            "source": f"raw/papers/markdown/{doc_path.name}",
            "chunk_index": i,
            "total_chunks": len(chunks),
            "indexed_at": datetime.now().isoformat()
        })
    
    # 添加到集合
    if documents:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    return {
        "page": str(doc_path),
        "title": doc_path.stem,
        "type": "raw",
        "chunks": len(chunks),
        "status": "indexed"
    }


# =============================================================================
# 主函数
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki ChromaDB 索引脚本")
    parser.add_argument("--wiki", action="store_true", help="索引 wiki 页面")
    parser.add_argument("--raw", action="store_true", help="索引原始文档")
    parser.add_argument("--reset", action="store_true", help="重置索引（删除并重建）")
    parser.add_argument("--limit", type=int, default=0, help="限制处理的文档数量")
    args = parser.parse_args()
    
    print("=" * 60)
    print("LLM-Wiki Indexer v3.0 (ChromaDB)")
    print("=" * 60)
    
    # 确保索引目录存在
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    # 获取 ChromaDB 客户端
    print(f"\n[1/4] 连接 ChromaDB: {CHROMA_PERSIST_DIR}")
    client = get_chroma_client()
    
    # 获取嵌入函数
    print(f"[2/4] 加载嵌入模型...")
    embedding_function = get_embedding_function()
    
    # 创建/获取集合
    print(f"[3/4] 获取集合: {COLLECTION_NAME}")
    collection = create_collection(client, embedding_function)
    
    # 重置索引（如果需要）
    if args.reset:
        print("  重置索引...")
        client.delete_collection(COLLECTION_NAME)
        collection = create_collection(client, embedding_function)
    
    # 获取当前统计
    current_count = collection.count()
    print(f"  当前索引: {current_count} 个 chunk")
    
    # 索引文档
    print(f"\n[4/4] 索引文档...")
    results = []
    
    if args.wiki:
        print("\n  索引 wiki 页面...")
        wiki_pages = list(WIKI_DIR.glob("**/*.md"))
        print(f"  发现 {len(wiki_pages)} 个 wiki 页面")
        
        if args.limit > 0:
            wiki_pages = wiki_pages[:args.limit]
        
        for i, page_path in enumerate(wiki_pages, 1):
            try:
                result = index_wiki_page(page_path, collection)
                results.append(result)
                if i % 10 == 0:
                    print(f"    已索引 {i}/{len(wiki_pages)}")
            except Exception as e:
                print(f"    错误 {page_path.name}: {e}")
                results.append({"page": str(page_path), "status": "error", "error": str(e)})
    
    if args.raw:
        print("\n  索引原始文档...")
        raw_docs = list(RAW_DIR.glob("*.md"))
        print(f"  发现 {len(raw_docs)} 个原始文档")
        
        if args.limit > 0:
            raw_docs = raw_docs[:args.limit]
        
        for i, doc_path in enumerate(raw_docs, 1):
            try:
                result = index_raw_doc(doc_path, collection)
                results.append(result)
                if i % 10 == 0:
                    print(f"    已索引 {i}/{len(raw_docs)}")
            except Exception as e:
                print(f"    错误 {doc_path.name}: {e}")
                results.append({"page": str(doc_path), "status": "error", "error": str(e)})
    
    # 最终统计
    final_count = collection.count()
    
    # 保存索引报告
    report = {
        "indexed_at": datetime.now().isoformat(),
        "collection": COLLECTION_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "previous_count": current_count,
        "final_count": final_count,
        "new_chunks": final_count - current_count,
        "documents": len(results),
        "results": results
    }
    
    report_file = INDEX_DIR / "index_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"索引完成:")
    print(f"  新增 chunks: {final_count - current_count}")
    print(f"  总 chunks: {final_count}")
    print(f"  处理文档: {len(results)}")
    print(f"  报告: {report_file}")
    print(f"{'=' * 60}")
    
    return 0


if __name__ == "__main__":
    exit(main())
