#!/usr/bin/env python3
"""
LLM-Wiki v3.0 Lint 脚本
系统体检：第一层（规则检查）+ 第二层（LLM深度检查）

用法：
    python lint.py [--vault PATH] [--output FORMAT] [--layer 1|2|all]

输出：
    - 控制台摘要
    - JSON/Markdown 格式报告
"""

import os
import re
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from config_loader import get_paths_config


PAPER_REQUIRED_SECTIONS = ['基本信息', '核心观点', '摘要', '问题定义', '方法', '实验验证', '结论与展望', '提取的实体', '涉及的概念']


class WikiLinter:
    """Wiki 系统 Linter"""
    
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.wiki_path = self.vault_path / "wiki"
        self.index_path = self.wiki_path / "index.md"
        
        self.pages: Dict[str, dict] = {}
        self.issues: List[dict] = []
        self.stats: Dict[str, int] = defaultdict(int)
        self.details: Dict[str, List[dict]] = {}
        
    def scan(self):
        if not self.wiki_path.exists():
            self.issues.append({
                "severity": "error",
                "type": "system",
                "message": f"Wiki 目录不存在: {self.wiki_path}"
            })
            return
        
        for md_file in self.wiki_path.rglob("*.md"):
            if md_file.name in ("index.md", "log.md", "CLAUDE.md"):
                continue
            rel = md_file.relative_to(self.wiki_path)
            if any(part.startswith("_") for part in rel.parts):
                continue
            self._parse_page(md_file)
        
        self.stats["total_pages"] = len(self.pages)
    
    def _parse_page(self, path: Path):
        rel_path = path.relative_to(self.wiki_path)
        page_id = str(rel_path.with_suffix("")).replace("\\", "/")
        
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            self.issues.append({
                "severity": "error",
                "type": "read_error",
                "page": str(rel_path),
                "message": f"读取失败: {e}"
            })
            return
        
        frontmatter = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                except Exception:
                    pass
        
        source_id_count = len(re.findall(r'\[Source:\s*[^\]]+\]', content))
        lines = [l for l in content.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("---")]
        total_lines = len(lines)
        source_id_ratio = source_id_count / total_lines if total_lines > 0 else 0
        
        conflicts = re.findall(r'\[Conflict:\s*([^\]]+)\]', content)
        
        links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)
        links = [l for l in links if not l.startswith("raw/")]
        
        sections = re.findall(r'^## (.+)$', content, re.MULTILINE)
        
        title = frontmatter.get("title", "")
        
        self.pages[page_id] = {
            "path": str(rel_path),
            "frontmatter": frontmatter,
            "content_length": len(content),
            "source_id_count": source_id_count,
            "source_id_ratio": source_id_ratio,
            "conflicts": conflicts,
            "links": links,
            "sections": sections,
            "has_valid_frontmatter": bool(frontmatter.get("title")),
            "content": content,
            "title": title,
        }
    
    def _normalize_link(self, link: str) -> str:
        link_norm = link.replace("\\", "/").replace(".md", "")
        if link_norm.startswith("wiki/"):
            link_norm = link_norm[5:]
        return link_norm
    
    def _build_title_index(self) -> Dict[str, str]:
        title_to_id: Dict[str, str] = {}
        for page_id, page in self.pages.items():
            title = page.get("title", "")
            if title:
                title_to_id[title.lower().strip()] = page_id
                en_part = re.findall(r'[-/]([A-Za-z][\w\s\-]+)$', title)
                if en_part:
                    title_to_id[en_part[0].lower().strip()] = page_id
        return title_to_id
    
    def _resolve_link(self, link: str, all_page_ids: Set[str], title_index: Dict[str, str]) -> Optional[str]:
        link_norm = self._normalize_link(link)
        if link_norm in all_page_ids:
            return link_norm
        
        def _normalize_for_compare(s: str) -> str:
            s = s.lower().strip()
            s = s.replace(" ", "-").replace("_", "-")
            while "--" in s:
                s = s.replace("--", "-")
            return s.strip("-")
        
        link_cmp = _normalize_for_compare(link_norm)
        
        for page_id in all_page_ids:
            pid_lower = page_id.lower()
            link_lower = link_norm.lower()
            if pid_lower == link_lower:
                return page_id
            if _normalize_for_compare(page_id) == link_cmp:
                return page_id
            pid_parts = page_id.split("/")[-1].split("-")
            link_parts = link_norm.split("/")[-1].split("-")
            if len(pid_parts) >= 2 and len(link_parts) >= 2:
                if pid_parts[-1].lower() == link_parts[-1].lower():
                    return page_id
        
        link_basename = link_norm.split("/")[-1] if "/" in link_norm else link_norm
        link_base_cmp = _normalize_for_compare(link_basename)
        for page_id in all_page_ids:
            pid_base = page_id.split("/")[-1] if "/" in page_id else page_id
            if _normalize_for_compare(pid_base) == link_base_cmp:
                return page_id
        
        for title_key, page_id in title_index.items():
            if title_key.endswith(link_basename.lower()):
                return page_id
        
        return None
    
    def check_orphans(self) -> List[dict]:
        orphans = []
        title_index = self._build_title_index()
        all_page_ids = set(self.pages.keys())
        
        indexed_pages = set()
        if self.index_path.exists():
            index_content = self.index_path.read_text(encoding="utf-8")
            raw_links = set(re.findall(r'\[\[([^\]|]+)', index_content))
            for link in raw_links:
                link_norm = self._normalize_link(link)
                indexed_pages.add(link_norm)
        
        inbound_links: Dict[str, int] = defaultdict(int)
        for page_id, page in self.pages.items():
            for link in page["links"]:
                resolved = self._resolve_link(link, all_page_ids, title_index)
                if resolved:
                    inbound_links[resolved] += 1
                else:
                    link_norm = self._normalize_link(link)
                    inbound_links[link_norm] += 1
        
        for page_id, page in self.pages.items():
            ref_count = inbound_links.get(page_id, 0)
            in_index = page_id in indexed_pages
            
            if ref_count == 0 and not in_index:
                orphans.append({
                    "page": page_id,
                    "title": page["frontmatter"].get("title", page_id),
                    "type": page["frontmatter"].get("type", "unknown"),
                    "in_index": in_index,
                    "inbound_links": ref_count
                })
                self.stats["orphans"] += 1
        
        if orphans:
            self.issues.append({
                "severity": "info",
                "type": "orphan_pages",
                "count": len(orphans),
                "pages": [o["page"] for o in orphans],
            })
            self.details["orphan_pages"] = orphans
        
        return orphans
    
    def check_conflicts(self) -> List[dict]:
        conflict_pages = []
        
        for page_id, page in self.pages.items():
            if page["conflicts"]:
                conflict_pages.append({
                    "page": page_id,
                    "title": page["frontmatter"].get("title", page_id),
                    "conflicts": page["conflicts"]
                })
                self.stats["conflicts"] += len(page["conflicts"])
        
        if conflict_pages:
            self.issues.append({
                "severity": "warning",
                "type": "unresolved_conflicts",
                "count": len(conflict_pages),
                "pages": [c["page"] for c in conflict_pages],
            })
            self.details["unresolved_conflicts"] = conflict_pages
        
        return conflict_pages
    
    def check_frontmatter(self) -> List[dict]:
        invalid_pages = []
        
        for page_id, page in self.pages.items():
            if not page["has_valid_frontmatter"]:
                invalid_pages.append({
                    "page": page_id,
                    "title": page["frontmatter"].get("title", ""),
                    "reason": "missing_title" if not page["frontmatter"] else "invalid_frontmatter",
                    "type": page["frontmatter"].get("type", "unknown"),
                })
                self.stats["invalid_frontmatter"] += 1
        
        if invalid_pages:
            self.issues.append({
                "severity": "warning",
                "type": "invalid_frontmatter",
                "count": len(invalid_pages),
                "pages": [i["page"] for i in invalid_pages],
            })
            self.details["invalid_frontmatter"] = invalid_pages
        
        return invalid_pages
    
    def check_source_ratio(self) -> List[dict]:
        no_source_pages = []
        
        for page_id, page in self.pages.items():
            page_type = page.get("frontmatter", {}).get("type", "")
            if page_type not in ("entity", "concept"):
                continue
            
            if page["source_id_count"] == 0:
                no_source_pages.append({
                    "page": page_id,
                    "title": page["frontmatter"].get("title", page_id),
                    "type": page_type,
                    "source_count": 0,
                })
                self.stats["no_source_id"] += 1
        
        if no_source_pages:
            self.issues.append({
                "severity": "warning",
                "type": "no_source_id",
                "count": len(no_source_pages),
                "pages": [l["page"] for l in no_source_pages],
            })
            self.details["no_source_id"] = no_source_pages
        
        return no_source_pages
    
    def check_paper_completeness(self) -> List[dict]:
        broken_papers = []
        
        for page_id, page in self.pages.items():
            page_type = page.get("frontmatter", {}).get("type", "")
            if page_type != "paper":
                continue
            
            missing = []
            for section in PAPER_REQUIRED_SECTIONS:
                if f'## {section}' not in page["content"]:
                    missing.append(section)
            
            body_start = page["content"].find('## 基本信息')
            body_end = page["content"].find('## 提取的实体')
            if body_end == -1:
                body_end = page["content"].find('## 涉及的概念')
            if body_end == -1:
                body_end = len(page["content"])
            
            body_content = page["content"][body_start:body_end] if body_start != -1 else ""
            body_length = len(body_content)
            source_count = page["source_id_count"]
            has_content = body_length > 500
            
            if missing or not has_content:
                broken_papers.append({
                    "page": page_id,
                    "title": page["frontmatter"].get("title", page_id),
                    "missing_sections": missing,
                    "body_length": body_length,
                    "source_count": source_count,
                    "has_content": has_content,
                    "status": page["frontmatter"].get("status", "unknown"),
                    "llm_enhanced": page["frontmatter"].get("llm_enhanced", False),
                })
                self.stats["broken_papers"] += 1
        
        if broken_papers:
            self.issues.append({
                "severity": "warning",
                "type": "broken_papers",
                "count": len(broken_papers),
                "pages": [b["page"] for b in broken_papers],
            })
            self.details["broken_papers"] = broken_papers
        
        return broken_papers
    
    def check_broken_links(self) -> List[dict]:
        broken_link_pages = []
        all_page_ids = set(self.pages.keys())
        title_index = self._build_title_index()
        
        for page_id, page in self.pages.items():
            broken = []
            for link in page["links"]:
                resolved = self._resolve_link(link, all_page_ids, title_index)
                if resolved is None:
                    link_norm = self._normalize_link(link)
                    broken.append(link_norm)
            
            if broken:
                broken_link_pages.append({
                    "page": page_id,
                    "title": page["frontmatter"].get("title", page_id),
                    "type": page["frontmatter"].get("type", "unknown"),
                    "broken_links": broken,
                    "broken_count": len(broken),
                })
                self.stats["broken_links"] += len(broken)
        
        if broken_link_pages:
            self.issues.append({
                "severity": "warning",
                "type": "broken_links",
                "count": len(broken_link_pages),
                "pages": [b["page"] for b in broken_link_pages],
            })
            self.details["broken_links"] = broken_link_pages
        
        return broken_link_pages
    
    def check_duplicate_entities(self) -> List[dict]:
        duplicate_groups = []
        entities_by_en_name: Dict[str, List[dict]] = defaultdict(list)
        
        for page_id, page in self.pages.items():
            page_type = page.get("frontmatter", {}).get("type", "")
            if page_type not in ("entity", "concept"):
                continue
            
            title = page["frontmatter"].get("title", "")
            center_idea = page["frontmatter"].get("center_idea", "")
            
            en_parts = re.findall(r'[-/](\w[\w\s\-\.]+)$', title)
            en_key = en_parts[0].lower().strip() if en_parts else ""
            
            if en_key:
                en_key_clean = re.sub(r'[^a-z0-9]', '', en_key)
                entities_by_en_name[en_key_clean].append({
                    "page": page_id,
                    "title": title,
                    "type": page_type,
                    "center_idea": center_idea,
                    "en_key": en_key,
                })
        
        for en_key, group in entities_by_en_name.items():
            if len(group) > 1:
                duplicate_groups.append({
                    "name_key": en_key,
                    "items": group,
                    "count": len(group),
                })
                self.stats["duplicate_entities"] += len(group)
        
        if duplicate_groups:
            self.issues.append({
                "severity": "warning",
                "type": "duplicate_entities",
                "count": len(duplicate_groups),
                "pages": [g["name_key"] for g in duplicate_groups],
            })
            self.details["duplicate_entities"] = duplicate_groups
        
        return duplicate_groups
    
    def check_missing_concepts(self) -> List[dict]:
        mentioned_concepts: Dict[str, int] = defaultdict(int)
        all_page_ids = set(self.pages.keys())
        title_index = self._build_title_index()
        
        for page_id, page in self.pages.items():
            for link in page["links"]:
                resolved = self._resolve_link(link, all_page_ids, title_index)
                if resolved is None:
                    link_norm = self._normalize_link(link)
                    mentioned_concepts[link_norm] += 1
        
        missing = []
        for concept_id, count in sorted(mentioned_concepts.items(), key=lambda x: -x[1]):
            if concept_id:
                missing.append({
                    "page": concept_id,
                    "mentioned_count": count,
                })
                self.stats["missing_concepts"] += 1
        
        if missing:
            self.issues.append({
                "severity": "info",
                "type": "missing_concepts",
                "count": len(missing),
                "pages": [m["page"] for m in missing[:50]],
            })
            self.details["missing_concepts"] = missing
        
        return missing
    
    def run_layer1(self):
        self.scan()
        self.check_orphans()
        self.check_conflicts()
        self.check_frontmatter()
        self.check_source_ratio()
        self.check_paper_completeness()
        self.check_broken_links()
        self.check_duplicate_entities()
        self.check_missing_concepts()
        return self.generate_report("layer1")
    
    def run_layer2(self, llm_client=None):
        self.scan()
        
        concept_suggestions = []
        if llm_client:
            concept_suggestions = self._llm_suggest_concepts(llm_client)
        
        quality_samples = self._sample_quality_check()
        
        self.stats["llm_concept_suggestions"] = len(concept_suggestions)
        self.stats["quality_samples"] = len(quality_samples)
        
        if concept_suggestions:
            self.issues.append({
                "severity": "info",
                "type": "llm_concept_suggestions",
                "count": len(concept_suggestions),
                "pages": [s["concept"] for s in concept_suggestions[:20]],
            })
            self.details["llm_concept_suggestions"] = concept_suggestions
        
        if quality_samples:
            self.issues.append({
                "severity": "info",
                "type": "quality_samples",
                "count": len(quality_samples),
                "pages": [q["page"] for q in quality_samples],
            })
            self.details["quality_samples"] = quality_samples
        
        return self.generate_report("layer2")
    
    def _llm_suggest_concepts(self, llm_client) -> List[dict]:
        suggestions = []
        try:
            all_mentions: Dict[str, int] = defaultdict(int)
            all_page_ids = set(self.pages.keys())
            title_index = self._build_title_index()
            
            for page_id, page in self.pages.items():
                for link in page["links"]:
                    resolved = self._resolve_link(link, all_page_ids, title_index)
                    if resolved is None:
                        link_norm = self._normalize_link(link)
                        all_mentions[link_norm] += 1
            
            for concept_id, count in sorted(all_mentions.items(), key=lambda x: -x[1]):
                if concept_id and count >= 3:
                    suggestions.append({
                        "concept": concept_id,
                        "mentioned_count": count,
                        "reason": f"被引用{count}次但无独立页面",
                    })
                    if len(suggestions) >= 20:
                        break
        except Exception as e:
            self.issues.append({
                "severity": "error",
                "type": "llm_concept_error",
                "message": str(e),
            })
        
        return suggestions
    
    def _sample_quality_check(self, sample_size: int = 5) -> List[dict]:
        import random
        samples = []
        page_list = list(self.pages.items())
        if not page_list:
            return samples
        
        sample_count = min(sample_size, len(page_list))
        sampled = random.sample(page_list, sample_count)
        
        for page_id, page in sampled:
            page_type = page.get("frontmatter", {}).get("type", "")
            title = page["frontmatter"].get("title", page_id)
            content_len = page["content_length"]
            source_count = page["source_id_count"]
            has_sections = len(page["sections"]) > 0
            has_links = len(page["links"]) > 0
            
            quality_notes = []
            if content_len < 200:
                quality_notes.append("内容过短")
            if page_type in ("entity", "concept") and source_count == 0:
                quality_notes.append("无Source标注")
            if not has_sections:
                quality_notes.append("无章节结构")
            if not has_links:
                quality_notes.append("无内部链接")
            if not page["has_valid_frontmatter"]:
                quality_notes.append("Frontmatter不完整")
            
            samples.append({
                "page": page_id,
                "title": title,
                "type": page_type,
                "content_length": content_len,
                "source_count": source_count,
                "section_count": len(page["sections"]),
                "link_count": len(page["links"]),
                "quality_notes": quality_notes,
                "quality_score": max(0, 10 - len(quality_notes) * 2),
            })
        
        return samples
    
    def run_all_checks(self, layer: str = "all"):
        if layer == "layer1":
            return self.run_layer1()
        elif layer == "layer2":
            return self.run_layer2()
        else:
            self.run_layer1()
            self.run_layer2()
            return self.generate_report("all")
    
    def generate_report(self, layer: str = "all") -> dict:
        total = self.stats["total_pages"]
        if total == 0:
            health_score = 0
        else:
            orphan_score = max(0, 1 - self.stats.get("orphans", 0) / total)
            conflict_score = max(0, 1 - self.stats.get("conflicts", 0) / max(1, total))
            fm_score = max(0, 1 - self.stats.get("invalid_frontmatter", 0) / total)
            paper_score = max(0, 1 - self.stats.get("broken_papers", 0) / max(1, self.stats.get("total_papers", total)))
            link_score = max(0, 1 - self.stats.get("broken_links", 0) / max(1, total * 3))
            dup_score = max(0, 1 - self.stats.get("duplicate_entities", 0) / max(1, total))
            source_score = max(0, 1 - self.stats.get("no_source_id", 0) / max(1, total))
            
            health_score = (
                orphan_score * 0.15 +
                conflict_score * 0.10 +
                fm_score * 0.10 +
                paper_score * 0.15 +
                link_score * 0.15 +
                dup_score * 0.10 +
                source_score * 0.10 +
                0.15
            ) * 100
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "vault_path": str(self.vault_path),
            "wiki_path": str(self.wiki_path),
            "layer": layer,
            "summary": {
                "total_pages": total,
                "health_score": round(health_score, 1),
                "total_issues": len(self.issues)
            },
            "stats": dict(self.stats),
            "issues": self.issues,
            "details": self.details,
        }
        
        return report
    
    def print_summary(self, report: dict):
        print("\n" + "=" * 60)
        print("[REPORT] LLM-Wiki System Health Report")
        print("=" * 60)
        print(f"Time: {report['timestamp']}")
        print(f"Layer: {report['layer']}")
        print(f"Wiki path: {report['wiki_path']}")
        print(f"\n[Summary]")
        print(f"  Total pages: {report['summary']['total_pages']}")
        print(f"  Health score: {report['summary']['health_score']}/100")
        print(f"  Issues: {report['summary']['total_issues']}")
        
        print(f"\n[Stats]")
        for k, v in report["stats"].items():
            print(f"  {k}: {v}")
        
        if self.issues:
            print(f"\n[Issues]")
            for issue in self.issues:
                severity_icon = {"error": "[ERROR]", "warning": "[WARN]", "info": "[INFO]"}.get(issue["severity"], "[*]")
                print(f"  {severity_icon} [{issue['type']}] count={issue.get('count', 1)}")
                if "pages" in issue:
                    for p in issue["pages"][:5]:
                        print(f"      - {p}")
                    if len(issue["pages"]) > 5:
                        print(f"      ... total {len(issue['pages'])} pages")
        
        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki 系统体检")
    _paths = get_paths_config()
    _default_vault = _paths.get("vault_root", ".")
    parser.add_argument("--vault", default=_default_vault, 
                        help="Obsidian Vault 路径")
    parser.add_argument("--output", choices=["json", "markdown", "console"], default="console",
                        help="输出格式")
    parser.add_argument("--out-file", default=None, help="输出文件路径")
    parser.add_argument("--layer", choices=["layer1", "layer2", "all"], default="all",
                        help="检查层级")
    
    args = parser.parse_args()
    
    linter = WikiLinter(args.vault)
    report = linter.run_all_checks(layer=args.layer)
    
    if args.output == "console":
        linter.print_summary(report)
    elif args.output == "json":
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out_file:
            Path(args.out_file).write_text(output, encoding="utf-8")
            print(f"报告已保存到: {args.out_file}")
        else:
            print(output)
    elif args.output == "markdown":
        md_report = generate_markdown_report(report)
        if args.out_file:
            Path(args.out_file).write_text(md_report, encoding="utf-8")
            print(f"报告已保存到: {args.out_file}")
        else:
            print(md_report)


def generate_markdown_report(report: dict) -> str:
    lines = [
        f"# LLM-Wiki 系统体检报告",
        "",
        f"**时间**: {report['timestamp']}",
        f"**层级**: {report['layer']}",
        f"**Wiki 路径**: `{report['wiki_path']}`",
        "",
        "## 总览",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 总页面 | {report['summary']['total_pages']} |",
        f"| 健康分数 | {report['summary']['health_score']}/100 |",
        f"| 问题数 | {report['summary']['total_issues']} |",
        "",
        "## 统计",
        ""
    ]
    
    for k, v in report["stats"].items():
        lines.append(f"- {k}: {v}")
    
    if report["issues"]:
        lines.extend(["", "## 问题详情", ""])
        for issue in report["issues"]:
            severity_icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue["severity"], "•")
            lines.append(f"### {severity_icon} {issue['type']}")
            lines.append("")
            lines.append(f"- 数量: {issue.get('count', 1)}")
            if "pages" in issue:
                lines.append("- 涉及页面:")
                for p in issue["pages"]:
                    lines.append(f"  - `{p}`")
    
    return "\n".join(lines)


if __name__ == "__main__":
    main()
