"""LLM-Wiki Web API Service v3.1

对接真实数据源：Obsidian Vault 文件 + qmd_search 检索 + LLM 查询
"""

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import os
import re
import sys
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional
import yaml

# 项目路径 - 使用 config.yaml 统一配置
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from config_loader import get_paths_config

PATHS = get_paths_config()
RAGTEST_DIR = Path(PATHS["work_dir"])
SCRIPTS_DIR = RAGTEST_DIR / "scripts"
VAULT_PATH = Path(PATHS["vault_root"])
WIKI_PATH = Path(PATHS["wiki_dir"])
RAW_DIR = Path(PATHS["raw_dir"])

app = FastAPI(title="LLM-Wiki API", version="3.1")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 注册认证相关路由
from api.routers import auth_router, users_router, logs_router
from api.database import init_db, SessionLocal
from api.services.log_service import LogService
from api.database import get_db
from api.middleware.auth import require_role
from api.models import User

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(logs_router, prefix="/api")


@app.on_event("startup")
def startup_event():
    init_db()
    if WIKI_PATH.exists():
        app.mount("/wiki", StaticFiles(directory=str(WIKI_PATH)), name="wiki")
    dist_dir = Path(__file__).parent.parent / "web" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
    try:
        with get_db_ctx() as db:
            LogService.log_system_event(db, "INFO", "system", "startup", "LLM-Wiki 系统启动")
    except Exception:
        pass


# === 数据模型 ===

class QueryRequest(BaseModel):
    question: str


class SourceRef(BaseModel):
    id: str
    title: str
    path: str
    relevance: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceRef]
    related_questions: List[str]


class PageItem(BaseModel):
    id: str
    title: str
    type: str
    tags: List[str]
    updated: str
    summary: Optional[str] = None


class PageListResponse(BaseModel):
    items: List[PageItem]
    total: int


class PageDetail(BaseModel):
    id: str
    title: str
    type: str
    status: str
    content: str
    frontmatter: dict
    tags: List[str]
    updated: str


class SystemStatus(BaseModel):
    total_docs: int
    processed_docs: int
    pending_docs: int
    pass_rate: float
    avg_score: float
    review_queue: int
    last_check: str
    counts_by_type: dict


class HotQueriesResponse(BaseModel):
    queries: List[str]


class RecentUpdate(BaseModel):
    id: str
    title: str
    type: str
    updated: str


class RecentUpdatesResponse(BaseModel):
    items: List[RecentUpdate]


class VaultIndex:
    """Vault 文件索引，启动时构建"""
    
    def __init__(self):
        self.pages = {}
        self.by_type = {}
        self.last_scan = None
        self._lock = threading.RLock()
        self.scan()
    
    def scan(self):
        """扫描 Vault 目录"""
        with self._lock:
            self._do_scan()
    
    def _do_scan(self):
        self.pages = {}
        self.by_type = {"paper": [], "entity": [], "concept": [], "synthesis": []}
        
        type_map = {
            "papers": "paper",
            "entities": "entity",
            "concepts": "concept",
            "summaries": "synthesis",
            "syntheses": "synthesis"
        }
        
        for subdir, type_name in type_map.items():
            dir_path = WIKI_PATH / subdir
            if not dir_path.exists():
                continue
            
            for md_file in dir_path.glob("*.md"):
                page_id = f"{subdir}/{md_file.stem}"
                title = md_file.stem
                tags = []
                updated = datetime.fromtimestamp(md_file.stat().st_mtime).strftime("%Y-%m-%d")
                
                try:
                    file_content = md_file.read_text(encoding="utf-8")
                    if file_content.startswith("---"):
                        parts = file_content.split("---", 2)
                        if len(parts) >= 3:
                            fm = yaml.safe_load(parts[1]) or {}
                            title = fm.get("title", title)
                            raw_tags = fm.get("tags", [])
                            # 确保 tags 都是字符串
                            if isinstance(raw_tags, list):
                                tags = [str(t) for t in raw_tags]
                            elif raw_tags:
                                tags = [str(raw_tags)]
                except Exception:
                    pass
                
                page_info = {
                    "id": page_id,
                    "title": str(title),
                    "type": type_name,
                    "tags": tags if isinstance(tags, list) else [tags],
                    "updated": updated,
                    "file_path": str(md_file),
                }
                
                self.pages[page_id] = page_info
                if type_name in self.by_type:
                    self.by_type[type_name].append(page_id)
        
        self.last_scan = datetime.now().isoformat()
        print(f"Vault 索引构建完成: {len(self.pages)} 个页面")


@contextmanager
def get_db_ctx():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


vault_index = VaultIndex()

background_tasks: Dict[str, dict] = {}


def _cleanup_old_tasks():
    now = datetime.now()
    expired = [tid for tid, t in background_tasks.items()
               if t.get("status") in ("completed", "failed")
               and t.get("finished_at")
               and (now - datetime.fromisoformat(t["finished_at"])).total_seconds() > 3600]
    for tid in expired:
        del background_tasks[tid]


def _safe_path(base: Path, id: str, suffix: str = ".md") -> Path:
    target = (base / f"{id}{suffix}").resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
    return target


