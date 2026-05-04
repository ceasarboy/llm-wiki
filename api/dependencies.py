"""共享依赖：VaultIndex、辅助函数、全局状态"""

import re
import sys
import threading
import yaml
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from fastapi import HTTPException
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from config_loader import get_paths_config

PATHS = get_paths_config()
RAGTEST_DIR = Path(PATHS["work_dir"])
SCRIPTS_DIR = RAGTEST_DIR / "scripts"
VAULT_PATH = Path(PATHS["vault_root"])
WIKI_PATH = Path(PATHS["wiki_dir"])
RAW_DIR = Path(PATHS["raw_dir"])

HOT_QUERIES = [
    "什么是 RAG 中的多跳检索？",
    "Chiplet 技术的优势是什么？",
    "3D 集成的挑战有哪些？",
    "向量数据库如何优化？",
]


class VaultIndex:
    """Vault 文件索引，启动时构建"""

    def __init__(self):
        self.pages = {}
        self.by_type = {}
        self.last_scan = None
        self._lock = threading.RLock()
        self.scan()

    def scan(self):
        with self._lock:
            self._do_scan()

    def _do_scan(self):
        self.pages = {}
        self.by_type = {"paper": [], "entity": [], "concept": [], "survey": [], "comparison": []}

        type_map = {
            "papers": "paper",
            "entities": "entity",
            "concepts": "concept",
            "summaries": "synthesis",
            "syntheses": "synthesis",
        }

        for subdir, type_name in type_map.items():
            dir_path = WIKI_PATH / subdir
            if not dir_path.exists():
                continue

            for md_file in dir_path.glob("*.md"):
                page_id = f"{subdir}/{md_file.stem}"
                title = md_file.stem
                tags = []
                updated = datetime.fromtimestamp(
                    md_file.stat().st_mtime
                ).strftime("%Y-%m-%d")

                try:
                    file_content = md_file.read_text(encoding="utf-8")
                    if file_content.startswith("---"):
                        parts = file_content.split("---", 2)
                        if len(parts) >= 3:
                            fm = yaml.safe_load(parts[1]) or {}
                            title = fm.get("title", title)
                            raw_tags = fm.get("tags", [])
                            if isinstance(raw_tags, list):
                                tags = [str(t) for t in raw_tags]
                            elif raw_tags:
                                tags = [str(raw_tags)]
                except Exception:
                    pass

                effective_type = type_name
                if type_name == "synthesis":
                    if "comparison" in tags:
                        effective_type = "comparison"
                    else:
                        effective_type = "survey"

                page_info = {
                    "id": page_id,
                    "title": str(title),
                    "type": effective_type,
                    "tags": tags if isinstance(tags, list) else [tags],
                    "updated": updated,
                    "file_path": str(md_file),
                }

                self.pages[page_id] = page_info
                if effective_type in self.by_type:
                    self.by_type[effective_type].append(page_id)

        self.last_scan = datetime.now().isoformat()
        print(f"Vault 索引构建完成: {len(self.pages)} 个页面")


vault_index = VaultIndex()
background_tasks: Dict[str, dict] = {}


@contextmanager
def get_db_ctx():
    from api.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _cleanup_old_tasks():
    now = datetime.now()
    expired = [
        tid
        for tid, t in background_tasks.items()
        if t.get("status") in ("completed", "failed")
        and t.get("finished_at")
        and (now - datetime.fromisoformat(t["finished_at"])).total_seconds() > 3600
    ]
    for tid in expired:
        del background_tasks[tid]


def _safe_path(base: Path, id: str, suffix: str = ".md") -> Path:
    target = (base / f"{id}{suffix}").resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(
            status_code=403, detail="Access denied: path traversal detected"
        )
    return target


def _safe_filename(name: str) -> str:
    safe = re.sub(r"[^\w\-\u4e00-\u9fff.]", "_", name)
    if not safe or safe.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe
