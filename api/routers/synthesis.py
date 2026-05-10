"""综述与对比分析 API"""

import time
import threading
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from api.dependencies import (
    vault_index,
    background_tasks,
    _cleanup_old_tasks,
    WIKI_PATH,
    RAW_DIR,
)
from api.middleware.auth import require_role

router = APIRouter(prefix="/synthesis", tags=["synthesis"])


import logging

logger = logging.getLogger(__name__)


class SelectedItem(BaseModel):
    id: str
    type: str


class SurveyRequest(BaseModel):
    items: List[SelectedItem]
    topic: str = ""
    prompt: str = ""


class CompareRequest(BaseModel):
    items: List[SelectedItem]
    topic: str = ""
    prompt: str = ""


class TaskResponse(BaseModel):
    task_id: str
    status: str


class SynthesisItem(BaseModel):
    id: str
    title: str
    type: str
    tags: List[str]
    updated: str
    query_origin: str


class SynthesisListResponse(BaseModel):
    items: List[SynthesisItem]
    total: int


class SearchItem(BaseModel):
    id: str
    title: str
    type: str
    tags: List[str]
    updated: str


class SearchItemsResponse(BaseModel):
    items: List[SearchItem]
    total: int


def _collect_item_content(item: SelectedItem) -> dict | None:
    """根据 item 的 id 和 type 收集内容"""
    if item.type == "raw":
        md_file = RAW_DIR / f"{item.id}.md"
        if not md_file.exists():
            return None
        content = md_file.read_text(encoding="utf-8")
        return {
            "id": item.id,
            "title": md_file.stem,
            "content": content[:8000],
            "type": "raw",
        }

    if item.id in vault_index.pages:
        page_info = vault_index.pages[item.id]
        file_path = Path(page_info["file_path"])
        if not file_path.exists():
            return None
        content = file_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return {
            "id": item.id,
            "title": page_info["title"],
            "content": content[:8000],
            "type": page_info["type"],
        }

    type_dirs = {
        "paper": "papers",
        "entity": "entities",
        "concept": "concepts",
        "synthesis": "syntheses",
    }
    subdir = type_dirs.get(item.type, "")
    if subdir:
        for suffix in ["_论文", "_综合", ""]:
            test_path = WIKI_PATH / subdir / f"{item.id}{suffix}.md"
            if test_path.exists():
                content = test_path.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        content = parts[2].strip()
                return {
                    "id": item.id,
                    "title": test_path.stem.replace("_论文", "").replace("_综合", ""),
                    "content": content[:8000],
                    "type": item.type,
                }

    return None


def _run_survey_task(task_id: str, items: list, topic: str, prompt: str = ""):
    try:
        import sys
        scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from survey import generate_survey_from_items, save_survey

        background_tasks[task_id]["status"] = "collecting"
        background_tasks[task_id]["progress"] = 10

        collected = []
        for item_data in items:
            si = SelectedItem(id=item_data["id"], type=item_data["type"])
            result = _collect_item_content(si)
            if result:
                collected.append(result)

        if not collected:
            background_tasks[task_id]["status"] = "failed"
            background_tasks[task_id]["error"] = "未能收集到任何有效内容"
            background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return

        background_tasks[task_id]["status"] = "generating"
        background_tasks[task_id]["progress"] = 30

        content = generate_survey_from_items(collected, topic, user_prompt=prompt)
        if not content:
            background_tasks[task_id]["status"] = "failed"
            background_tasks[task_id]["error"] = "LLM 生成失败"
            background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return

        background_tasks[task_id]["status"] = "reviewing"
        background_tasks[task_id]["progress"] = 60

        try:
            from review_survey import review_survey_with_fix_cycle
            result, fixed_content = review_survey_with_fix_cycle(content)
            background_tasks[task_id]["review_score"] = result.overall_score
            background_tasks[task_id]["review_passed"] = result.passed
            if not result.passed:
                fixed_content = content
            content = fixed_content
        except Exception as e:
            logger.warning(f"  审核失败，使用原始内容: {e}")
            background_tasks[task_id]["review_error"] = str(e)
            background_tasks[task_id]["review_passed"] = False

        background_tasks[task_id]["status"] = "saving"
        background_tasks[task_id]["progress"] = 80

        save_topic = topic or "、".join([c["title"][:20] for c in collected[:3]])
        filepath = save_survey(save_topic, content)
        vault_index.scan()

        background_tasks[task_id]["status"] = "completed"
        background_tasks[task_id]["progress"] = 100
        background_tasks[task_id]["result_file"] = str(filepath)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    except Exception as e:
        background_tasks[task_id]["status"] = "failed"
        background_tasks[task_id]["error"] = str(e)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")


def _run_compare_task(task_id: str, items: list, topic: str, prompt: str = ""):
    try:
        import sys
        scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from compare import generate_compare_from_items, save_compare

        background_tasks[task_id]["status"] = "collecting"
        background_tasks[task_id]["progress"] = 10

        collected = []
        for item_data in items:
            si = SelectedItem(id=item_data["id"], type=item_data["type"])
            result = _collect_item_content(si)
            if result:
                collected.append(result)

        if len(collected) < 2:
            background_tasks[task_id]["status"] = "failed"
            background_tasks[task_id]["error"] = f"至少需要 2 个有效项目进行对比，当前只有 {len(collected)} 个"
            background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return

        background_tasks[task_id]["status"] = "generating"
        background_tasks[task_id]["progress"] = 30

        content = generate_compare_from_items(collected, topic, user_prompt=prompt)
        if not content:
            background_tasks[task_id]["status"] = "failed"
            background_tasks[task_id]["error"] = "LLM 生成失败"
            background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return

        background_tasks[task_id]["status"] = "reviewing"
        background_tasks[task_id]["progress"] = 60

        try:
            from review_compare import review_compare_with_fix_cycle
            result, fixed_content = review_compare_with_fix_cycle(content)
            background_tasks[task_id]["review_score"] = result.overall_score
            background_tasks[task_id]["review_passed"] = result.passed
            if not result.passed:
                fixed_content = content
            content = fixed_content
        except Exception as e:
            logger.warning(f"  审核失败，使用原始内容: {e}")
            background_tasks[task_id]["review_error"] = str(e)
            background_tasks[task_id]["review_passed"] = False

        background_tasks[task_id]["status"] = "saving"
        background_tasks[task_id]["progress"] = 80

        save_topic = topic or " vs ".join([c["title"][:20] for c in collected[:4]])
        filepath = save_compare(save_topic, content)
        vault_index.scan()

        background_tasks[task_id]["status"] = "completed"
        background_tasks[task_id]["progress"] = 100
        background_tasks[task_id]["result_file"] = str(filepath)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    except Exception as e:
        background_tasks[task_id]["status"] = "failed"
        background_tasks[task_id]["error"] = str(e)
        background_tasks[task_id]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")


@router.post("/survey", response_model=TaskResponse)
async def create_survey(request: SurveyRequest, user=Depends(require_role(["admin", "core"]))):
    _cleanup_old_tasks()
    if not request.items:
        raise HTTPException(status_code=400, detail="请至少选择 1 个项目")

    task_id = f"survey_{int(time.time())}"
    background_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "type": "survey",
        "items": [item.dict() for item in request.items],
        "topic": request.topic,
        "prompt": request.prompt,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    thread = threading.Thread(
        target=_run_survey_task,
        args=(task_id, [item.dict() for item in request.items], request.topic, request.prompt),
    )
    thread.daemon = True
    thread.start()
    return TaskResponse(task_id=task_id, status="running")