def _safe_filename(name: str) -> str:
    safe = re.sub(r'[^\w\-\u4e00-\u9fff.]', '_', name)
    if not safe or safe.startswith('.'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe


# === 热门查询 ===

HOT_QUERIES = [
    "什么是 RAG 中的多跳检索？",
    "Chiplet 技术的优势是什么？",
    "3D 集成的挑战有哪些？",
    "向量数据库如何优化？",
]


# === API 端点 ===

@app.get("/")
async def root():
    return {"message": "LLM-Wiki API v3.1", "docs": "/docs", "pages": len(vault_index.pages)}


@app.get("/api/status", response_model=SystemStatus)
async def get_status():
    """系统状态"""
    total = len(vault_index.pages)
    by_type = {k: len(v) for k, v in vault_index.by_type.items()}
    
    return SystemStatus(
        total_docs=total,
        processed_docs=by_type.get("paper", 0) + by_type.get("concept", 0) + by_type.get("entity", 0),
        pending_docs=0,
        pass_rate=95.0,
        avg_score=8.5,
        review_queue=0,
        last_check=vault_index.last_scan or datetime.now().isoformat(),
        counts_by_type=by_type,
    )


@app.post("/api/pages/rescan")
async def rescan_vault():
    """重新扫描 Vault 索引"""
    vault_index.scan()
    return {"success": True, "total_pages": len(vault_index.pages)}


@app.post("/api/health-check")
async def run_health_check(layer: str = "all"):
    """运行系统健康体检，layer: layer1=快速规则检查, layer2=深度检查, all=全部"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from scripts.lint import WikiLinter
    
    def _run_lint():
        linter = WikiLinter(str(VAULT_PATH))
        return linter.run_all_checks(layer=layer)
    
    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(ThreadPoolExecutor(1), _run_lint)
    
    return {
        "success": True,
        "report": report,
    }


@app.post("/api/fix/frontmatter/{id:path}")
async def fix_frontmatter(id: str, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """自动修复无效Frontmatter：从内容中提取title写入frontmatter"""
    page = vault_index.pages.get(id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    md_file = _safe_path(WIKI_PATH, id)
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    content = md_file.read_text(encoding="utf-8")
    
    extracted_title = None
    
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if title_match:
        extracted_title = title_match.group(1).strip()
    
    if not extracted_title:
        arxiv_match = re.search(r'\*\*arXiv ID\*\*:\s*(.+)', content)
        if arxiv_match:
            extracted_title = arxiv_match.group(1).strip()
    
    if not extracted_title:
        title_field_match = re.search(r'\*\*标题\*\*:\s*(.+)', content)
        if title_field_match:
            extracted_title = title_field_match.group(1).strip()
    
    if not extracted_title:
        h2_match = re.search(r'^##\s+(.+)$', content, re.MULTILINE)
        if h2_match:
            extracted_title = h2_match.group(1).strip()
    
    if not extracted_title:
        file_stem = md_file.stem
        extracted_title = file_stem.replace("_论文", "").replace("_", " ")
    
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                fm = {}
            fm["title"] = extracted_title
            new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
            new_content = f"---\n{new_fm}\n---{parts[2]}"
        else:
            raise HTTPException(status_code=400, detail="Cannot parse frontmatter")
    else:
        page_type = "paper" if "论文" in md_file.stem or "基本信息" in content else \
                    "entity" if md_file.parent.name == "entities" else \
                    "concept" if md_file.parent.name == "concepts" else "unknown"
        fm = {"title": extracted_title, "type": page_type}
        new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
        new_content = f"---\n{new_fm}\n---\n{content}"
    
    md_file.write_text(new_content, encoding="utf-8")
    vault_index.scan()
    
    return {"success": True, "message": f"已修复: title={extracted_title}"}


@app.post("/api/fix/regenerate-paper/{id:path}")
async def regenerate_paper(id: str, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """删除不完整论文及其关联实体/概念，后台从源文件重新生成"""
    _cleanup_old_tasks()
    page = vault_index.pages.get(id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    page_type = page.get("type", "")
    if page_type != "paper":
        raise HTTPException(status_code=400, detail="Not a paper page")
    
    md_file = _safe_path(WIKI_PATH, id)
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    content = md_file.read_text(encoding="utf-8")
    
    source_file_stem = None
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                fm = {}
            source_val = fm.get("source", "")
            if isinstance(source_val, list):
                for item in source_val:
                    item_str = str(item).strip("- []")
                    if item_str:
                        source_val = item_str
                        break
            source_str = str(source_val).strip("[]")
            source_match = re.search(r'raw/papers/markdown/(.+?)\.md', source_str)
            if source_match:
                source_file_stem = source_match.group(1)
    
    if not source_file_stem:
        source_match = re.search(r'source:\s*\[\[raw/papers/markdown/(.+?)\.md\]\]', content)
        if not source_match:
            source_match = re.search(r'raw/papers/markdown/(.+?)\.md', content)
        if source_match:
            source_file_stem = source_match.group(1)
    
    if not source_file_stem:
        source_file_stem = md_file.stem.replace("_论文", "")
    
    deleted_entities = []
    deleted_concepts = []
    
    entity_links = re.findall(r'\[\[entities/([^\]|]+)', content)
    for link in entity_links:
        entity_id = f"entities/{link}"
        entity_file = _safe_path(WIKI_PATH, entity_id)
        if entity_file.exists():
            entity_file.unlink()
            deleted_entities.append(entity_id)
    
    concept_links = re.findall(r'\[\[concepts/([^\]|]+)', content)
    for link in concept_links:
        concept_id = f"concepts/{link}"
        concept_file = _safe_path(WIKI_PATH, concept_id)
        if concept_file.exists():
            concept_file.unlink()
            deleted_concepts.append(concept_id)
    
    md_file.unlink()
    vault_index.scan()
    
    raw_file = RAW_DIR / f"{source_file_stem}.md"
    if not raw_file.exists():
        task_id = str(uuid.uuid4())[:8]
        background_tasks[task_id] = {
            "status": "failed",
            "message": f"论文和关联页面已删除，但源文件不存在: {source_file_stem}.md",
            "deleted_paper": id,
            "deleted_entities": deleted_entities,
            "deleted_concepts": deleted_concepts,
            "created_at": datetime.now().isoformat(),
            "finished_at": datetime.now().isoformat(),
        }
        return {
            "task_id": task_id,
            "status": "failed",
            "message": f"论文已删除，但源文件不存在: {source_file_stem}.md",
            "deleted_paper": id,
            "deleted_entities": deleted_entities,
            "deleted_concepts": deleted_concepts,
        }
    
    task_id = str(uuid.uuid4())[:8]
    background_tasks[task_id] = {
        "status": "running",
        "message": "正在重新生成论文...",
        "deleted_paper": id,
        "deleted_entities": deleted_entities,
        "deleted_concepts": deleted_concepts,
        "source_file": source_file_stem,
        "created_at": datetime.now().isoformat(),
    }
    
    def _run_regen():
        try:
            sys.path.insert(0, str(SCRIPTS_DIR))
            from batch import process_document, persist_to_wiki
            import shutil
            
            temp_dir = WIKI_PATH / "_regen_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                result = process_document(raw_file, temp_dir)
                
                if result.get("status") != "passed":
                    background_tasks[task_id].update({
                        "status": "failed",
                        "message": f"重新生成失败: {result.get('status', 'unknown')}",
                        "finished_at": datetime.now().isoformat(),
                    })
                    return
                
                persisted = []
                if result.get("paper"):
                    paper_path = Path(result["paper"])
                    dest = persist_to_wiki(paper_path, "paper", raw_file)
                    persisted.append(str(dest))
                
                for entity_path_str in result.get("entities", []):
                    entity_path = Path(entity_path_str)
                    dest = persist_to_wiki(entity_path, "entity")
                    persisted.append(str(dest))
                
                for concept_path_str in result.get("concepts", []):
                    concept_path = Path(concept_path_str)
                    dest = persist_to_wiki(concept_path, "concept")
                    persisted.append(str(dest))
                
                background_tasks[task_id].update({
                    "status": "completed",
                    "message": f"论文已重新生成 (源: {source_file_stem}.md)",
                    "regenerated_files": persisted,
                    "finished_at": datetime.now().isoformat(),
                })
            finally:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            background_tasks[task_id].update({
                "status": "failed",
                "message": f"重新生成异常: {str(e)}",
                "finished_at": datetime.now().isoformat(),
            })
        finally:
            vault_index.scan()
    
    thread = threading.Thread(target=_run_regen, daemon=True)
    thread.start()
    
    return {
        "task_id": task_id,
        "status": "running",
        "message": "论文已删除，正在后台重新生成...",
        "deleted_paper": id,
        "deleted_entities": deleted_entities,
        "deleted_concepts": deleted_concepts,
    }


@app.get("/api/fix/task-status/{task_id}")
async def get_task_status(task_id: str):
    """查询后台任务状态"""
    task = background_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/api/fix/broken-link/{id:path}")
async def fix_broken_link(id: str, body: dict, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """修复断裂链接：remove=删除链接, replace=替换链接"""
    action = body.get("action", "remove")
    broken_link = body.get("broken_link", "")
    replacement = body.get("replacement", "")
    
    md_file = _safe_path(WIKI_PATH, id)
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    content = md_file.read_text(encoding="utf-8")
    
    if action == "remove":
        new_content = re.sub(
            rf'-\s*\[\[{re.escape(broken_link)}(?:\|[^\]]+)?\]\]\s*\n?',
            '',
            content
        )
        new_content = re.sub(
            rf'\[\[{re.escape(broken_link)}(?:\|[^\]]+)?\]\]',
            '',
            new_content
        )
    elif action == "replace":
        if not replacement:
            raise HTTPException(status_code=400, detail="Replacement link required")
        new_content = content.replace(f"[[{broken_link}]]", f"[[{replacement}]]")
        display_match = re.search(r'\[\[([^\]|]+)\|([^\]]+)\]\]', content)
        if display_match:
            new_content = re.sub(
                rf'\[\[{re.escape(broken_link)}\|[^\]]+\]\]',
                f'[[{replacement}]]',
                new_content
            )
    else:
        raise HTTPException(status_code=400, detail="Invalid action: use 'remove' or 'replace'")
    
    md_file.write_text(new_content, encoding="utf-8")
    vault_index.scan()
    
    return {"success": True, "message": f"链接已{'删除' if action == 'remove' else '替换'}"}


@app.post("/api/fix/merge-entities")
async def merge_entities(body: dict, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """合并重复实体：保留keep_page，删除remove_page，更新所有引用"""
    keep_page = body.get("keep_page", "")
    remove_page = body.get("remove_page", "")
    
    if not keep_page or not remove_page:
        raise HTTPException(status_code=400, detail="keep_page and remove_page required")
    
    keep_file = WIKI_PATH / f"{keep_page}.md"
    remove_file = WIKI_PATH / f"{remove_page}.md"
    
    if not keep_file.exists():
        raise HTTPException(status_code=404, detail=f"Keep page not found: {keep_page}")
    if not remove_file.exists():
        raise HTTPException(status_code=404, detail=f"Remove page not found: {remove_page}")
    
    remove_content = remove_file.read_text(encoding="utf-8")
    keep_content = keep_file.read_text(encoding="utf-8")
    
    if keep_content.startswith("---"):
        parts = keep_content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                fm = {}
            body_start = parts[2]
        else:
            fm = {}
            body_start = keep_content
    else:
        fm = {}
        body_start = keep_content
    
    if remove_content.startswith("---"):
        r_parts = remove_content.split("---", 2)
        if len(r_parts) >= 3:
            remove_body = r_parts[2]
        else:
            remove_body = remove_content
    else:
        remove_body = remove_content
    
    merged_body = body_start.rstrip() + "\n\n## 合并自: " + remove_page + "\n" + remove_body.lstrip()
    merged_content = f"---\n{yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()}\n---\n{merged_body}"
    
    keep_file.write_text(merged_content, encoding="utf-8")
    remove_file.unlink()
    
    updated_refs = 0
    for md_file in WIKI_PATH.rglob("*.md"):
        if md_file == keep_file:
            continue
        try:
            file_content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        
        new_file_content = file_content.replace(f"[[{remove_page}]]", f"[[{keep_page}]]")
        new_file_content = re.sub(
            rf'\[\[{re.escape(remove_page)}\|[^\]]+\]\]',
            f'[[{keep_page}]]',
            new_file_content
        )
        
        if new_file_content != file_content:
            md_file.write_text(new_file_content, encoding="utf-8")
            updated_refs += 1
    
    vault_index.scan()
    
    return {
        "success": True,
        "message": f"已合并: 保留 {keep_page}，删除 {remove_page}，更新了 {updated_refs} 个引用",
        "updated_refs": updated_refs,
    }


@app.post("/api/refresh")
async def refresh_index():
    """刷新索引"""
    vault_index.scan()
    return {"message": "索引已刷新", "total_pages": len(vault_index.pages)}


@app.get("/api/pages", response_model=PageListResponse)
async def get_pages(type: Optional[str] = None, page: int = 1, page_size: int = 20):
    """获取页面列表"""
    results = []
    
    if type and type in vault_index.by_type:
        page_ids = vault_index.by_type[type]
    else:
        page_ids = list(vault_index.pages.keys())
    
    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    
    for pid in page_ids[start:end]:
        p = vault_index.pages[pid]
        results.append(PageItem(
            id=pid,
            title=p["title"],
            type=p["type"],
            tags=p["tags"],
            updated=p["updated"],
        ))
    
    return PageListResponse(items=results, total=len(page_ids))


@app.get("/api/pages/{id:path}", response_model=PageDetail)
async def get_page_detail(id: str):
    """获取页面详情"""
    file_path = None
    
    # 直接路径
    if id in vault_index.pages:
        file_path = Path(vault_index.pages[id]["file_path"])
    else:
        # 尝试子目录匹配，支持多种文件名格式
        type_suffixes = {
            "papers": "_论文",
            "entities": "",
            "concepts": "",
            "summaries": "",
            "syntheses": "_综合",
        }
        for subdir, suffix in type_suffixes.items():
            # 尝试多种格式
            for pattern in [f"{id}{suffix}.md", f"{id}.md"]:
                test_path = WIKI_PATH / subdir / pattern
                if test_path.exists():
                    file_path = test_path
                    break
            if file_path:
                break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    content = file_path.read_text(encoding="utf-8")
    frontmatter = {}
    
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass
            content = parts[2].strip()
    
    # 安全提取 frontmatter 字段（YAML 可能把数字解析为 float，日期解析为 date）
    raw_tags = frontmatter.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = [raw_tags] if raw_tags else []
    safe_tags = [str(t) for t in raw_tags]

    raw_updated = frontmatter.get("updated", datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d"))
    safe_updated = str(raw_updated)

    return PageDetail(
        id=id,
        title=str(frontmatter.get("title", file_path.stem)),
        type=str(frontmatter.get("type", "unknown")),
        status=str(frontmatter.get("status", "stable")),
        content=content,
        frontmatter=frontmatter,
        tags=safe_tags,
        updated=safe_updated,
    )


class PageUpdateRequest(BaseModel):
    content: str

@app.put("/api/pages/{id:path}")
async def update_page(id: str, update: PageUpdateRequest, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """更新页面内容"""
    file_path = None
    
    if id in vault_index.pages:
        file_path = Path(vault_index.pages[id]["file_path"])
    else:
        type_suffixes = {
            "papers": "_论文",
            "entities": "",
            "concepts": "",
            "summaries": "",
            "syntheses": "_综合",
        }
        for subdir, suffix in type_suffixes.items():
            for pattern in [f"{id}{suffix}.md", f"{id}.md"]:
                test_path = WIKI_PATH / subdir / pattern
                if test_path.exists():
                    file_path = test_path
                    break
            if file_path:
                break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    file_path.write_text(update.content, encoding='utf-8')
    
    vault_index.scan()
    
    return {"success": True, "message": "页面已保存"}


class ManualReviewRequest(BaseModel):
    action: str  # "approve" | "reject"
    comment: str = ""
    reviewer: str = ""

class ManualReviewResponse(BaseModel):
    success: bool
    message: str
    new_status: str

@app.post("/api/pages/{id:path}/manual-review", response_model=ManualReviewResponse)
async def set_manual_review(id: str, request: ManualReviewRequest, current_user: User = Depends(require_role(["admin", "maintainer", "core"]))):
    """
    人工审核页面
    - approve: 审核通过，状态改为 reviewed
    - reject: 审核不通过，状态改为 pending
    """
    from version_control import save_version
    
    file_path = None
    
    if id in vault_index.pages:
        file_path = Path(vault_index.pages[id]["file_path"])
    else:
        type_suffixes = {
            "papers": "_论文",
            "entities": "",
            "concepts": "",
            "summaries": "",
        }
        for subdir, suffix in type_suffixes.items():
            for pattern in [f"{id}{suffix}.md", f"{id}.md"]:
                test_path = WIKI_PATH / subdir / pattern
                if test_path.exists():
                    file_path = test_path
                    break
            if file_path:
                break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    content = file_path.read_text(encoding='utf-8')
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2]
            except Exception:
                frontmatter = {}
                body = parts[2]
        else:
            frontmatter = {}
            body = content
    else:
        frontmatter = {}
        body = content
    
    # 保存版本
    try:
        save_version(file_path, f"人工审核: {request.action}")
    except Exception as e:
        print(f"保存版本失败: {e}")
    
    # 更新状态
    status_map = {
        "approve": "reviewed",
        "reject": "pending"
    }
    new_status = status_map.get(request.action, "generated")
    
    frontmatter["status"] = new_status
    frontmatter["reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frontmatter["reviewer"] = request.reviewer
    if request.comment:
        frontmatter["review_comment"] = request.comment
    
    # 重新构建文件内容
    new_content = "---\n" + yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False) + "---\n\n" + body.strip()
    file_path.write_text(new_content, encoding='utf-8')
    
    vault_index.scan()
    
    return ManualReviewResponse(
        success=True,
        message=f"审核完成，状态已更新为 {new_status}",
        new_status=new_status
    )


class RecheckRequest(BaseModel):
    reason: str = ""

@app.post("/api/pages/{id:path}/recheck")
async def recheck_page(id: str, request: RecheckRequest = RecheckRequest(), current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """复审页面：重新生成wiki内容"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    
    file_path = None
    
    if id in vault_index.pages:
        file_path = Path(vault_index.pages[id]["file_path"])
    else:
        for subdir in ["papers", "entities", "concepts", "summaries"]:
            for pattern in [f"{id}.md", f"{id}_论文.md"]:
                test_path = WIKI_PATH / subdir / pattern
                if test_path.exists():
                    file_path = test_path
                    break
            if file_path:
                break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    # 读取frontmatter
    content = file_path.read_text(encoding='utf-8')
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                frontmatter = {}
        else:
            frontmatter = {}
    else:
        frontmatter = {}
    
    # 检查是否有source和review_comment
    source = frontmatter.get('source')
    review_comment = frontmatter.get('review_comment')
    
    if not source:
        raise HTTPException(status_code=400, detail="页面缺少source信息")
    
    if not review_comment:
        raise HTTPException(status_code=400, detail="页面缺少审核意见")
    
    # 解析source路径
    if isinstance(source, list):
        source_path = source[0]
    else:
        source_path = source
    
    # 去掉 [[]] 标记
    source_path = source_path.strip('[]')
    
    # 构建完整路径
    full_source_path = VAULT_PATH / source_path
    
    if not full_source_path.exists():
        raise HTTPException(status_code=404, detail=f"原始文档不存在: {source_path}")
    
    # 执行复审
    try:
        from recheck import recheck_page as do_recheck
        success, wiki_path, error = do_recheck(
            str(full_source_path),
            review_comment,
            str(file_path.parent)
        )
        
        if success:
            vault_index.scan()
            try:
                with get_db_ctx() as db:
                    LogService.log_system_event(db, "INFO", "review", "recheck", f"复审成功: {id}")
            except Exception:
                pass
            return {
                "success": True,
                "message": "复审成功",
                "wiki_path": wiki_path
            }
        else:
            try:
                with get_db_ctx() as db:
                    LogService.log_system_event(db, "WARNING", "review", "recheck_failed", f"复审失败: {id}", details=str(error))
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        try:
            with get_db_ctx() as db:
                LogService.log_system_event(db, "ERROR", "review", "recheck_error", f"复审异常: {id}", details=str(e))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"复审失败: {str(e)}")


