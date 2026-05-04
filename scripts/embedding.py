"""
语义嵌入模型模块
统一的 sentence-transformers 嵌入模型管理
"""

import os


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
