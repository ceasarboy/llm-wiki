import re
import random
from pathlib import Path
from datetime import datetime

WIKI_PATH = Path("C:/Users/Administrator/Documents/Obsidian Vault/wiki")
FAQ_DIR = WIKI_PATH / "faq"

CONCEPT_DIR = WIKI_PATH / "concepts"
ENTITY_DIR = WIKI_PATH / "entities"
PAPERS_DIR = WIKI_PATH / "papers"

today = datetime.now().strftime("%Y-%m-%d")

qa_structures = {
    "concept": [
        ("什么是{name}？", "{overview}", "概念"),
        ("{name}的核心原理是什么？", "{overview}\n\n{detail}", "概念"),
        ("{name}有哪些应用场景？", "{overview}\n\n{detail}", "概念"),
        ("{name}与其他相关概念有什么区别？", "{overview}\n\n{detail}", "概念"),
    ],
    "entity": [
        ("{name}是什么？", "{overview}", "实体"),
        ("{name}的核心贡献有哪些？", "{overview}\n\n{detail}", "实体"),
        ("{name}的技术架构是怎样的？", "{overview}\n\n{detail}", "实体"),
    ],
    "paper": [
        ("{name}论文的核心观点是什么？", "{overview}\n\n**方法**：{detail}", "论文"),
        ("{name}提出了哪些创新方法？", "{overview}\n\n**方法**：{detail}", "论文"),
        ("{name}的实验结果说明了什么？", "{overview}\n\n**实验**：{detail}", "论文"),
    ],
}