# === 历史版本 API ===

HISTORY_DIR = WIKI_PATH / "history"

class HistoryVersion(BaseModel):
    version: int
    filename: str
    path: str
    saved_at: str
    save_reason: str
    size: int

class HistoryListResponse(BaseModel):
    items: List[HistoryVersion]
    total: int

class HistoryDetailResponse(BaseModel):
    version: int
    filename: str
    content: str
    saved_at: str
    save_reason: str
    frontmatter: Dict[str, Any]

@app.get("/api/pages/{page_id:path}/history", response_model=HistoryListResponse)
async def get_page_history(page_id: str):
    """获取页面的历史版本列表"""
    # 找到页面文件
    file_path = None
    for subdir in ["papers", "entities", "concepts", "summaries", "syntheses"]:
        for pattern in [f"{page_id}.md", f"{page_id}_论文.md"]:
            test_path = WIKI_PATH / subdir / pattern
            if test_path.exists():
                file_path = test_path
                break
        if file_path:
            break
    
    if not file_path:
        try:
            file_path = _safe_path(WIKI_PATH, page_id)
        except HTTPException:
            file_path = None
        if not file_path or not file_path.exists():
            try:
                file_path = _safe_path(WIKI_PATH, page_id, "")
            except HTTPException:
                file_path = None
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    # 查找历史版本
    history_items = []
    
    if HISTORY_DIR.exists():
        # 获取相对路径
        try:
            relative = file_path.relative_to(WIKI_PATH)
            history_subdir = HISTORY_DIR / relative.parent
            stem = file_path.stem
            
            if history_subdir.exists():
                for f in sorted(history_subdir.glob(f"{stem}_v*.md"), reverse=True):
                    # 解析版本号
                    import re
                    match = re.search(r'_v(\d+)\.md$', f.name)
                    if match:
                        version = int(match.group(1))
                        content = f.read_text(encoding='utf-8')
                        
                        # 解析 frontmatter
                        saved_at = ""
                        save_reason = ""
                        if content.startswith('---'):
                            parts = content.split('---', 2)
                            if len(parts) >= 3:
                                try:
                                    import yaml
                                    fm = yaml.safe_load(parts[1])
                                    saved_at = fm.get('saved_at', '')
                                    save_reason = fm.get('save_reason', '')
                                except Exception:
                                    pass
                        
                        history_items.append(HistoryVersion(
                            version=version,
                            filename=f.name,
                            path=str(f.relative_to(WIKI_PATH)),
                            saved_at=saved_at,
                            save_reason=save_reason,
                            size=f.stat().st_size,
                        ))
        except ValueError:
            pass
    
    return HistoryListResponse(items=history_items, total=len(history_items))

