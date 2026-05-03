#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本控制模块
功能：
  1. save_version(): 保存新版本（保存到 wiki/history/ 目录）
  2. get_version_list(): 获取版本列表
  3. get_version_content(): 获取指定版本内容
  4. restore_version(): 恢复到指定版本
"""

import os
import sys
import re
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_paths_config

PATHS = get_paths_config()
WIKI_DIR = Path(PATHS["wiki_dir"])
HISTORY_DIR = WIKI_DIR / "history"


def _get_history_dir(content_type: str) -> Path:
    """获取历史版本目录"""
    if content_type == "paper":
        return HISTORY_DIR / "papers"
    elif content_type == "entity":
        return HISTORY_DIR / "entities"
    elif content_type == "concept":
        return HISTORY_DIR / "concepts"
    else:
        return HISTORY_DIR / "papers"


def _parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """解析 YAML Frontmatter"""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            import yaml
            try:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return frontmatter or {}, body
            except:
                pass
    return {}, content


def _build_frontmatter(frontmatter: Dict, updates: Dict) -> str:
    """构建更新后的 Frontmatter"""
    import yaml
    merged = {**frontmatter, **updates}
    return yaml.dump(merged, allow_unicode=True, default_flow_style=False)


def save_version(
    file_path: Path,
    save_reason: str = "用户修改",
    content_type: str = None
) -> Tuple[bool, int, str]:
    """
    保存新版本
    
    参数:
        file_path: 当前文件路径
        save_reason: 保存原因
        content_type: 内容类型 (paper/entity/concept)
    
    返回:
        (success, version_number, history_file_path)
    """
    if not file_path.exists():
        return False, 0, None
    
    # 自动检测内容类型
    if content_type is None:
        if "papers" in str(file_path):
            content_type = "paper"
        elif "entities" in str(file_path):
            content_type = "entity"
        elif "concepts" in str(file_path):
            content_type = "concept"
        else:
            content_type = "paper"
    
    history_dir = _get_history_dir(content_type)
    history_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取当前内容
    content = file_path.read_text(encoding='utf-8')
    frontmatter, body = _parse_frontmatter(content)
    
    # 确定版本号
    existing_versions = list(history_dir.glob(f"{file_path.stem}_v*.md"))
    if existing_versions:
        version_numbers = []
        for v in existing_versions:
            match = re.search(r'_v(\d+)\.md$', v.name)
            if match:
                version_numbers.append(int(match.group(1)))
        next_version = max(version_numbers) + 1 if version_numbers else 1
    else:
        next_version = 1
    
    # 构建历史版本文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_filename = f"{file_path.stem}_v{next_version}_{timestamp}.md"
    history_file = history_dir / history_filename
    
    # 更新 frontmatter
    updated_fm = {
        **frontmatter,
        "version": next_version,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "save_reason": save_reason,
        "original_file": str(file_path.relative_to(WIKI_DIR)),
    }
    
    # 构建历史版本内容
    history_content = f"---\n{_build_frontmatter(updated_fm, {})}---\n\n{body}"
    
    # 保存历史版本
    history_file.write_text(history_content, encoding='utf-8')
    
    print(f"[VersionControl] 保存版本 {next_version}: {history_file.name}")
    return True, next_version, str(history_file)


def get_version_list(
    file_path: Path,
    content_type: str = None
) -> List[Dict]:
    """
    获取版本列表
    
    参数:
        file_path: 当前文件路径
        content_type: 内容类型
    
    返回:
        版本列表 [{"version": 1, "saved_at": "...", "save_reason": "...", "file": "..."}, ...]
    """
    if content_type is None:
        if "papers" in str(file_path):
            content_type = "paper"
        elif "entities" in str(file_path):
            content_type = "entity"
        elif "concepts" in str(file_path):
            content_type = "concept"
        else:
            content_type = "paper"
    
    history_dir = _get_history_dir(content_type)
    
    if not history_dir.exists():
        return []
    
    versions = []
    for history_file in history_dir.glob(f"{file_path.stem}_v*.md"):
        try:
            content = history_file.read_text(encoding='utf-8')
            frontmatter, _ = _parse_frontmatter(content)
            
            versions.append({
                "version": frontmatter.get("version", 0),
                "saved_at": frontmatter.get("saved_at", ""),
                "save_reason": frontmatter.get("save_reason", ""),
                "file": str(history_file),
                "filename": history_file.name,
                "size": history_file.stat().st_size,
            })
        except Exception as e:
            print(f"[VersionControl] 警告: 无法读取 {history_file.name}: {e}")
    
    # 按版本号降序排列
    versions.sort(key=lambda x: x["version"], reverse=True)
    return versions


def get_version_content(
    file_path: Path,
    version: int,
    content_type: str = None
) -> Optional[str]:
    """
    获取指定版本内容
    
    参数:
        file_path: 当前文件路径
        version: 版本号
        content_type: 内容类型
    
    返回:
        版本内容字符串，不存在返回 None
    """
    if content_type is None:
        if "papers" in str(file_path):
            content_type = "paper"
        elif "entities" in str(file_path):
            content_type = "entity"
        elif "concepts" in str(file_path):
            content_type = "concept"
        else:
            content_type = "paper"
    
    history_dir = _get_history_dir(content_type)
    
    # 查找指定版本文件
    for history_file in history_dir.glob(f"{file_path.stem}_v{version}_*.md"):
        return history_file.read_text(encoding='utf-8')
    
    return None


def restore_version(
    file_path: Path,
    version: int,
    content_type: str = None
) -> Tuple[bool, str]:
    """
    恢复到指定版本
    
    参数:
        file_path: 当前文件路径
        version: 要恢复的版本号
        content_type: 内容类型
    
    返回:
        (success, message)
    """
    if content_type is None:
        if "papers" in str(file_path):
            content_type = "paper"
        elif "entities" in str(file_path):
            content_type = "entity"
        elif "concepts" in str(file_path):
            content_type = "concept"
        else:
            content_type = "paper"
    
    # 先保存当前版本
    save_success, current_version, _ = save_version(file_path, f"恢复前自动保存", content_type)
    if not save_success:
        return False, "无法保存当前版本"
    
    # 获取要恢复的版本内容
    history_content = get_version_content(file_path, version, content_type)
    if not history_content:
        return False, f"找不到版本 {version}"
    
    # 写入当前文件
    file_path.write_text(history_content, encoding='utf-8')
    
    print(f"[VersionControl] 已恢复到版本 {version}")
    return True, f"已恢复到版本 {version}，当前版本已保存为版本 {current_version}"


def cleanup_old_versions(
    content_type: str = None,
    keep_count: int = 10
) -> int:
    """
    清理旧版本，只保留最近的 N 个版本
    
    参数:
        content_type: 内容类型，None 表示所有类型
        keep_count: 保留的版本数量
    
    返回:
        删除的文件数量
    """
    deleted_count = 0
    
    if content_type:
        dirs = [_get_history_dir(content_type)]
    else:
        dirs = [
            HISTORY_DIR / "papers",
            HISTORY_DIR / "entities",
            HISTORY_DIR / "concepts",
        ]
    
    for history_dir in dirs:
        if not history_dir.exists():
            continue
        
        # 按原始文件分组
        files_by_original = {}
        for f in history_dir.glob("*.md"):
            # 提取原始文件名（去掉版本号和时间戳）
            match = re.match(r'^(.+)_v\d+_\d+_\d+\.md$', f.name)
            if match:
                original = match.group(1)
                if original not in files_by_original:
                    files_by_original[original] = []
                files_by_original[original].append(f)
        
        # 对每个原始文件，只保留最近的 keep_count 个版本
        for original, files in files_by_original.items():
            if len(files) <= keep_count:
                continue
            
            # 按修改时间排序
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # 删除旧版本
            for f in files[keep_count:]:
                f.unlink()
                deleted_count += 1
                print(f"[VersionControl] 删除旧版本: {f.name}")
    
    return deleted_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="版本控制模块")
    parser.add_argument("--cleanup", action="store_true", help="清理旧版本")
    parser.add_argument("--keep", type=int, default=10, help="保留的版本数量")
    args = parser.parse_args()
    
    if args.cleanup:
        deleted = cleanup_old_versions(keep_count=args.keep)
        print(f"清理完成，删除 {deleted} 个旧版本文件")
    else:
        parser.print_help()
