#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChromaDB 索引脚本
使用 sentence-transformers 语义嵌入构建向量索引
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import re

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_paths_config

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
if not os.environ.get('HF_ENDPOINT'):
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

PATHS = get_paths_config()

RAW_DIR = Path(PATHS["raw_dir"])
WIKI_DIR = Path(PATHS["wiki_dir"])
INDEX_DIR = Path(PATHS.get("index_dir", "E:/ragtest/index"))
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"
COLLECTION_NAME = "llm_wiki"

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# =============================================================================
# 语义嵌入模型
# =============================================================================

class SentenceTransformerEmbedding:
    """基于 sentence-transformers 的语义嵌入"""
    
    _instance = None
    _model = None
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.dim = 384
    
    @classmethod
    def get_model(cls, model_name: str = "all-MiniLM-L6-v2"):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            try:
                cls._model = SentenceTransformer(model_name)
            except Exception:
                os.environ.pop('HF_HUB_OFFLINE', None)
                os.environ.pop('TRANSFORMERS_OFFLINE', None)
                cls._model = SentenceTransformer(model_name)
        return cls._model
    
    def __call__(self, input):
        return self.embed_documents(input)
    
    def embed_documents(self, texts):
        texts = texts if isinstance(texts, list) else [texts]
        model = self.get_model(self.model_name)
        embeddings = model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()
    
    def embed_query(self, input):
        return self.embed_documents(input)
    
    def name(self):
        return f"sentence-transformers/{self.model_name}"


# =============================================================================
# 工具函数
# =============================================================================

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """将文本分块"""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # 尽量在句子边界分割
        if end < len(text):
            for i in range(min(100, len(chunk)), 0, -1):
                if chunk[-i] in '。！？.!?\n':
                    chunk = chunk[:len(chunk) - i + 1]
                    break
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return chunks


# =============================================================================
# ChromaDB 操作
# =============================================================================

def get_chroma_client():
    """获取 ChromaDB 客户端"""
    import chromadb
    from chromadb.config import Settings
    
    client = chromadb.PersistentClient(
        path=str(CHROMA_PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False, allow_reset=True)
    )
    return client


def index_raw_doc(doc_path: Path, collection) -> Dict:
    """索引原始文档"""
    
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
            "source": f"raw/papers/markdown/{doc_path.name}",
            "chunk_index": i,
            "total_chunks": len(chunks),
            "indexed_at": datetime.now().isoformat()
        })
    
    # 添加到集合
    if documents:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    
    return {
        "page": str(doc_path),
        "title": doc_path.stem,
        "chunks": len(chunks),
        "status": "indexed"
    }


def index_wiki_page(page_path: Path, collection) -> Dict:
    """索引wiki页面（论文、实体、概念）"""
    
    with open(page_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取frontmatter中的信息
    import re
    title = ""
    page_type = ""
    for line in content.split('\n'):
        if line.startswith('title:'):
            title = line.split(':', 1)[1].strip().strip('"').strip("'")
        if line.startswith('type:'):
            page_type = line.split(':', 1)[1].strip().strip('"').strip("'")
    
    # 去掉frontmatter
    if content.startswith('---'):
        end = content.find('---', 3)
        if end >= 0:
            content = content[end+3:].strip()
    
    # 分块
    chunks = chunk_text(content)
    
    # 确定子目录类型
    rel_path = page_path.relative_to(WIKI_DIR)
    sub_type = rel_path.parts[0] if len(rel_path.parts) > 1 else "wiki"
    
    # 准备 ChromaDB 数据
    ids = []
    documents = []
    metadatas = []
    
    page_stem = page_path.stem
    
    for i, chunk in enumerate(chunks):
        chunk_id = f"wiki_{sub_type}_{page_stem}_{i}"
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "page_path": str(page_path),
            "page_name": page_stem,
            "title": title or page_stem,
            "type": page_type or sub_type,
            "source": f"wiki/{rel_path}",
            "chunk_index": i,
            "total_chunks": len(chunks),
            "indexed_at": datetime.now().isoformat()
        })
    
    # 添加到集合
    if documents:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    
    return {
        "page": str(page_path),
        "title": title or page_stem,
        "type": page_type or sub_type,
        "chunks": len(chunks),
        "status": "indexed"
    }