@app.get("/api/pages/{page_id:path}/history/{version:int}", response_model=HistoryDetailResponse)
async def get_history_version(page_id: str, version: int):
    """获取特定历史版本的内容"""
    # 找到页面文件
    file_path = None
    for subdir in ["papers", "entities", "concepts", "summaries", "syntheses"]:
        for pattern in [f"{page_id}.md", f"{page_id}_论文.md"]:
            test_path = WIKI_PATH / subdir / pattern
            if test_path.exists():
                file_path = test_path
                break
        if file_path:
            break
    
    if not file_path:
        try:
            file_path = _safe_path(WIKI_PATH, page_id)
        except HTTPException:
            file_path = None
        if not file_path or not file_path.exists():
            try:
                file_path = _safe_path(WIKI_PATH, page_id, "")
            except HTTPException:
                file_path = None
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    # 查找历史版本文件
    try:
        relative = file_path.relative_to(WIKI_PATH)
        history_subdir = HISTORY_DIR / relative.parent
        stem = file_path.stem
        history_file = history_subdir / f"{stem}_v{version}.md"
        
        if not history_file.exists():
            raise HTTPException(status_code=404, detail="History version not found")
        
        content = history_file.read_text(encoding='utf-8')
        
        # 解析 frontmatter
        frontmatter = {}
        saved_at = ""
        save_reason = ""
        body = content
        
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    saved_at = frontmatter.get('saved_at', '')
                    save_reason = frontmatter.get('save_reason', '')
                    body = parts[2].strip()
                except Exception:
                    pass
        
        return HistoryDetailResponse(
            version=version,
            filename=history_file.name,
            content=body,
            saved_at=saved_at,
            save_reason=save_reason,
            frontmatter=frontmatter,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="History version not found")


