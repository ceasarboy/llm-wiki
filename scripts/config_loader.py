#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载模块
统一加载 config.yaml 和环境变量
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

# 配置文件路径
CONFIG_FILE = Path("E:/ragtest/config.yaml")


def load_config() -> Dict[str, Any]:
    """
    加载配置文件
    优先级：环境变量 > 配置文件 > 默认值
    """
    # 加载配置文件
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    else:
        config = {}
    
    # 从环境变量覆盖
    # LLM 配置
    if os.environ.get("LLM_API_URL"):
        config.setdefault("llm", {})["api_url"] = os.environ["LLM_API_URL"]
    
    if os.environ.get("LLM_MODEL"):
        config.setdefault("llm", {})["model"] = os.environ["LLM_MODEL"]
    
    if os.environ.get("LLM_API_KEY"):
        config.setdefault("llm", {})["api_key"] = os.environ["LLM_API_KEY"]
    
    return config


def get_llm_config() -> Dict[str, Any]:
    """获取 LLM 配置"""
    config = load_config()
    return config.get("llm", {
        "api_url": "http://127.0.0.1:28789/v1/chat/completions",
        "model": "default",
        "api_key": "",
        "temperature": 0.3,
        "max_tokens": 4000,
        "timeout": 120
    })


def get_paths_config() -> Dict[str, Any]:
    """获取路径配置"""
    config = load_config()
    return config.get("paths", {
        "vault_root": "C:/Users/Administrator/Documents/Obsidian Vault",
        "raw_dir": "C:/Users/Administrator/Documents/Obsidian Vault/raw/papers/markdown",
        "wiki_dir": "C:/Users/Administrator/Documents/Obsidian Vault/wiki",
        "work_dir": "E:/ragtest",
        "index_dir": "E:/ragtest/index",
        "templates_dir": "E:/ragtest/templates",
        "output_dir": "E:/ragtest/generated"
    })


def get_index_config() -> Dict[str, Any]:
    """获取索引配置"""
    config = load_config()
    return config.get("index", {
        "collection_name": "llm_wiki",
        "embedding_model": "default",
        "chunk_size": 512,
        "chunk_overlap": 50
    })


def get_search_config() -> Dict[str, Any]:
    """获取检索配置"""
    config = load_config()
    return config.get("search", {
        "top_k": 10,
        "vector_weight": 0.7,
        "keyword_weight": 0.3
    })


def get_scoring_config() -> Dict[str, Any]:
    """获取评分配置"""
    config = load_config()
    return config.get("scoring", {
        "pass_threshold": 7.5,
        "weights": {
            "completeness": 0.25,
            "accuracy": 0.25,
            "structure": 0.20,
            "discoverability": 0.15,
            "conflict_handling": 0.15
        }
    })


def get_generation_config() -> Dict[str, Any]:
    """获取生成配置"""
    config = load_config()
    return config.get("generation", {
        "min_content_length": 3000,
        "source_id_required": True,
        "source_id_min_ratio": 0.6,
        "extract_entities": True,
        "extract_concepts": True,
        "max_retries": 3
    })


# 全局配置实例（延迟加载）
_config = None

def get_config() -> Dict[str, Any]:
    """获取全局配置（单例）"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


if __name__ == "__main__":
    # 测试配置加载
    config = load_config()
    print("配置加载成功:")
    print(f"  LLM API URL: {config.get('llm', {}).get('api_url')}")
    print(f"  LLM Model: {config.get('llm', {}).get('model')}")
    print(f"  API Key: {'已设置' if config.get('llm', {}).get('api_key') else '未设置'}")
    print(f"  Raw Dir: {config.get('paths', {}).get('raw_dir')}")
