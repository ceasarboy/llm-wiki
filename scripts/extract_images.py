"""用 PyMuPDF 直接从 PDF 提取图片（轻量快速）"""
import sys
from pathlib import Path

PDF_DIR = Path("C:/Users/Administrator/Documents/Obsidian Vault/raw/papers/pdf")
RAW_DIR = Path("C:/Users/Administrator/Documents/Obsidian Vault/raw/papers/markdown")


def extract_images_fitz(pdf_path: Path, article_id: str):
    import fitz
    doc = fitz.open(str(pdf_path))
    saved = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]

            name = f"{article_id}_page{page_num + 1}_img{img_idx + 1}.{ext}"
            dest = RAW_DIR / name
            dest.write_bytes(image_bytes)
            saved += 1

    doc.close()
    return saved


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_images.py <pdf1.pdf> [pdf2.pdf ...]")
        sys.exit(1)

    try:
        import fitz
    except ImportError:
        print("PyMuPDF not installed. Run: pip install pymupdf")
        sys.exit(1)

    for filename in sys.argv[1:]:
        pdf_path = PDF_DIR / filename
        if not pdf_path.exists():
            print(f"[{filename}] SKIP: not found")
            continue

        article_id = pdf_path.stem
        print(f"[{filename}]", end=" ", flush=True)
        count = extract_images_fitz(pdf_path, article_id)
        print(f"{count} images saved as {article_id}_page*_img*")