# === 原文 API ===

class RawDocument(BaseModel):
    id: str
    title: str
    path: str
    size: int
    updated: str

class RawDocumentListResponse(BaseModel):
    items: List[RawDocument]
    total: int

class RawDocumentDetail(BaseModel):
    id: str
    title: str
    path: str
    content: str
    size: int
    updated: str

@app.get("/api/raw", response_model=RawDocumentListResponse)
async def list_raw_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
):
    """获取原文列表"""
    raw_path = RAW_DIR
    if not raw_path.exists():
        return RawDocumentListResponse(items=[], total=0)
    
    items = []
    for md_file in raw_path.glob("*.md"):
        stat = md_file.stat()
        title = md_file.stem
        
        # 搜索过滤
        if search and search.lower() not in title.lower():
            continue
        
        items.append(RawDocument(
            id=md_file.stem,
            title=title,
            path=str(md_file),
            size=stat.st_size,
            updated=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        ))
    
    # 按更新时间排序
    items.sort(key=lambda x: x.updated, reverse=True)
    
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    
    return RawDocumentListResponse(items=items[start:end], total=total)

@app.get("/api/raw/{id}", response_model=RawDocumentDetail)
async def get_raw_document(id: str):
    """获取原文详情"""
    raw_path = RAW_DIR
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="Raw directory not found")
    
    # 尝试匹配文件
    md_file = raw_path / f"{id}.md"
    if not md_file.exists():
        # 尝试 URL 解码
        from urllib.parse import unquote
        decoded_id = unquote(id)
        md_file = raw_path / f"{decoded_id}.md"
    
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    content = md_file.read_text(encoding="utf-8")
    stat = md_file.stat()
    
    return RawDocumentDetail(
        id=md_file.stem,
        title=md_file.stem,
        path=str(md_file),
        content=content,
        size=stat.st_size,
        updated=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
    )


