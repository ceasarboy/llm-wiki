#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qmd 混合检索脚本 (简化版)
结合向量检索（语义）和关键词检索（BM25）
"""

import os
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

INDEX_DIR = Path(PATHS.get("index_dir", "E:/ragtest/index"))
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"
COLLECTION_NAME = "llm_wiki"

QMD_INDEX_FILE = INDEX_DIR / "qmd_index.json"

DEFAULT_TOP_K = 10
VECTOR_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3


# =============================================================================
# 语义嵌入模型（与 indexer_simple.py 一致）
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
# ChromaDB 操作
# =============================================================================

def get_chroma_client():
    """获取 ChromaDB 客户端"""
    import chromadb
    from chromadb.config import Settings
    
    client = chromadb.PersistentClient(
        path=str(CHROMA_PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False)
    )
    return client


def vector_search(query: str, top_k: int = DEFAULT_TOP_K) -> List[Dict]:
    """向量语义检索"""
    
    client = get_chroma_client()
    ef = SentenceTransformerEmbedding()
    try:
        collection = client.get_collection(COLLECTION_NAME, embedding_function=ef)
    except Exception:
        print(f"Collection '{COLLECTION_NAME}' 不存在，请先运行索引构建")
        return []
    
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    # 格式化结果
    formatted = []
    for i in range(len(results['ids'][0])):
        formatted.append({
            "id": results['ids'][0][i],
            "content": results['documents'][0][i],
            "metadata": results['metadatas'][0][i],
            "distance": results['distances'][0][i],
            "score": 1 - results['distances'][0][i],
            "type": "vector"
        })
    
    return formatted


# =============================================================================
# BM25 关键词检索
# =============================================================================

def tokenize(text: str) -> List[str]:
    """分词（支持中英文混合）"""
    text = re.sub(r'([a-zA-Z])([^\x00-\x7F])', r'\1 \2', text)
    text = re.sub(r'([^\x00-\x7F])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', text.lower())
    tokens = text.split()
    stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'of', 'at',
                 'for', 'with', '的', '是', '在', '和', '了', '有', '什么',
                 '怎么', '如何', '哪些', '为什么', '吗', '呢', '吧'}
    result = []
    for t in tokens:
        if t in stopwords or len(t) < 1:
            continue
        if len(t) <= 1 and not re.match(r'[\u4e00-\u9fff]', t):
            continue
        if re.match(r'^[\u4e00-\u9fff]+$', t):
            for i in range(len(t)):
                if i + 1 < len(t):
                    result.append(t[i:i+2])
                if i + 2 < len(t):
                    result.append(t[i:i+3])
            result.append(t)
        else:
            result.append(t)
    return result


def build_qmd_index():
    """构建 qmd 关键词索引"""
    
    print("构建 qmd 索引...")
    
    client = get_chroma_client()
    ef = SentenceTransformerEmbedding()
    try:
        collection = client.get_collection(COLLECTION_NAME, embedding_function=ef)
    except Exception:
        print(f"Collection '{COLLECTION_NAME}' 不存在，请先运行索引构建")
        return {"documents": {}, "terms": {}, "doc_count": 0, "avg_doc_length": 0}
    
    all_docs = collection.get(include=["documents", "metadatas"])
    
    index = {"documents": {}, "terms": {}, "doc_count": 0, "avg_doc_length": 0}
    total_length = 0
    
    for i, doc_id in enumerate(all_docs['ids']):
        content = all_docs['documents'][i]
        metadata = all_docs['metadatas'][i]
        
        terms = tokenize(content)
        
        index["documents"][doc_id] = {
            "content": content,
            "metadata": metadata,
            "length": len(terms),
            "terms": terms
        }
        
        total_length += len(terms)
        
        for term in set(terms):
            if term not in index["terms"]:
                index["terms"][term] = {"doc_freq": 0, "postings": {}}
            index["terms"][term]["doc_freq"] += 1
            index["terms"][term]["postings"][doc_id] = terms.count(term)
    
    index["doc_count"] = len(all_docs['ids'])
    index["avg_doc_length"] = total_length / index["doc_count"] if index["doc_count"] > 0 else 0
    index["built_at"] = datetime.now().isoformat()
    
    with open(QMD_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False)
    
    print(f"  索引文档: {index['doc_count']}")
    print(f"  唯一词项: {len(index['terms'])}")
    
    return index


def bm25_search(query: str, index: Dict, top_k: int = DEFAULT_TOP_K) -> List[Dict]:
    """BM25 关键词检索"""
    
    import math
    
    k1, b = 1.5, 0.75
    query_terms = tokenize(query)
    scores = {}
    
    for term in query_terms:
        if term not in index["terms"]:
            continue
        
        term_info = index["terms"][term]
        idf = math.log((index["doc_count"] - term_info["doc_freq"] + 0.5) / (term_info["doc_freq"] + 0.5) + 1)
        
        for doc_id, tf in term_info["postings"].items():
            doc_length = index["documents"][doc_id]["length"]
            avg_length = index["avg_doc_length"]
            
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_length / avg_length))
            score = idf * (numerator / denominator)
            
            scores[doc_id] = scores.get(doc_id, 0) + score
    
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    
    results = []
    for doc_id, score in sorted_scores:
        doc_info = index["documents"][doc_id]
        results.append({
            "id": doc_id,
            "content": doc_info["content"],
            "metadata": doc_info["metadata"],
            "score": score,
            "type": "keyword"
        })
    
    return results


# =============================================================================
# 混合检索
# =============================================================================

def hybrid_search(query: str, top_k: int = DEFAULT_TOP_K,
                  vector_weight: float = VECTOR_WEIGHT,
                  keyword_weight: float = KEYWORD_WEIGHT) -> List[Dict]:
    """混合检索"""
    
    print(f"\n查询: {query}")
    print(f"参数: top_k={top_k}, vector_weight={vector_weight}, keyword_weight={keyword_weight}")
    
    print("\n[1/3] 向量检索...")
    vector_results = vector_search(query, top_k=top_k * 4)
    print(f"  返回 {len(vector_results)} 个结果")
    
    print("\n[2/3] 关键词检索...")
    if QMD_INDEX_FILE.exists():
        with open(QMD_INDEX_FILE, 'r', encoding='utf-8') as f:
            index = json.load(f)
    else:
        index = build_qmd_index()
    
    keyword_results = bm25_search(query, index, top_k=top_k * 4)
    print(f"  返回 {len(keyword_results)} 个结果")
    
    print("\n[3/3] 融合结果...")
    
    # 归一化
    if vector_results:
        max_v = max(r["score"] for r in vector_results)
        for r in vector_results:
            r["normalized_score"] = r["score"] / max_v if max_v > 0 else 0
    
    if keyword_results:
        max_k = max(r["score"] for r in keyword_results)
        for r in keyword_results:
            r["normalized_score"] = r["score"] / max_k if max_k > 0 else 0
    
    # 合并
    merged = {}
    for r in vector_results:
        doc_id = r["id"]
        merged[doc_id] = {
            "id": doc_id, "content": r["content"], "metadata": r["metadata"],
            "vector_score": r["normalized_score"], "keyword_score": 0,
            "final_score": r["normalized_score"] * vector_weight
        }
    
    for r in keyword_results:
        doc_id = r["id"]
        if doc_id in merged:
            merged[doc_id]["keyword_score"] = r["normalized_score"]
            merged[doc_id]["final_score"] += r["normalized_score"] * keyword_weight
        else:
            merged[doc_id] = {
                "id": doc_id, "content": r["content"], "metadata": r["metadata"],
                "vector_score": 0, "keyword_score": r["normalized_score"],
                "final_score": r["normalized_score"] * keyword_weight
            }
    
    query_lower = query.lower()
    query_terms = set(re.findall(r'[a-zA-Z]+', query_lower))
    query_terms.update(set(re.findall(r'[\u4e00-\u9fff]+', query_lower)))
    for doc_id, doc_info in merged.items():
        title = doc_info["metadata"].get("title", "").lower()
        page_name = doc_info["metadata"].get("page_name", "").lower()
        page_type = doc_info["metadata"].get("type", "")
        title_terms = set(re.findall(r'[a-zA-Z]+', title))
        title_terms.update(set(re.findall(r'[\u4e00-\u9fff]+', title)))
        overlap = query_terms & title_terms
        if overlap:
            base_boost = 0.5 if page_type in ("concept", "entity") else 0.2
            overlap_ratio = len(overlap) / max(len(title_terms), 1)
            doc_info["final_score"] += base_boost * overlap_ratio
    
    final_results = sorted(merged.values(), key=lambda x: x["final_score"], reverse=True)[:top_k]
    
    return final_results


# =============================================================================
# 主函数
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki qmd 混合检索")
    parser.add_argument("query", nargs="?", help="查询语句")
    parser.add_argument("--build-index", action="store_true", help="构建 qmd 索引")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="返回结果数量")
    args = parser.parse_args()
    
    print("=" * 60)
    print("LLM-Wiki qmd Search v3.0")
    print("=" * 60)
    
    if args.build_index:
        build_qmd_index()
        return 0
    
    if not args.query:
        print("错误: 请提供查询语句或使用 --build-index")
        return 1
    
    results = hybrid_search(args.query, top_k=args.top_k)
    
    print(f"\n{'=' * 60}")
    print(f"检索结果 (Top {len(results)}):")
    print(f"{'=' * 60}")
    
    for i, result in enumerate(results, 1):
        metadata = result["metadata"]
        print(f"\n[{i}] 综合得分: {result['final_score']:.3f} "
              f"(向量: {result['vector_score']:.3f}, 关键词: {result['keyword_score']:.3f})")
        print(f"    来源: {metadata.get('page_name', 'unknown')}")
        print(f"    标题: {metadata.get('title', 'unknown')}")
        content = result["content"][:200].replace('\n', ' ')
        content = ''.join(c for c in content if c.isprintable() or c == ' ')
        print(f"    内容: {content}...")
    
    # 保存结果
    output_file = INDEX_DIR / f"search_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "query": args.query,
            "timestamp": datetime.now().isoformat(),
            "parameters": {"top_k": args.top_k},
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果保存: {output_file}")
    print(f"{'=' * 60}")
    
    return 0


if __name__ == "__main__":
    exit(main())