# =============================================================================
# 主函数
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki ChromaDB 索引脚本（简化版）")
    parser.add_argument("--raw", action="store_true", help="索引原始文档")
    parser.add_argument("--reset", action="store_true", help="重置索引")
    parser.add_argument("--rebuild", action="store_true", help="重建索引（删除旧索引）")
    parser.add_argument("--wiki-only", action="store_true", help="仅索引wiki目录")
    parser.add_argument("--raw-only", action="store_true", help="仅索引raw目录")
    parser.add_argument("--limit", type=int, default=0, help="限制处理的文档数量")
    args = parser.parse_args()
    
    print("=" * 60)
    print("LLM-Wiki Indexer v3.0 (Semantic Embedding)")
    print("=" * 60)
    
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    
    # 获取 ChromaDB 客户端
    print(f"\n[1/3] 连接 ChromaDB: {CHROMA_PERSIST_DIR}")
    client = get_chroma_client()
    
    # 使用简单的哈希嵌入
    print(f"[2/3] 加载语义嵌入模型 (all-MiniLM-L6-v2)")
    embedding_function = SentenceTransformerEmbedding()
    
    # 创建/获取集合
    print(f"[3/3] 获取集合: {COLLECTION_NAME}")
    
    if args.reset or args.rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
            print("  已重置索引")
        except:
            pass
    
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"}
    )
    
    current_count = collection.count()
    print(f"  当前索引: {current_count} 个 chunk")
    
    results = []
    
    # 索引原始文档
    if not args.wiki_only:
        if args.raw or args.raw_only or (not args.wiki_only and not args.raw_only):
            print(f"\n索引原始文档...")
            raw_docs = list(RAW_DIR.glob("*.md"))
            print(f"  发现 {len(raw_docs)} 个原始文档")
            
            if args.limit > 0:
                raw_docs = raw_docs[:args.limit]
                print(f"  限制处理: {args.limit} 个")
            
            for i, doc_path in enumerate(raw_docs, 1):
                try:
                    result = index_raw_doc(doc_path, collection)
                    results.append(result)
                    print(f"  [{i}/{len(raw_docs)}] {doc_path.name}: {result['chunks']} chunks")
                except Exception as e:
                    print(f"  [{i}/{len(raw_docs)}] {doc_path.name}: 错误 - {e}")
                    results.append({"page": str(doc_path), "status": "error", "error": str(e)})
    
    # 索引 wiki 目录
    if not args.raw_only:
        if WIKI_DIR.exists():
            print(f"\n--- 索引 wiki 目录: {WIKI_DIR} ---")
            wiki_files = []
            for sub_dir in ["papers", "entities", "concepts"]:
                sub_path = WIKI_DIR / sub_dir
                if sub_path.exists():
                    wiki_files.extend(sorted(sub_path.glob("*.md")))
            
            print(f"找到 {len(wiki_files)} 个wiki页面")
            
            for page_path in wiki_files:
                try:
                    result = index_wiki_page(page_path, collection)
                    results.append(result)
                    print(f"  ✅ {page_path.name}: {result['chunks']} chunks ({result.get('type', 'unknown')})")
                except Exception as e:
                    print(f"  ❌ {page_path.name}: {e}")
                    results.append({"page": str(page_path), "status": "error", "error": str(e)})
        else:
            print(f"wiki 目录不存在: {WIKI_DIR}")
    
    # 最终统计
    final_count = collection.count()
    
    # 保存报告
    report = {
        "indexed_at": datetime.now().isoformat(),
        "collection": COLLECTION_NAME,
        "embedding": "SentenceTransformerEmbedding (all-MiniLM-L6-v2)",
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