def extract_title(text):
    m = re.search(r'^# (.+)', text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def extract_overview(text):
    m = re.search(r'^## 概述\n(.+?)(?=\n## |\[Source:)', text, re.MULTILINE)
    if m:
        overview = m.group(1).strip()
        return re.sub(r'\s*\[Source:\s*\*\*.+?\*\*\]', '', overview).strip()[:300]
    m = re.search(r'^## 定义\n(.+?)(?=\n## |\[Source:)', text, re.MULTILINE)
    if m:
        overview = m.group(1).strip()
        return re.sub(r'\s*\[Source:\s*\*\*.+?\*\*\]', '', overview).strip()[:300]
    m = re.search(r'^## 核心观点\n(.+?)(?=\n##|\Z)', text, re.MULTILINE | re.DOTALL)
    if m:
        overview = m.group(1).strip()[:300]
        return re.sub(r'\s*\[Source:[\s\*]+.+?[\s\*]*\]', '', overview).strip()
    first_para = re.search(r'^# .+\n\n(.+?)(?:\n#|\n##|\Z)', text, re.MULTILINE | re.DOTALL)
    if first_para:
        overview = first_para.group(1).strip()[:300]
        return re.sub(r'\s*\[Source:[\s\*]+.+?[\s\*]*\]', '', overview).strip()
    return "请参阅相关文档了解详情。"


def extract_detail(text):
    sections = []
    for m in re.finditer(r'^## (技术特点|应用场景|核心观点|方法|实验)\n(.+?)(?=\n## |\[Source:)', text, re.MULTILINE):
        content = m.group(2).strip()
        content = re.sub(r'\s*\[Source:[\s\*]+.+?[\s\*]*\]', '', content).strip()
        if len(content) > 20:
            sections.append(f"**{m.group(1)}**：{content[:250]}")
    if sections:
        return "\n\n".join(sections[:2])

    sections = []
    for m in re.finditer(r'^## (.+?)\n(.+?)(?=\n## |\[Source:)', text, re.MULTILINE):
        section_title = m.group(1).strip()
        content = m.group(2).strip()
        content = re.sub(r'\s*\[Source:[\s\*]+.+?[\s\*]*\]', '', content).strip()
        if section_title not in ("概述", "定义", "引用来源", "相关论文", "相关链接", "相关实体", "相关概念", "提取的实体", "涉及的概念") and len(content) > 20:
            sections.append(f"**{section_title}**：{content[:250]}")
        if len(sections) >= 2:
            break
    if sections:
        return "\n\n".join(sections)

    return ""


def extract_sources(text):
    sources = []
    for m in re.finditer(r'\[Source:\s*\*\*(.+?)\*\*\]', text):
        sources.append(m.group(1))
    if not sources:
        for m in re.finditer(r'## 引用来源\s*\n\s*\n?- \[(.+?)\]', text, re.DOTALL):
            sources.append(m.group(1).strip().rstrip("]").rstrip(")").split("](")[0].strip("* "))
    return list(dict.fromkeys(sources))


def extract_wikilinks(text):
    links = []
    for m in re.finditer(r'\[\[(papers|concepts|entities)/(.+?)(?:\|.*?)?\]\]', text):
        links.append(f"[[{m.group(1)}/{m.group(2)}|{m.group(2)}]]")
    return list(dict.fromkeys(links))[:3]


def extract_relevant_papers(text):
    papers = []
    for m in re.finditer(r'\[\[(?:papers|entities)/(.+?)(?:\|.*?)?\]\]', text):
        papers.append(m.group(1))
    return papers


def clean_filename(text):
    return text[:40].replace("/", "_").replace("\\", "_").replace("?", "").replace("？", "").replace("*", "").replace(":", "").replace("|", "").strip()


def create_faq(page_type, title, overview, detail, sources, wikilinks, subdir, filename_stem):
    template = random.choice(qa_structures.get(page_type, qa_structures["concept"]))
    question = template[0].format(name=title)

    source_ref = ""
    if sources:
        source_ref = " [Source: **{}**]".format(sources[0].split("](")[0].split("][")[0] if "][" in sources[0] else sources[0])

    if detail:
        answer = f"**概述**：{overview}{source_ref}\n\n{detail}"
    else:
        answer = f"**概述**：{overview}{source_ref}"

    source_lines = []
    if wikilinks:
        source_lines.append(f"- [[{subdir}/{filename_stem}|{title}]]")
    for sl in wikilinks[1:4]:
        source_lines.append(f"- {sl}")

    sources_block = ""
    if source_lines:
        sources_block = "\n\n## 来源\n\n" + "\n".join(source_lines)

    content = f"# {question}\n\n## 回答\n\n{answer}{sources_block}\n---\n_自动生成于: {datetime.now().isoformat()}_\n"

    filename = f"{today}_{clean_filename(question)}.md"
    filepath = FAQ_DIR / filename
    filepath.write_text(content, encoding="utf-8")
    return question


def cleanup_old():
    for f in FAQ_DIR.glob(f"{today}_*.md"):
        f.unlink()


def main():
    cleanup_old()
    FAQ_DIR.mkdir(parents=True, exist_ok=True)

    faqs = []
    seen_titles = set()

    for dir_path, ptype, subdir in [(CONCEPT_DIR, "concept", "concepts"), (ENTITY_DIR, "entity", "entities"), (PAPERS_DIR, "paper", "papers")]:
        if not dir_path.exists():
            continue
        files = list(dir_path.glob("*.md"))
        random.shuffle(files)
        for f in files:
            if len(faqs) >= 50:
                break
            try:
                text = f.read_text(encoding="utf-8")
                title = extract_title(text)
                if not title or title in seen_titles:
                    continue

                overview = extract_overview(text)
                detail = extract_detail(text)
                sources = extract_sources(text)
                wikilinks = extract_wikilinks(text)

                q = create_faq(ptype, title, overview, detail, sources, wikilinks, subdir, f.stem)
                if q not in seen_titles:
                    seen_titles.add(title)
                    faqs.append({"question": q, "title": title})

                if len(faqs) % 10 == 0:
                    print(f"  ... 已生成 {len(faqs)} 条FAQ")
            except Exception as e:
                print(f"  跳过 {f.name}: {e}")

    print(f"\n共有 {len(faqs)} 条FAQ，保存在 {FAQ_DIR}")

    for i, f in enumerate(faqs[:5]):
        print(f"  {i+1}. {f['question'][:70]}")

    if len(faqs) > 5:
        print("  ...")


if __name__ == "__main__":
    main()