@router.post("/compare", response_model=TaskResponse)
async def create_compare(request: CompareRequest, user=Depends(require_role(["admin", "core"]))):
    _cleanup_old_tasks()
    if len(request.items) < 2:
        raise HTTPException(status_code=400, detail="至少需要选择 2 个项目进行对比")

    task_id = f"compare_{int(time.time())}"
    background_tasks[task_id] = {
        "status": "running",
        "progress": 0,
        "type": "compare",
        "items": [item.dict() for item in request.items],
        "topic": request.topic,
        "prompt": request.prompt,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    thread = threading.Thread(
        target=_run_compare_task,
        args=(task_id, [item.dict() for item in request.items], request.topic, request.prompt),
    )
    thread.daemon = True
    thread.start()
    return TaskResponse(task_id=task_id, status="running")


@router.get("/task/{task_id}")
async def get_task_status(task_id: str, user=Depends(require_role(["admin", "core", "maintainer"]))):
    if task_id not in background_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return background_tasks[task_id]


@router.get("/search-items", response_model=SearchItemsResponse)
async def search_items(
    q: str = Query("", alias="q"),
    type_filter: Optional[str] = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user=Depends(require_role(["admin", "core", "maintainer", "general"])),
):
    """搜索所有知识库项目（原文 + wiki 页面），供综述/对比选择器使用"""
    items = []
    query_lower = q.lower() if q else ""

    if not type_filter or type_filter == "raw":
        if RAW_DIR.exists():
            for md_file in sorted(RAW_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
                title = md_file.stem
                if query_lower and query_lower not in title.lower():
                    continue
                from datetime import datetime
                items.append(SearchItem(
                    id=md_file.stem,
                    title=title,
                    type="raw",
                    tags=[],
                    updated=datetime.fromtimestamp(md_file.stat().st_mtime).strftime("%Y-%m-%d"),
                ))

    for page_id, page_info in vault_index.pages.items():
        if type_filter and page_info["type"] != type_filter:
            continue
        if query_lower:
            title = page_info.get("title", "").lower()
            tags = " ".join(page_info.get("tags", [])).lower()
            if query_lower not in title and query_lower not in tags and query_lower not in page_id.lower():
                continue
        items.append(SearchItem(
            id=page_id,
            title=page_info.get("title", page_id),
            type=page_info.get("type", "unknown"),
            tags=page_info.get("tags", []),
            updated=page_info.get("updated", ""),
        ))

    total = len(items)
    start = (page - 1) * page_size
    items = items[start:start + page_size]
    return SearchItemsResponse(items=items, total=total)


@router.get("/list", response_model=SynthesisListResponse)
async def list_syntheses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type_filter: Optional[str] = Query(None, alias="type"),
    user=Depends(require_role(["admin", "core", "maintainer", "general"])),
):
    items = []
    for page_id, info in vault_index.pages.items():
        page_type = info.get("type", "")
        if page_type not in ("survey", "comparison"):
            continue
        if type_filter and page_type != type_filter:
            continue
        items.append(SynthesisItem(
            id=page_id,
            title=info.get("title", page_id),
            type=page_type,
            tags=info.get("tags", []),
            updated=info.get("updated", ""),
            query_origin="",
        ))

    total = len(items)
    start = (page - 1) * page_size
    items = items[start:start + page_size]
    return SynthesisListResponse(items=items, total=total)


def _markdown_to_story(md_text: str, title: str, font_name: str) -> list:
    """将 Markdown 文本转换为 reportlab flowable story 列表，支持表格/代码块/粗斜体/链接"""
    import markdown
    from html.parser import HTMLParser
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Preformatted, HRFlowable

    base_styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "MDTitle", parent=base_styles["Heading1"],
        fontName=font_name, fontSize=18, spaceAfter=20,
    )
    h2_style = ParagraphStyle(
        "MDH2", parent=base_styles["Heading2"],
        fontName=font_name, fontSize=14, spaceBefore=15, spaceAfter=8,
    )
    h3_style = ParagraphStyle(
        "MDH3", parent=base_styles["Heading3"],
        fontName=font_name, fontSize=12, spaceBefore=10, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "MDBody", parent=base_styles["Normal"],
        fontName=font_name, fontSize=11, leading=18,
    )
    code_style = ParagraphStyle(
        "MDCode", parent=base_styles["Code"],
        fontName="Courier", fontSize=9, leading=12,
        leftIndent=12, rightIndent=12, spaceBefore=6, spaceAfter=6,
        backColor=colors.Color(0.95, 0.95, 0.95),
    )
    quote_style = ParagraphStyle(
        "MDQuote", parent=body_style,
        leftIndent=20, textColor=colors.Color(0.4, 0.4, 0.4),
        borderLeftWidth=3, borderLeftColor=colors.Color(0.7, 0.7, 0.7),
        borderLeftPadding=8,
    )

    html = markdown.markdown(md_text, extensions=['extra', 'sane_lists'])

    story = [Paragraph(title, title_style), Spacer(1, 20)]

    cell_style = ParagraphStyle(
        "CellStyle", parent=body_style, fontSize=10, leading=14,
    )

    class _Builder(HTMLParser):
        def __init__(self):
            super().__init__()
            self._story = []
            self._buf = []
            self._tag_stack = []
            self._table_rows = []
            self._table_cell_buf = []
            self._in_cell = False
            self._in_pre = False
            self._in_li = False
            self._li_buf = []
            self._list_type = None
            self._li_counter = 0
            self._skip_tags = {'html', 'head', 'body', 'div'}

        def _flush_p(self):
            text = "".join(self._buf).strip()
            self._buf.clear()
            if not text:
                return
            self._story.append(Paragraph(text, body_style))

        def _flush_li(self):
            text = "".join(self._li_buf).strip()
            self._li_buf.clear()
            if not text:
                return
            if self._list_type == 'ol':
                self._li_counter += 1
                prefix = f"{self._li_counter}. "
            else:
                prefix = "• "
            self._story.append(Paragraph(prefix + text, body_style))

        def handle_starttag(self, tag, attrs):
            tagl = tag.lower()
            if tagl in self._skip_tags:
                return
            self._tag_stack.append(tagl)

            if tagl in ('h2', 'h3', 'h4', 'p'):
                pass
            elif tagl == 'pre':
                self._in_pre = True
                self._buf.clear()
            elif tagl == 'code':
                if not self._in_pre:
                    self._buf.append('<font face="Courier" color="#c7254e">')
            elif tagl in ('strong', 'b'):
                self._buf.append('<b>')
            elif tagl in ('em', 'i'):
                self._buf.append('<i>')
            elif tagl == 'a':
                href = dict(attrs).get('href', '')
                if href:
                    self._buf.append(f'<a href="{href}"><u>')
            elif tagl == 'table':
                self._table_rows = []
            elif tagl == 'thead':
                pass
            elif tagl == 'tbody':
                pass
            elif tagl == 'tr':
                self._table_rows.append([])
            elif tagl in ('td', 'th'):
                self._in_cell = True
                self._table_cell_buf.clear()
            elif tagl == 'ul':
                self._list_type = 'ul'
                self._li_counter = 0
            elif tagl == 'ol':
                self._list_type = 'ol'
                self._li_counter = 0
            elif tagl == 'li':
                self._in_li = True
                self._li_buf.clear()
            elif tagl == 'hr':
                self._story.append(HRFlowable(width="100%", thickness=1, color=colors.Color(0.8, 0.8, 0.8)))
                self._story.append(Spacer(1, 8))
            elif tagl == 'blockquote':
                pass
            elif tagl == 'img':
                pass

        def handle_endtag(self, tag):
            tagl = tag.lower()
            if tagl in self._skip_tags:
                return
            if self._tag_stack:
                self._tag_stack.pop()

            if tagl == 'pre':
                self._in_pre = False
                code_text = "".join(self._buf).rstrip('\n')
                self._buf.clear()
                if code_text:
                    self._story.append(Preformatted(code_text, code_style))
            elif tagl == 'code':
                if not self._in_pre:
                    self._buf.append('</font>')
            elif tagl == 'h2':
                text = "".join(self._buf).strip()
                self._buf.clear()
                if text:
                    self._story.append(Paragraph(text, h2_style))
            elif tagl == 'h3':
                text = "".join(self._buf).strip()
                self._buf.clear()
                if text:
                    self._story.append(Paragraph(text, h3_style))
            elif tagl == 'h4':
                text = "".join(self._buf).strip()
                self._buf.clear()
                if text:
                    self._story.append(Paragraph("<b>" + text + "</b>", body_style))
            elif tagl == 'p':
                self._flush_p()
                self._story.append(Spacer(1, 4))
            elif tagl in ('strong', 'b'):
                self._buf.append('</b>')
            elif tagl in ('em', 'i'):
                self._buf.append('</i>')
            elif tagl == 'a':
                self._buf.append('</u></a>')
            elif tagl == 'table':
                if self._table_rows:
                    col_count = max((len(r) for r in self._table_rows), default=1)
                    max_per_col = []
                    for c in range(col_count):
                        max_w = 0
                        for r in self._table_rows:
                            if c < len(r):
                                max_w = max(max_w, len(r[c]))
                        max_per_col.append(max_w)
                    total_max = sum(max_per_col) or 1
                    page_w = A4[0] - 72
                    col_widths = [max(page_w * w / total_max, 40) for w in max_per_col]

                    cell_data = []
                    for row in self._table_rows:
                        cell_row = []
                        for text in row:
                            cell_row.append(Paragraph(text, cell_style))
                        while len(cell_row) < col_count:
                            cell_row.append(Paragraph("", cell_style))
                        cell_data.append(cell_row)

                    tbl = Table(cell_data, colWidths=col_widths)
                    tbl.setStyle(TableStyle([
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.6, 0.6, 0.6)),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ]))
                    self._story.append(tbl)
                    self._story.append(Spacer(1, 8))
                self._table_rows = []
            elif tagl == 'tr':
                pass
            elif tagl in ('td', 'th'):
                self._in_cell = False
                cell_text = "".join(self._table_cell_buf).strip()
                self._table_cell_buf.clear()
                if self._table_rows:
                    self._table_rows[-1].append(cell_text)
            elif tagl == 'li':
                self._in_li = False
                self._flush_li()
            elif tagl in ('ul', 'ol'):
                self._list_type = None
                self._li_counter = 0
            elif tagl == 'blockquote':
                self._flush_p()
            elif tagl == 'img':
                pass

        def handle_data(self, data):
            if self._in_pre:
                self._buf.append(data)
            elif self._in_cell:
                self._table_cell_buf.append(data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            elif self._in_li:
                self._li_buf.append(data)
            else:
                self._buf.append(data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    builder = _Builder()
    builder.feed(html)
    story.extend(builder._story)
    return story


@router.get("/export-pdf/{page_id:path}")
async def export_synthesis_pdf(
    page_id: str,
    token: Optional[str] = Query(None),
    user=Depends(require_role(["admin", "core", "maintainer", "general"])),
):
    """导出综述/对比为 PDF"""
    import io
    import traceback
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from fastapi.responses import StreamingResponse

    try:
        if page_id not in vault_index.pages:
            raise HTTPException(status_code=404, detail="页面不存在")

        page_info = vault_index.pages[page_id]
        file_path = Path(page_info["file_path"])

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        content = file_path.read_text(encoding="utf-8")

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()

        title = page_info.get("title", page_id)

        font_paths = [
            ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
            ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
        ]

        font_name = "Helvetica"
        for font_path, fname in font_paths:
            if Path(font_path).exists():
                try:
                    if fname not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(fname, font_path))
                    font_name = fname
                    break
                except Exception:
                    pass

        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)

        story = _markdown_to_story(content, title, font_name)

        doc.build(story)
        pdf_buffer.seek(0)

        from urllib.parse import quote
        filename = f"{title}.pdf"
        encoded_filename = quote(filename)

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"PDF export error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF 导出失败: {str(e)}")
