"""维护与修复 API"""

import re
import sys
import uuid
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime

import yaml
from fastapi import APIRouter, HTTPException, Depends

from api.dependencies import (
    vault_index,
    background_tasks,
    _cleanup_old_tasks,
    _safe_path,
    WIKI_PATH,
    VAULT_PATH,
    SCRIPTS_DIR,
    RAW_DIR,
    RAGTEST_DIR,
    get_db_ctx,
)
from api.database import get_db
from api.middleware.auth import require_role
from api.models import User

sys.path.insert(0, str(SCRIPTS_DIR))
_qdrant_cfg = yaml.safe_load(open(RAGTEST_DIR / "config.yaml", encoding="utf-8")).get("qdrant", {})

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/status")
async def get_status():
    total = len(vault_index.pages)
    by_type = {k: len(v) for k, v in vault_index.by_type.items()}
    return {
        "total_docs": total,
        "processed_docs": by_type.get("paper", 0)
        + by_type.get("concept", 0)
        + by_type.get("entity", 0),
        "pending_docs": 0,
        "pass_rate": 95.0,
        "avg_score": 8.5,
        "review_queue": 0,
        "last_check": vault_index.last_scan or datetime.now().isoformat(),
        "counts_by_type": by_type,
    }


@router.post("/rescan")
async def rescan_vault():
    vault_index.scan()
    return {"success": True, "total_pages": len(vault_index.pages)}


@router.post("/health-check")
async def run_health_check(layer: str = "all"):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from scripts.lint import WikiLinter

    def _run_lint():
        linter = WikiLinter(str(VAULT_PATH), wiki_path=str(WIKI_PATH))
        return linter.run_all_checks(layer=layer)

    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(ThreadPoolExecutor(1), _run_lint)
    return {"success": True, "report": report}


@router.post("/fix/frontmatter/{id:path}")
async def fix_frontmatter(
    id: str, current_user: User = Depends(require_role(["admin", "maintainer"]))
):
    page = vault_index.pages.get(id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    md_file = _safe_path(WIKI_PATH, id)
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = md_file.read_text(encoding="utf-8")
    extracted_title = None

    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        extracted_title = title_match.group(1).strip()

    if not extracted_title:
        arxiv_match = re.search(r"\*\*arXiv ID\*\*:\s*(.+)", content)
        if arxiv_match:
            extracted_title = arxiv_match.group(1).strip()

    if not extracted_title:
        title_field_match = re.search(r"\*\*标题\*\*:\s*(.+)", content)
        if title_field_match:
            extracted_title = title_field_match.group(1).strip()

    if not extracted_title:
        h2_match = re.search(r"^##\s+(.+)$", content, re.MULTILINE)
        if h2_match:
            extracted_title = h2_match.group(1).strip()

    if not extracted_title:
        extracted_title = md_file.stem.replace("_论文", "").replace("_", " ")

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except Exception:
                fm = {}
            fm["title"] = extracted_title
            new_fm = yaml.dump(
                fm, allow_unicode=True, default_flow_style=False
            ).strip()
            new_content = f"---\n{new_fm}\n---{parts[2]}"
        else:
            raise HTTPException(status_code=400, detail="Cannot parse frontmatter")
    else:
        page_type = (
            "paper"
            if "论文" in md_file.stem or "基本信息" in content
            else (
                "entity"
                if md_file.parent.name == "entities"
                else "concept" if md_file.parent.name == "concepts" else "unknown"
            )
        )
        fm = {"title": extracted_title, "type": page_type}
        new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
        new_content = f"---\n{new_fm}\n---\n{content}"

    md_file.write_text(new_content, encoding="utf-8")
    vault_index.scan()
    return {"success": True, "message": f"已修复: title={extracted_title}"}


@router.post("/fix/regenerate-paper/{id:path}")
async def regenerate_paper(
    id: str, current_user: User = Depends(require_role(["admin", "maintainer"]))
):
    _cleanup_old_tasks()
    page = vault_index.pages.get(id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.get("type", "") != "paper":
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
            source_match = re.search(r"raw/papers/markdown/(.+?)\.md", source_str)
            if source_match:
                source_file_stem = source_match.group(1)

    if not source_file_stem:
        source_match = re.search(
            r"source:\s*\[\[raw/papers/markdown/(.+?)\.md\]\]", content
        )
        if not source_match:
            source_match = re.search(r"raw/papers/markdown/(.+?)\.md", content)
        if source_match:
            source_file_stem = source_match.group(1)

    if not source_file_stem:
        source_file_stem = md_file.stem.replace("_论文", "")

    deleted_entities = []
    deleted_concepts = []

    entity_links = re.findall(r"\[\[entities/([^\]|]+)", content)
    for link in entity_links:
        entity_id = f"entities/{link}"
        entity_file = _safe_path(WIKI_PATH, entity_id)
        if entity_file.exists():
            entity_file.unlink()
            deleted_entities.append(entity_id)

    concept_links = re.findall(r"\[\[concepts/([^\]|]+)", content)
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
            if str(SCRIPTS_DIR) not in sys.path:
                sys.path.insert(0, str(SCRIPTS_DIR))
            from batch import process_document, persist_to_wiki
            import shutil

            temp_dir = WIKI_PATH / "_regen_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                result = process_document(raw_file, temp_dir)
                if result.get("status") != "passed":
                    background_tasks[task_id].update(
                        {
                            "status": "failed",
                            "message": f"重新生成失败: {result.get('status', 'unknown')}",
                            "finished_at": datetime.now().isoformat(),
                        }
                    )
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

                background_tasks[task_id].update(
                    {
                        "status": "completed",
                        "message": f"论文已重新生成 (源: {source_file_stem}.md)",
                        "regenerated_files": persisted,
                        "finished_at": datetime.now().isoformat(),
                    }
                )
            finally:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            background_tasks[task_id].update(
                {
                    "status": "failed",
                    "message": f"重新生成异常: {str(e)}",
                    "finished_at": datetime.now().isoformat(),
                }
            )
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


@router.get("/fix/task-status/{task_id}")
async def get_task_status(task_id: str):
    task = background_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/fix/broken-link/{id:path}")
async def fix_broken_link(
    id: str,
    body: dict,
    current_user: User = Depends(require_role(["admin", "maintainer"])),
):
    action = body.get("action", "remove")
    broken_link = body.get("broken_link", "")
    replacement = body.get("replacement", "")

    md_file = _safe_path(WIKI_PATH, id)
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    content = md_file.read_text(encoding="utf-8")

    if action == "remove":
        new_content = re.sub(
            rf"-\s*\[\[{re.escape(broken_link)}(?:\|[^\]]+)?\]\]\s*\n?", "", content
        )
        new_content = re.sub(
            rf"\[\[{re.escape(broken_link)}(?:\|[^\]]+)?\]\]", "", new_content
        )
    elif action == "replace":
        if not replacement:
            raise HTTPException(status_code=400, detail="Replacement link required")
        new_content = content.replace(f"[[{broken_link}]]", f"[[{replacement}]]")
        new_content = re.sub(
            rf"\[\[{re.escape(broken_link)}\|[^\]]+\]\]",
            f"[[{replacement}]]",
            new_content,
        )
    else:
        raise HTTPException(
            status_code=400, detail="Invalid action: use 'remove' or 'replace'"
        )

    md_file.write_text(new_content, encoding="utf-8")
    vault_index.scan()
    return {
        "success": True,
        "message": f"链接已{'删除' if action == 'remove' else '替换'}",
    }


@router.post("/fix/merge-entities")
async def merge_entities(
    body: dict, current_user: User = Depends(require_role(["admin", "maintainer"]))
):
    keep_page = body.get("keep_page", "")
    remove_page = body.get("remove_page", "")

    if not keep_page or not remove_page:
        raise HTTPException(
            status_code=400, detail="keep_page and remove_page required"
        )

    keep_file = WIKI_PATH / f"{keep_page}.md"
    remove_file = WIKI_PATH / f"{remove_page}.md"

    if not keep_file.exists():
        raise HTTPException(status_code=404, detail=f"Keep page not found: {keep_page}")
    if not remove_file.exists():
        raise HTTPException(
            status_code=404, detail=f"Remove page not found: {remove_page}"
        )

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
        remove_body = r_parts[2] if len(r_parts) >= 3 else remove_content
    else:
        remove_body = remove_content

    merged_body = (
        body_start.rstrip()
        + "\n\n## 合并自: "
        + remove_page
        + "\n"
        + remove_body.lstrip()
    )
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

        new_file_content = file_content.replace(
            f"[[{remove_page}]]", f"[[{keep_page}]]"
        )
        new_file_content = re.sub(
            rf"\[\[{re.escape(remove_page)}\|[^\]]+\]\]",
            f"[[{keep_page}]]",
            new_file_content,
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


@router.post("/refresh")
async def refresh_index():
    vault_index.scan()
    return {"message": "索引已刷新", "total_pages": len(vault_index.pages)}


@router.post("/rebuild-chromadb")
async def rebuild_chromadb(
    current_user: User = Depends(require_role(["admin"])),
):
    import shutil

    chroma_dir = RAGTEST_DIR / "index" / "chroma"
    if not chroma_dir.exists():
        return {"success": True, "message": "ChromaDB 目录不存在，无需重建"}

    shutil.rmtree(str(chroma_dir), ignore_errors=True)

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from indexer import WikiIndexer

    indexer = WikiIndexer(
        vault_path=str(VAULT_PATH),
        index_path=str(RAGTEST_DIR / "index"),
    )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        ThreadPoolExecutor(1),
        indexer.build_index,
    )

    return {"success": True, "message": "ChromaDB 已成功重建"}


@router.post("/rebuild-qdrant")
async def rebuild_qdrant(
    current_user: User = Depends(require_role(["admin"])),
):
    try:
        from concurrent.futures import ThreadPoolExecutor
        from qdrant_indexer import build_qdrant_index

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            ThreadPoolExecutor(1),
            build_qdrant_index,
            WIKI_PATH,
            _qdrant_cfg.get("collection_name", "llm_wiki_bge"),
        )
        return {"success": True, "message": "Qdrant BGE-M3 索引已成功重建"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant 重建失败: {str(e)}")
