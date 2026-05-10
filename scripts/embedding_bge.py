"""BGE-M3 向量嵌入模块"""
import os
import numpy as np
from pathlib import Path
from typing import List, Union

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is None:
        from FlagEmbedding import BGEM3FlagModel
        _MODEL = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, device="cpu")
    return _MODEL


def encode(texts: Union[str, List[str]], batch_size: int = 8) -> np.ndarray:
    model = _load_model()
    if isinstance(texts, str):
        texts = [texts]
    embeddings = model.encode(
        texts, 
        batch_size=batch_size, 
        max_length=8192,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    return np.array(embeddings["dense_vecs"], dtype=np.float32)


def get_embedding_dim() -> int:
    return 1024


def test():
    emb = encode("测试文本")
    print(f"BGE-M3 dim: {emb.shape[1]}, sample: {emb[0][:5]}")


if __name__ == "__main__":
    test()