@app.put("/api/raw/{id}")
async def update_raw_document(id: str, body: dict, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    content = body.get("content", "")
    new_filename = body.get("filename")
    
    from urllib.parse import unquote
    decoded_id = unquote(id)
    
    try:
        md_file = _safe_path(RAW_DIR, decoded_id)
    except HTTPException:
        md_file = None
    if not md_file or not md_file.exists():
        try:
            md_file = _safe_path(RAW_DIR, id)
        except HTTPException:
            md_file = None
    if not md_file or not md_file.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    if new_filename and new_filename != md_file.stem:
        new_filename = new_filename.strip()
        if not new_filename or '/' in new_filename or '\\' in new_filename or '.' in new_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        new_path = RAW_DIR / f"{new_filename}.md"
        if new_path.exists() and new_path != md_file:
            raise HTTPException(status_code=400, detail="File already exists")
        try:
            md_file.rename(new_path)
            md_file = new_path
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Rename failed: {str(e)}")
    
    try:
        md_file.write_text(content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")
    
    return {"success": True, "message": "保存成功", "new_id": md_file.stem}


@app.get("/api/raw/{id}/pdf")
async def get_raw_pdf(id: str):
    from urllib.parse import unquote
    decoded_id = unquote(id)
    
    pdf_dir = VAULT_PATH / "raw" / "papers" / "pdf"
    if not pdf_dir.exists():
        raise HTTPException(status_code=404, detail="PDF directory not found")
    
    pdf_file = pdf_dir / f"{decoded_id}.pdf"
    if not pdf_file.exists():
        pdf_file = pdf_dir / f"{id}.pdf"
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    return FileResponse(pdf_file, media_type="application/pdf")


@app.get("/api/assets")
async def get_asset(path: str):
    """获取静态资源文件（图片等）"""
    from urllib.parse import unquote
    
    # 解码路径
    decoded_path = unquote(path)
    if os.path.isabs(decoded_path) or '..' in decoded_path:
        raise HTTPException(status_code=403, detail="Absolute paths and parent references not allowed")
    
    # 安全检查：确保路径在允许的目录内
    allowed_dirs = [
        VAULT_PATH / "assets",
        VAULT_PATH / "raw",
    ]
    
    asset_path = Path(decoded_path)
    
    # 检查路径是否在允许的目录内
    is_allowed = False
    for allowed_dir in allowed_dirs:
        try:
            asset_path.resolve().relative_to(allowed_dir.resolve())
            is_allowed = True
            break
        except ValueError:
            continue
    
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # 根据扩展名设置 content type
    suffix = asset_path.suffix.lower()
    content_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
    }
    content_type = content_types.get(suffix, 'application/octet-stream')
    
    return FileResponse(asset_path, media_type=content_type)


class PDFListResponse(BaseModel):
    items: List[dict]
    total: int


@app.get("/api/pdfs", response_model=PDFListResponse)
async def list_pdfs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), search: str = ""):
    """获取PDF文件列表"""
    pdf_dir = VAULT_PATH / "raw" / "papers" / "pdf"
    if not pdf_dir.exists():
        return PDFListResponse(items=[], total=0)
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    items = []
    
    search_lower = search.lower() if search else ""
    
    for pdf_file in pdf_files:
        title = pdf_file.stem
        if search_lower and search_lower not in title.lower():
            continue
        
        stat = pdf_file.stat()
        items.append({
            "id": pdf_file.stem,
            "title": title,
            "path": str(pdf_file),
            "size": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "updated": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    
    items.sort(key=lambda x: x["updated"], reverse=True)
    
    total = len(items)
    start = (page - 1) * page_size
    items = items[start:start + page_size]
    
    return PDFListResponse(items=items, total=total)


@app.get("/api/pdfs/{pdf_id}")
async def get_pdf(pdf_id: str):
    """获取PDF文件"""
    pdf_dir = VAULT_PATH / "raw" / "papers" / "pdf"
    pdf_file = pdf_dir / f"{pdf_id}.pdf"
    
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    return FileResponse(pdf_file, media_type="application/pdf")


@app.get("/api/search")
async def search(q: str = "", type: Optional[str] = None):
    """知识库搜索"""
    results = []
    query_lower = q.lower() if q else ""
    
    for pid, p in vault_index.pages.items():
        if type and p["type"] != type:
            continue
        if query_lower and query_lower not in p["title"].lower() and query_lower not in " ".join(p["tags"]).lower():
            continue
        results.append({
            "id": pid,
            "title": p["title"],
            "type": p["type"],
            "tags": p["tags"],
            "updated": p["updated"],
        })
    
    return {"results": results[:20]}


def call_llm_for_query(question: str, contexts: list) -> str:
    """调用 LLM 生成答案"""
    import requests
    
    # 构建 context
    context_text = "\n\n---\n\n".join([f"【文档{i+1}】{c[:1500]}" for i, c in enumerate(contexts[:15])])
    
    prompt = f"""你是一个知识库问答助手。基于以下检索到的文档内容回答用户问题。

要求：
1. 答案要具体、准确，直接回答问题
2. 如果问题涉及列举或统计（如"有几种"、"有哪些"），请尽可能完整地列出所有检索到的相关内容
3. 如果文档内容不足以完整回答，说明已列出的部分并提示可能还有未覆盖的内容
4. 用简洁的中文回答

---
检索到的文档：
{context_text}
---

用户问题：{question}

请回答："""

    try:
        # 从 config.yaml 读取 LLM 配置
        config_path = RAGTEST_DIR / "config.yaml"
        if config_path.exists():
            import yaml as yaml_loader
            config = yaml_loader.safe_load(config_path.read_text(encoding="utf-8"))
            llm_config = config.get("llm", {})
            api_url = llm_config.get("api_url", "http://127.0.0.1:28789/v1/chat/completions")
            api_key = llm_config.get("api_key", "")
            model = llm_config.get("model", "Pro/moonshotai/Kimi-K2.5")
        else:
            api_url = "http://127.0.0.1:28789/v1/chat/completions"
            api_key = ""
            model = "Pro/moonshotai/Kimi-K2.5"
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500,
        }
        
        resp = requests.post(api_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"基于检索结果的答案生成失败: {str(e)}\n\n请参考以下文档片段：\n{contexts[0][:300] if contexts else '无'}..."


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """自然语言查询（调用 qmd_search + LLM）"""
    try:
        from qmd_search_simple import hybrid_search
        search_results = hybrid_search(request.question, top_k=30)
        
        query_lower = request.question.lower()
        query_keywords = set(re.findall(r'[a-zA-Z]+', query_lower))
        cn_segments = re.findall(r'[\u4e00-\u9fff]+', query_lower)
        stop_words = {'有几种', '有哪些', '是什么', '什么是', '如何', '怎么', '为什么', '哪些', '几种', '什么', '如何', '可以', '能够', '之间', '关系', '区别', '联系', '还有', '其他', '关于', '对于', '以及', '或者', '但是', '而且', '因为', '所以', '如果', '那么', '虽然', '不过', '只是', '已经', '正在', '将要', '应该', '需要', '可能', '必须', '一定', '这个', '那个', '这些', '那些', '每个', '所有', '一些', '很多', '非常', '比较', '更加', '最', '很', '都', '也', '还', '又', '再', '才', '就', '却', '而', '且', '与', '及', '或', '的', '了', '在', '是', '我', '你', '他', '她', '它', '们', '这', '那', '一', '个', '不', '没', '会', '能', '要', '说', '去', '做', '看', '想', '给', '让', '被', '把', '从', '到', '对', '向', '为', '以', '用', '按', '经', '过', '将', '于', '比', '同', '跟', '和', '及'}
        for seg in cn_segments:
            query_keywords.add(seg)
            for i in range(len(seg)):
                for j in range(i + 2, min(len(seg) + 1, i + 5)):
                    sub = seg[i:j]
                    if sub not in stop_words and len(sub) >= 2:
                        query_keywords.add(sub)
        
        if query_keywords:
            existing_ids = {r["id"] for r in search_results}
            core_keywords = [kw for kw in query_keywords if len(kw) >= 2 and kw not in stop_words]
            for page_id, page_info in vault_index.pages.items():
                if page_id in existing_ids:
                    continue
                title = page_info.get("title", "").lower()
                matched = False
                for kw in core_keywords:
                    if kw in title:
                        matched = True
                        break
                if not matched:
                    continue
                try:
                    md_file = _safe_path(WIKI_PATH, page_id)
                except HTTPException:
                    continue
                if md_file.exists():
                    content = md_file.read_text(encoding="utf-8")
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            content = parts[2]
                    search_results.append({
                        "id": page_id,
                        "content": content[:2000],
                        "metadata": {
                            "page_name": page_id,
                            "title": page_info.get("title", ""),
                            "type": page_info.get("type", ""),
                        },
                        "final_score": 0.6,
                        "vector_score": 0,
                        "keyword_score": 0,
                    })
                    existing_ids.add(page_id)
        
        search_results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        search_results = search_results[:20]
        
        sources = []
        contexts = []
        for r in search_results:
            metadata = r.get("metadata", {})
            sources.append(SourceRef(
                id=metadata.get("page_name", r["id"]),
                title=metadata.get("title", r["id"]),
                path=f"wiki/{r['id']}",
                relevance=r.get("final_score", 0.5),
            ))
            contexts.append(r.get("content", ""))
        
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(None, call_llm_for_query, request.question, contexts)
        
        return QueryResponse(
            answer=answer,
            sources=sources,
            related_questions=HOT_QUERIES[:3],
        )
    except Exception as e:
        return QueryResponse(
            answer=f"搜索功能暂时不可用: {str(e)}",
            sources=[],
            related_questions=HOT_QUERIES[:3],
        )


@app.get("/api/hot-queries", response_model=HotQueriesResponse)
async def get_hot_queries():
    """热门查询"""
    return HotQueriesResponse(queries=HOT_QUERIES)


@app.get("/api/recent-updates", response_model=RecentUpdatesResponse)
async def get_recent_updates(limit: int = 5):
    """最近更新"""
    sorted_pages = sorted(vault_index.pages.values(), key=lambda x: x["updated"], reverse=True)
    
    items = []
    for p in sorted_pages[:limit]:
        items.append(RecentUpdate(
            id=p["id"],
            title=p["title"],
            type=p["type"],
            updated=p["updated"],
        ))
    
    return RecentUpdatesResponse(items=items)


# === PDF管理 API ===

from fastapi import UploadFile, File
from api.database import PDFFile, MarkdownFile
from sqlalchemy.orm import Session
from api.database import get_db
from scripts.pdf_converter import convert_pdf_to_markdown

PDF_DIR = VAULT_PATH / "raw" / "papers" / "pdf"
MD_DIR = VAULT_PATH / "raw" / "papers" / "markdown"

@app.post("/api/pdf/upload")
async def upload_pdf(file: UploadFile = File(...), current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """上传PDF文件"""
    if not file.filename or not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="只支持PDF文件")
    
    # 确保目录存在
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    
    pdf_path = PDF_DIR / _safe_filename(file.filename)
    
    # 保存文件
    with open(pdf_path, "wb") as buffer:
        import shutil
        shutil.copyfileobj(file.file, buffer)
    
    try:
        with get_db_ctx() as db:
            LogService.log_system_event(db, "INFO", "pdf", "upload", f"上传PDF文件: {file.filename}")
            pdf_file = PDFFile(
                filename=file.filename,
                path=str(pdf_path),
                size=pdf_path.stat().st_size,
                status="pending"
            )
            db.add(pdf_file)
            db.commit()
            db.refresh(pdf_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库保存失败: {str(e)}")
    
    return {
        "success": True,
        "message": "上传成功",
        "file": {
            "filename": file.filename,
            "path": str(pdf_path),
            "size": pdf_path.stat().st_size,
            "uploaded_at": datetime.now().isoformat()
        }
    }


@app.get("/api/pdf/list")
async def list_pdfs(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None
):
    """获取PDF文件列表"""
    with get_db_ctx() as db:
        query = db.query(PDFFile)
        
        if status:
            query = query.filter(PDFFile.status == status)
        
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        
        return {
            "items": [
                {
                    "filename": item.filename,
                    "path": item.path,
                    "size": item.size,
                    "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
                    "status": item.status,
                    "markdown_path": item.markdown_path
                }
                for item in items
            ],
            "total": total
        }


@app.post("/api/pdf/convert")
async def convert_pdf(filename: str, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """转换PDF为Markdown"""
    with get_db_ctx() as db:
        pdf_file = db.query(PDFFile).filter(PDFFile.filename == filename).first()
        
        if not pdf_file:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        if pdf_file.status == "converting":
            raise HTTPException(status_code=400, detail="文件正在转换中")
        
        pdf_file.status = "converting"
        db.commit()
        
        try:
            pdf_path = Path(pdf_file.path)
            MD_DIR.mkdir(parents=True, exist_ok=True)
            
            success, markdown_path, error = convert_pdf_to_markdown(pdf_path, MD_DIR)
            
            if success:
                pdf_file.status = "completed"
                pdf_file.markdown_path = markdown_path
                pdf_file.converted_at = datetime.now(timezone.utc)
                db.commit()
                LogService.log_system_event(db, "INFO", "pdf", "convert", f"PDF转换成功: {filename}")
                return {
                    "success": True,
                    "message": "转换成功",
                    "markdown_path": markdown_path
                }
            else:
                pdf_file.status = "failed"
                pdf_file.error_message = error
                db.commit()
                LogService.log_system_event(db, "ERROR", "pdf", "convert", f"PDF转换失败: {filename}", details=error)
                
                raise HTTPException(status_code=500, detail=error or "转换失败")
                
        except HTTPException:
            raise
        except Exception as e:
            pdf_file.status = "failed"
            pdf_file.error_message = str(e)
            db.commit()
            
            raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/pdf/{filename}")
async def delete_pdf(filename: str, current_user: User = Depends(require_role(["admin"]))):
    """删除PDF文件"""
    with get_db_ctx() as db:
        pdf_file = db.query(PDFFile).filter(PDFFile.filename == filename).first()
        
        if not pdf_file:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        pdf_path = Path(pdf_file.path)
        if pdf_path.exists():
            pdf_path.unlink()
        
        if pdf_file.markdown_path:
            md_path = Path(pdf_file.markdown_path)
            if md_path.exists():
                md_path.unlink()
        
        db.delete(pdf_file)
        db.commit()
        
        return {"success": True, "message": "删除成功"}


# === 论文导入 API ===
LOG_FILE = RAGTEST_DIR / "log.md"

class PendingDoc(BaseModel):
    filename: str
    path: str
    size: int
    modified: str

class PendingDocsResponse(BaseModel):
    count: int
    items: List[PendingDoc]

class IngestResult(BaseModel):
    success: bool
    message: str
    processed: int

def get_processed_docs() -> set:
    """从 log.md 和 wiki 目录读取已处理的文档列表"""
    processed = set()
    
    # 1. 从 log.md 读取
    if LOG_FILE.exists():
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        import re
        # 旧格式：原始文档: raw/papers/markdown/xxx.md
        pattern1 = r'原始文档:\s*([^\n]+)'
        matches = re.findall(pattern1, content)
        for match in matches:
            processed.add(match.strip())
        
        # 新格式：| 原始文档: raw/papers/markdown/xxx.md
        pattern2 = r'\|\s*原始文档:\s*(raw/papers/markdown/[^\n]+)'
        matches2 = re.findall(pattern2, content)
        for match in matches2:
            processed.add(match.strip())
    
    # 2. 从 wiki/papers 目录检查已存在的论文
    wiki_papers_dir = VAULT_PATH / "wiki" / "papers"
    if wiki_papers_dir.exists():
        for paper_file in wiki_papers_dir.glob("*_论文.md"):
            stem = paper_file.stem.replace("_论文", "")
            processed.add(f"raw/papers/markdown/{stem}.md")
    
    return processed


@app.get("/api/ingest/pending", response_model=PendingDocsResponse)
async def get_pending_docs():
    """获取待处理的文档列表"""
    if not RAW_DIR.exists():
        raise HTTPException(status_code=404, detail="Raw directory not found")
    
    all_docs = list(RAW_DIR.glob("*.md"))
    processed = get_processed_docs()
    
    pending = []
    for doc in all_docs:
        rel_path = f"raw/papers/markdown/{doc.name}"
        if rel_path not in processed and doc.name not in processed:
            stat = doc.stat()
            pending.append(PendingDoc(
                filename=doc.name,
                path=str(doc),
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            ))
    
    return PendingDocsResponse(count=len(pending), items=pending)


@app.post("/api/ingest/run", response_model=IngestResult)
async def run_ingest(limit: int = 10, current_user: User = Depends(require_role(["admin", "maintainer"]))):
    """运行论文导入流程 - 调用 batch.py 执行完整流程（生成+审核+写入）"""
    import subprocess
    
    # 清空日志文件
    log_file = RAGTEST_DIR / "ingest.log"
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"开始导入 {limit} 篇论文...\n")
    
    try:
        with get_db_ctx() as db:
            LogService.log_system_event(db, "INFO", "ingest", "start", f"开始导入 {limit} 篇论文")
        process = subprocess.Popen(
            [sys.executable, str(SCRIPTS_DIR / "batch.py"), "--batch-size", str(limit), "--max-batches", "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(RAGTEST_DIR),
        )
        
        # 实时写入日志
        with open(log_file, 'a', encoding='utf-8') as f:
            for line in process.stdout:
                f.write(line)
                f.flush()
        
        process.wait(timeout=600)
        
        if process.returncode != 0:
            try:
                with get_db_ctx() as db:
                    LogService.log_system_event(db, "ERROR", "ingest", "failed", "导入失败，请查看日志")
            except Exception:
                pass
            return IngestResult(
                success=False,
                message=f"导入失败，请查看日志",
                processed=0,
            )
        
        vault_index.scan()
        
        try:
            with get_db_ctx() as db:
                LogService.log_system_event(db, "INFO", "ingest", "complete", f"导入完成，处理 {limit} 篇论文")
        except Exception:
            pass
        
        return IngestResult(
            success=True,
            message=f"导入完成",
            processed=limit,
        )
    except subprocess.TimeoutExpired:
        return IngestResult(
            success=False,
            message="导入超时（超过10分钟）",
            processed=0,
        )
    except Exception as e:
        return IngestResult(
            success=False,
            message=f"导入出错: {str(e)}",
            processed=0,
        )


class IngestLogResponse(BaseModel):
    log: str
    finished: bool

@app.get("/api/ingest/log", response_model=IngestLogResponse)
async def get_ingest_log():
    """获取导入日志"""
    log_file = RAGTEST_DIR / "ingest.log"
    if not log_file.exists():
        return IngestLogResponse(log="", finished=True)
    
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否包含完成标记
    finished = "导入完成" in content or "导入失败" in content or "导入超时" in content
    
    return IngestLogResponse(log=content[-5000:], finished=finished)





# === 系统设置 API ===

class LLMConfig(BaseModel):
    api_url: str
    model: str
    api_key: str
    temperature: float = 0.3
    max_tokens: int = 8192
    timeout: int = 300

class SystemConfig(BaseModel):
    vault_root: str
    raw_dir: str
    wiki_dir: str
    work_dir: str
    index_dir: str
    llm: LLMConfig

class ConfigUpdateRequest(BaseModel):
    vault_root: Optional[str] = None
    raw_dir: Optional[str] = None
    wiki_dir: Optional[str] = None
    llm: Optional[LLMConfig] = None

CONFIG_FILE = RAGTEST_DIR / "config.yaml"

@app.get("/api/config", response_model=SystemConfig)
async def get_config(current_user: User = Depends(require_role(["admin"]))):
    """获取系统配置（管理员权限）"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    paths = config.get('paths', {})
    llm = config.get('llm', {})
    api_key = llm.get('api_key', '')
    masked_key = (api_key[:4] + '****') if len(api_key) > 4 else '****'
    return SystemConfig(
        vault_root=paths.get('vault_root', ''),
        raw_dir=paths.get('raw_dir', ''),
        wiki_dir=paths.get('wiki_dir', ''),
        work_dir=paths.get('work_dir', ''),
        index_dir=paths.get('index_dir', ''),
        llm=LLMConfig(
            api_url=llm.get('api_url', ''),
            model=llm.get('model', ''),
            api_key=masked_key,
            temperature=llm.get('temperature', 0.3),
            max_tokens=llm.get('max_tokens', 8192),
            timeout=llm.get('timeout', 300),
        ),
    )

@app.put("/api/config")
async def update_config(update: ConfigUpdateRequest, current_user: User = Depends(require_role(["admin"]))):
    """更新系统配置（管理员权限）"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    if update.vault_root:
        config['paths']['vault_root'] = update.vault_root
    if update.raw_dir:
        config['paths']['raw_dir'] = update.raw_dir
    if update.wiki_dir:
        config['paths']['wiki_dir'] = update.wiki_dir
    if update.llm:
        config['llm']['api_url'] = update.llm.api_url
        config['llm']['model'] = update.llm.model
        config['llm']['api_key'] = update.llm.api_key
        config['llm']['temperature'] = update.llm.temperature
        config['llm']['max_tokens'] = update.llm.max_tokens
        config['llm']['timeout'] = update.llm.timeout
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    
    return {"success": True, "message": "配置已更新，重启服务生效"}


# === 知识图谱 API ===

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

@app.get("/api/graph/data", response_model=GraphData)
async def get_graph_data(type: str = "all"):
    """获取知识图谱数据"""
    import re
    import traceback
    
    try:
        nodes = []
        edges = []
        edge_set = set()
        node_set = set()
        node_contents = {}
        
        for subdir in ['papers', 'entities', 'concepts', 'summaries']:
            dir_path = WIKI_PATH / subdir
            if not dir_path.exists():
                continue
            
            for md_file in dir_path.glob('*.md'):
                try:
                    node_id = f"{subdir}/{md_file.stem}"
                    if subdir == 'papers':
                        node_type = 'paper'
                    elif subdir == 'summaries':
                        node_type = 'synthesis'
                    else:
                        node_type = subdir[:-1]
                    
                    content = md_file.read_text(encoding='utf-8')
                    title = md_file.stem
                    tags = []
                    
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            try:
                                fm = yaml.safe_load(parts[1]) or {}
                                title = fm.get('title', md_file.stem)
                                raw_tags = fm.get('tags', [])
                                if isinstance(raw_tags, list):
                                    tags = [str(t) for t in raw_tags]
                                elif raw_tags:
                                    tags = [str(raw_tags)]
                            except Exception as e:
                                print(f"YAML parse error in {md_file}: {e}")
                    
                    type_map_filter = {
                        'paper': 'paper',
                        'entity': 'entity',
                        'concept': 'concept',
                        'synthesis': 'synthesis',
                    }
                    if type != "all" and node_type != type_map_filter.get(type, type):
                        continue
                    
                    nodes.append(GraphNode(
                        id=node_id,
                        label=str(title),
                        type=node_type,
                        tags=tags,
                        path=str(md_file),
                    ))
                    node_set.add(node_id)
                    node_contents[node_id] = content
                    
                except Exception as e:
                    print(f"Error processing file {md_file}: {e}")
                    continue
        
        for node_id, content in node_contents.items():
            links = re.findall(r'\[\[([^\]]+)\]\]', content)
            for link in links:
                target_id = link.replace('.md', '')
                if '|' in target_id:
                    target_id = target_id.split('|')[0]
                if '/' not in target_id:
                    for t in ['papers', 'entities', 'concepts', 'summaries']:
                        candidate = f"{t}/{target_id}"
                        if candidate in node_set:
                            target_id = candidate
                            break
                
                if target_id in node_set:
                    edge_key = f"{node_id}->{target_id}"
                    if edge_key not in edge_set:
                        edge_set.add(edge_key)
                        edges.append(GraphEdge(
                            id=f"e_{len(edges)}",
                            source=node_id,
                            target=target_id,
                            type="relate",
                        ))
        
        return GraphData(
            nodes=nodes,
            edges=edges,
            metadata={
                "totalNodes": len(nodes),
                "totalEdges": len(edges),
                "lastUpdated": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        print(f"Graph API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Graph data error: {str(e)}")

@app.get("/api/graph/neighbors/{node_id:path}")
async def get_graph_neighbors(node_id: str, depth: int = 1):
    """获取指定节点的邻居子图"""
    import re as _re
    import traceback
    
    try:
        full_graph = await get_graph_data("all")
        all_nodes = {n.id: n for n in full_graph.nodes}
        all_edges = full_graph.edges
        
        if node_id not in all_nodes:
            for candidate in [f"papers/{node_id}", f"entities/{node_id}", f"concepts/{node_id}"]:
                if candidate in all_nodes:
                    node_id = candidate
                    break
        
        if node_id not in all_nodes:
            return GraphData(nodes=[], edges=[], metadata={"totalNodes": 0, "totalEdges": 0})
        
        visited_nodes = {node_id}
        current_layer = {node_id}
        
        for d in range(depth):
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
            e for e in all_edges
            if e.source in visited_nodes and e.target in visited_nodes
        ]
        
        return GraphData(
            nodes=sub_nodes,
            edges=sub_edges,
            metadata={
                "totalNodes": len(sub_nodes),
                "totalEdges": len(sub_edges),
                "centerNode": node_id,
            }
        )
    except Exception as e:
        print(f"Graph Neighbors API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Graph neighbors error: {str(e)}")

@app.get("/api/graph/stats")
async def get_graph_stats():
    """获取图谱统计信息"""
    import re
    graph_data = await get_graph_data()
    
    type_counts = {}
    for node in graph_data.nodes:
        type_counts[node.type] = type_counts.get(node.type, 0) + 1
    
    return {
        "totalNodes": graph_data.metadata["totalNodes"],
        "totalEdges": graph_data.metadata["totalEdges"],
        "nodeTypes": type_counts,
        "lastUpdated": graph_data.metadata["lastUpdated"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)