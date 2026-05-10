import subprocess
import sys
import os
import json
import tempfile
from pathlib import Path
from typing import Optional, Tuple

_marker_models_loaded = None

def _convert_with_marker_api(pdf_path: Path, output_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        from marker.models import create_model_dict
        from marker.config.parser import ConfigParser
        from marker.output import save_output

        global _marker_models_loaded
        if _marker_models_loaded is None:
            _marker_models_loaded = create_model_dict()

        config_parser = ConfigParser({
            'output_format': 'markdown',
            'use_llm': False,
        })
        converter_cls = config_parser.get_converter_cls()
        converter = converter_cls(
            config=config_parser.generate_config_dict(),
            artifact_dict=_marker_models_loaded,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
            llm_service=config_parser.get_llm_service()
        )
        rendered = converter(str(pdf_path))
        save_output(rendered, str(output_dir), pdf_path.stem)

        md_files = list(output_dir.glob(f"{pdf_path.stem}*.md"))
        if md_files:
            return True, str(md_files[0]), "使用marker-pdf转换成功"

        subdir = output_dir / pdf_path.stem
        md_files = list(subdir.glob("*.md")) if subdir.exists() else []
        if md_files:
            return True, str(md_files[0]), "使用marker-pdf转换成功"

        return False, None, "marker-pdf未生成输出文件"
    except Exception as e:
        return False, None, f"marker-pdf API调用失败: {str(e)}"


def convert_pdf_to_markdown(pdf_path: Path, output_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        success, md_path, msg = _convert_with_marker_api(pdf_path, output_dir)
        if success:
            return success, md_path, msg
        return False, None, msg
    except Exception as e:
        return False, None, str(e)


def get_pdf_status(pdf_path: Path) -> dict:
    if not pdf_path.exists():
        return {"exists": False}

    stat = pdf_path.stat()
    return {
        "exists": True,
        "filename": pdf_path.name,
        "path": str(pdf_path),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }
