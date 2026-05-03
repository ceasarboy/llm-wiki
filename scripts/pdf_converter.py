import subprocess
import sys
import os
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
            'languages': 'en'
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

        return False, None, "marker-pdf未生成输出文件"
    except Exception as e:
        return False, None, f"marker-pdf API调用失败: {str(e)}"


def _convert_with_pymupdf(pdf_path: Path, output_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        markdown_content = []
        image_count = 0

        for page_num, page in enumerate(doc):
            text = page.get_text()
            markdown_content.append(f"## 第 {page_num + 1} 页\n\n{text}\n\n")

            image_list = page.get_images()
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                image_filename = f"{pdf_path.stem}_page{page_num + 1}_img{img_index + 1}.{image_ext}"
                image_path = output_dir / image_filename
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)

                markdown_content.append(f"![图片{img_index + 1}]({image_filename})\n\n")
                image_count += 1

        doc.close()

        md_path = output_dir / f"{pdf_path.stem}.md"
        md_path.write_text("".join(markdown_content), encoding='utf-8')

        return True, str(md_path), f"使用PyMuPDF转换成功，提取了 {image_count} 张图片"

    except ImportError:
        return False, None, "PyMuPDF未安装，请运行: pip install PyMuPDF"
    except Exception as e:
        return False, None, str(e)


def convert_pdf_to_markdown(pdf_path: Path, output_dir: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        success, md_path, msg = _convert_with_marker_api(pdf_path, output_dir)
        if success:
            return success, md_path, msg

        print(f"marker-pdf转换失败({msg})，尝试使用PyMuPDF...")

        success, md_path, msg = _convert_with_pymupdf(pdf_path, output_dir)
        if success:
            return success, md_path, msg

        return False, None, f"所有转换方法均失败: marker-pdf失败, PyMuPDF失败({msg})"

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
