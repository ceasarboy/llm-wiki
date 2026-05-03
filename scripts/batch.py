#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 批量处理编排脚本 v2.0
功能：
  1. 扫描 raw 目录，找出未处理的文档
  2. 调用 generate_all_in_one() 合并生成论文+实体+概念
  3. 调用 review_with_fix_cycle() 进行审核修正循环
  4. 调用 process_merge() 检查是否需要融合
  5. 审核通过后写入 wiki 目录，更新 log.md
  6. 断点续传：记录已处理文件，支持中断后继续
  7. 每批输出质量统计
"""

import os
import sys
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_llm_config, get_paths_config, get_scoring_config

PATHS = get_paths_config()
SCORING = get_scoring_config()

RAW_DIR = Path(PATHS["raw_dir"])
WIKI_DIR = Path(PATHS["wiki_dir"])
WORK_DIR = Path(PATHS["work_dir"])
OUTPUT_DIR = WORK_DIR / "generated"
REPORTS_DIR = WORK_DIR / "reports"
SCRIPTS_DIR = Path(__file__).parent

STATE_FILE = WORK_DIR / "batch_state.json"
LOG_FILE = WIKI_DIR / "log.md"
INDEX_FILE = WIKI_DIR / "index.md"

PASS_THRESHOLD = SCORING["pass_threshold"]
DEFAULT_BATCH_SIZE = 20


def load_state() -> Dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "processed": [],
        "failed": [],
        "skipped": [],
        "total_batches": 0,
        "started_at": None,
        "last_updated": None,
    }


def save_state(state: Dict):
    state["last_updated"] = datetime.now().isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def scan_pending_docs(state: Dict, retry_failed: bool = False) -> List[Path]:
    raw_docs = sorted(RAW_DIR.glob("*.md"))
    print(f"raw 目录共 {len(raw_docs)} 个文档")

    processed_set = set(state.get("processed", []))
    skipped_set = set(state.get("skipped", []))

    if retry_failed and state.get("failed"):
        print(f"重试模式: 将重试 {len(state['failed'])} 个失败文档")
        state["failed"] = []
        save_state(state)

    failed_set = set(state.get("failed", []))

    wiki_papers_dir = WIKI_DIR / "papers"
    existing_wiki = set()
    if wiki_papers_dir.exists():
        for f in wiki_papers_dir.glob("*.md"):
            stem = f.stem
            if stem.endswith("_论文"):
                stem = stem[:-3]
            existing_wiki.add(stem)

    pending = []
    skipped_new = []

    for doc in raw_docs:
        name = doc.name
        stem = doc.stem

        if name in processed_set or name in failed_set:
            continue

        if stem in existing_wiki:
            if name not in skipped_set:
                skipped_new.append(name)
            continue

        pending.append(doc)

    if skipped_new:
        state["skipped"].extend(skipped_new)
        save_state(state)
        print(f"新增跳过（wiki 已存在）: {len(skipped_new)} 个")

    print(f"待处理: {len(pending)} 个 | 已处理: {len(processed_set)} | 跳过: {len(state['skipped'])} | 失败: {len(failed_set)}")
    return pending


def process_document(doc_path: Path, output_dir: Path) -> Dict:
    """
    处理单个文档 - 整合新流程
    1. 调用 generate_all_in_one() 合并生成
    2. 调用 review_with_fix_cycle() 审核修正
    3. 调用 process_merge() 检查融合
    """
    from agent_g import generate_all_in_one
    from review import review_with_fix_cycle
    from merge import process_merge
    
    result = {
        "doc": doc_path.name,
        "status": "error",
        "paper": None,
        "entities": [],
        "concepts": [],
        "paper_score": 0,
        "fix_iterations": 0,
    }
    
    print(f"    [Step 1] 调用 generate_all_in_one()...")
    
    try:
        content = doc_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"    [Error] 读取文档失败: {e}")
        return result
    
    gen_result = generate_all_in_one(doc_path, content)
    
    if not gen_result or not gen_result.get("paper") or not gen_result["paper"][0]:
        paper_val = gen_result.get("paper") if gen_result else None
        print(f"    [Error] 生成失败 (paper={paper_val})")
        return result
    
    paper_content, paper_meta = gen_result["paper"]
    entities = gen_result.get("entities", [])
    concepts = gen_result.get("concepts", [])
    llm_score = gen_result.get("llm_score", 0)
    llm_passed = gen_result.get("llm_passed", False)
    
    print(f"    [Step 1] 完成: LLM自评 {llm_score}/10, {'通过' if llm_passed else '打回'}")
    print(f"    [Step 1] 生成: 论文1篇, 实体{len(entities)}个, 概念{len(concepts)}个")
    
    paper_file = output_dir / "papers" / f"{doc_path.stem}_论文.md"
    paper_file.parent.mkdir(parents=True, exist_ok=True)
    with open(paper_file, 'w', encoding='utf-8') as f:
        f.write(paper_content)
    result["paper"] = str(paper_file)
    
    print(f"    [Step 2] 调用 review_with_fix_cycle()...")
    
    review_result, fix_iterations = review_with_fix_cycle(paper_file, "paper")
    paper_score = review_result.overall_score
    paper_passed = review_result.passed
    
    result["paper_score"] = paper_score
    result["fix_iterations"] = fix_iterations
    
    print(f"    [Step 2] 完成: 程序审核 {paper_score}/10, {'通过' if paper_passed else '不通过'}, 修正{fix_iterations}轮")
    
    if not paper_passed:
        result["status"] = "review_failed"
        return result
    
    entity_files = []
    for idx, (entity_content, entity_meta) in enumerate(entities, 1):
        entity_title = entity_meta.get("title", f"entity_{idx}")
        safe_name = entity_title.replace('/', '_').replace('\\', '_')[:50]
        entity_file = output_dir / "entities" / f"{safe_name}.md"
        entity_file.parent.mkdir(parents=True, exist_ok=True)
        
        should_save, merged_content, existing_path = process_merge(
            entity_title, entity_content, "entity",
            source_paper_stem=f"{doc_path.stem}_论文",
            source_title=paper_meta.get("title", doc_path.stem),
            doc_path=doc_path
        )
        
        if should_save:
            final_content = merged_content if merged_content else entity_content
            
            with open(entity_file, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            entity_review, _ = review_with_fix_cycle(entity_file, "entity")
            if entity_review.passed:
                entity_files.append(str(entity_file))
                merge_status = "融合" if existing_path else "新建"
                print(f"    [Entity] {entity_title}: {entity_review.overall_score}/10 [OK] ({merge_status})")
            else:
                print(f"    [Entity] {entity_title}: {entity_review.overall_score}/10 [FAIL]")
        else:
            print(f"    [Entity] {entity_title}: 跳过（已存在且无需更新）")
    
    result["entities"] = entity_files
    
    concept_files = []
    for idx, (concept_content, concept_meta) in enumerate(concepts, 1):
        concept_title = concept_meta.get("title", f"concept_{idx}")
        safe_name = concept_title.replace('/', '_').replace('\\', '_')[:50]
        concept_file = output_dir / "concepts" / f"{safe_name}.md"
        concept_file.parent.mkdir(parents=True, exist_ok=True)
        
        should_save, merged_content, existing_path = process_merge(
            concept_title, concept_content, "concept",
            source_paper_stem=f"{doc_path.stem}_论文",
            source_title=paper_meta.get("title", doc_path.stem),
            doc_path=doc_path
        )
        
        if should_save:
            final_content = merged_content if merged_content else concept_content
            
            with open(concept_file, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            concept_review, _ = review_with_fix_cycle(concept_file, "concept")
            if concept_review.passed:
                concept_files.append(str(concept_file))
                merge_status = "融合" if existing_path else "新建"
                print(f"    [Concept] {concept_title}: {concept_review.overall_score}/10 [OK] ({merge_status})")
            else:
                print(f"    [Concept] {concept_title}: {concept_review.overall_score}/10 [FAIL]")
        else:
            print(f"    [Concept] {concept_title}: 跳过（已存在且无需更新）")
    
    result["concepts"] = concept_files
    result["status"] = "passed"
    
    return result


def extract_and_copy_images(doc_path: Path, dest_dir: Path) -> List[str]:
    """
    从原始markdown中提取图片引用，复制到目标目录
    返回: 复制的图片文件名列表
    """
    copied_images = []
    try:
        content = doc_path.read_text(encoding='utf-8')
        # 查找markdown图片引用 ![](image.jpg)
        import re
        image_pattern = r'!\[.*?\]\((.*?)\)'
        matches = re.findall(image_pattern, content)
        
        src_dir = doc_path.parent
        
        for img_file in matches:
            img_path = src_dir / img_file
            if img_path.exists():
                dest_img = dest_dir / img_file
                if not dest_img.exists():
                    shutil.copy2(img_path, dest_img)
                    copied_images.append(img_file)
                    print(f"    [Image] 复制图片: {img_file}")
        
    except Exception as e:
        print(f"    [Warning] 处理图片失败: {e}")
    
    return copied_images


def persist_to_wiki(generated_file: Path, content_type: str = "paper", source_doc: Path = None) -> Path:
    if content_type == "paper":
        dest_dir = WIKI_DIR / "papers"
    elif content_type == "entity":
        dest_dir = WIKI_DIR / "entities"
    elif content_type == "concept":
        dest_dir = WIKI_DIR / "concepts"
    else:
        dest_dir = WIKI_DIR / "papers"
    
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制文档
    dest = dest_dir / generated_file.name
    shutil.copy2(generated_file, dest)
    print(f"    [Persist] 写入: {dest}")
    
    # 如果是论文，并且有原始文档，复制图片
    if content_type == "paper" and source_doc and source_doc.exists():
        extract_and_copy_images(source_doc, dest_dir)
    
    if content_type == "paper":
        try:
            import postprocess_links
            postprocess_links.process_paper(dest)
        except ImportError:
            print(f"    [PostProcess] 跳过链接后处理（模块未找到）")
        except Exception as e:
            print(f"    [PostProcess] 警告: {e}")
    
    return dest


def append_log(entries: List[Dict]):
    if not entries:
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        for entry in entries:
            ts = entry.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
            action = entry.get("action", "generated")
            page = entry.get("page", "")
            score = entry.get("score", "")
            source_doc = entry.get("source_doc", "")
            if source_doc:
                f.write(f"- [{ts}] {action}: `{page}` (score={score}) | 原始文档: {source_doc}\n")
            else:
                f.write(f"- [{ts}] {action}: `{page}` (score={score})\n")


def process_batch(batch: List[Path], batch_num: int, state: Dict) -> Dict:
    batch_dir = OUTPUT_DIR / f"batch_{batch_num:03d}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "batch": batch_num,
        "total": len(batch),
        "passed": 0,
        "review_failed": 0,
        "error": 0,
        "entities": 0,
        "concepts": 0,
        "details": [],
    }
    log_entries = []

    for i, doc_path in enumerate(batch, 1):
        print(f"\n  [{i}/{len(batch)}] {doc_path.name}")
        
        doc_dir = batch_dir / doc_path.stem
        doc_dir.mkdir(exist_ok=True)
        
        try:
            result = process_document(doc_path, doc_dir)
        except Exception as e:
            print(f"    [Error] 处理文档异常: {e}")
            result = {"doc": doc_path.name, "status": "error", "error": str(e),
                      "paper": None, "entities": [], "concepts": [], "paper_score": 0, "fix_iterations": 0}
        
        if result["status"] == "passed":
            if result["paper"]:
                persist_to_wiki(Path(result["paper"]), "paper", doc_path)
            
            for entity_file in result["entities"]:
                persist_to_wiki(Path(entity_file), "entity")
                stats["entities"] += 1
            
            for concept_file in result["concepts"]:
                persist_to_wiki(Path(concept_file), "concept")
                stats["concepts"] += 1
            
            state["processed"].append(doc_path.name)
            stats["passed"] += 1
            log_entries.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": "generated+reviewed",
                "page": Path(result["paper"]).name if result["paper"] else doc_path.name,
                "score": result["paper_score"],
                "entities": len(result["entities"]),
                "concepts": len(result["concepts"]),
                "fix_iterations": result["fix_iterations"],
                "source_doc": f"raw/papers/markdown/{doc_path.name}",
            })
        
        elif result["status"] == "review_failed":
            state["failed"].append(doc_path.name)
            stats["review_failed"] += 1
            log_entries.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "action": "review_failed",
                "page": doc_path.name,
                "score": result["paper_score"],
                "source_doc": f"raw/papers/markdown/{doc_path.name}",
            })
        
        else:
            state["failed"].append(doc_path.name)
            stats["error"] += 1
        
        stats["details"].append({
            "doc": doc_path.name,
            "status": result["status"],
            "paper_score": result["paper_score"],
            "entities": len(result["entities"]),
            "concepts": len(result["concepts"]),
            "fix_iterations": result["fix_iterations"],
        })
        
        save_state(state)

    append_log(log_entries)

    stats_file = batch_dir / "batch_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Phase 4 批量处理编排脚本 v2.0")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"每批文档数量（默认 {DEFAULT_BATCH_SIZE}）")
    parser.add_argument("--max-batches", type=int, default=None, help="最多处理几批（默认全部）")
    parser.add_argument("--reset", action="store_true", help="重置状态，从头开始")
    parser.add_argument("--status", action="store_true", help="只显示当前状态，不处理")
    parser.add_argument("--dry-run", action="store_true", help="只扫描，不实际处理")
    parser.add_argument("--retry-failed", action="store_true", help="重试所有失败的文档")
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 4 批量处理编排脚本 v2.0")
    print("新流程: generate_all_in_one → review_with_fix_cycle → process_merge")
    print("=" * 60)

    if args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("状态已重置")

    state = load_state()
    if state["started_at"] is None:
        state["started_at"] = datetime.now().isoformat()

    pending = scan_pending_docs(state, retry_failed=args.retry_failed)

    if args.status or args.dry_run:
        print(f"\n当前状态:")
        print(f"  待处理: {len(pending)} 个")
        print(f"  已处理: {len(state['processed'])} 个")
        print(f"  跳过:   {len(state['skipped'])} 个")
        print(f"  失败:   {len(state['failed'])} 个")
        print(f"  已完成批次: {state['total_batches']}")
        if args.dry_run and pending:
            print(f"\n前 5 个待处理文档:")
            for d in pending[:5]:
                print(f"  - {d.name}")
        return 0

    if not pending:
        print("\n所有文档已处理完毕！")
        return 0

    batch_size = args.batch_size
    batches = [pending[i:i+batch_size] for i in range(0, len(pending), batch_size)]
    total_batches = len(batches)

    if args.max_batches:
        batches = batches[:args.max_batches]

    print(f"\n共 {len(pending)} 个待处理文档，分 {total_batches} 批（每批 {batch_size} 个）")
    if args.max_batches:
        print(f"本次最多处理 {args.max_batches} 批（{args.max_batches * batch_size} 个文档）")

    all_stats = []
    total_passed = 0
    total_review_failed = 0
    total_error = 0

    for batch_idx, batch in enumerate(batches):
        batch_num = state["total_batches"] + batch_idx + 1
        print(f"\n{'=' * 60}")
        print(f"批次 {batch_num}/{state['total_batches'] + total_batches}  ({len(batch)} 个文档)")
        print(f"{'=' * 60}")

        try:
            stats = process_batch(batch, batch_num, state)
            all_stats.append(stats)
            total_passed += stats["passed"]
            total_review_failed += stats["review_failed"]
            total_error += stats["error"]

            print(f"\n批次 {batch_num} 完成: 通过={stats['passed']} 审核失败={stats['review_failed']} 错误={stats['error']}")

        except KeyboardInterrupt:
            print("\n\n用户中断，已保存进度，下次运行将从断点继续")
            save_state(state)
            break

    state["total_batches"] += len(all_stats)
    save_state(state)

    print(f"\n{'=' * 60}")
    print(f"Phase 4 批量处理汇总")
    print(f"{'=' * 60}")
    print(f"本次处理: {sum(s['total'] for s in all_stats)} 个文档")
    print(f"  通过:       {total_passed}")
    print(f"  审核失败:   {total_review_failed}")
    print(f"  错误:       {total_error}")
    print(f"累计进度: {len(state['processed'])}/{len(state['processed']) + len(pending)} 已完成")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "version": "2.0",
            "total_processed": sum(s["total"] for s in all_stats),
            "total_passed": total_passed,
            "total_review_failed": total_review_failed,
            "total_error": total_error,
            "batches": all_stats,
            "state_summary": {
                "processed": len(state["processed"]),
                "failed": len(state["failed"]),
                "skipped": len(state["skipped"]),
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\n汇总报告: {report_file}")

    return 0


if __name__ == "__main__":
    exit(main())
