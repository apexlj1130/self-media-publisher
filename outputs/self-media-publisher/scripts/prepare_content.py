#!/usr/bin/env python3
"""Prepare one Markdown source for WeChat and Xiaohongshu publishing.

The script performs deterministic parsing and renders a conservative staging
document. It does not open a browser, generate images, or make publishing
decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ILLUSTRATION_HEADING = "# 配图与插图建议"
LAYOUT_HEADING = "## 给 Codex 的发布与排版要求"
IMAGE_HEADER_RE = re.compile(r"^##\s+配图\s*(\d+)\s*[：:]\s*(.+?)\s*$")
FIELD_RE = re.compile(r"^\*\*(位置|作用|尺寸建议|可直接使用的提示词)[：:]\*\*\s*(.*)$")
HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
H2_NUMBER_RE = re.compile(r"^([一二三四五六七八九十]+)[、.．]\s*(.+)$")
CN_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


class ParseError(ValueError):
    """Raised when an article cannot satisfy the input contract."""


def _normalise(markdown: str) -> str:
    return markdown.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")


def _first_h1(lines: Sequence[str]) -> Tuple[int, str]:
    for index, line in enumerate(lines):
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return index, match.group(1).strip()
    raise ParseError("缺少文章一级标题")


def _find_exact_heading(lines: Sequence[str], heading: str, start: int = 0) -> int:
    for index in range(start, len(lines)):
        if lines[index].strip() == heading:
            return index
    raise ParseError(f"缺少“{heading.lstrip('# ')}”章节")


def _split_paragraphs(lines: Iterable[str]) -> List[str]:
    paragraphs: List[str] = []
    current: List[str] = []
    for raw in lines:
        line = raw.strip()
        if line:
            current.append(line)
        elif current:
            paragraphs.append("\n".join(current))
            current = []
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def _extract_fields(lines: Sequence[str], number: int) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = FIELD_RE.match(lines[index].strip())
        if not match:
            index += 1
            continue
        label, inline_value = match.groups()
        if label != "可直接使用的提示词":
            fields[label] = inline_value.strip()
            index += 1
            continue

        prompt_lines: List[str] = []
        if inline_value.strip():
            prompt_lines.append(inline_value.strip())
        index += 1
        while index < len(lines):
            possible_field = FIELD_RE.match(lines[index].strip())
            if possible_field:
                break
            prompt_line = lines[index].strip()
            if prompt_line.startswith(">"):
                prompt_line = prompt_line[1:].lstrip()
            prompt_lines.append(prompt_line)
            index += 1
        fields[label] = "\n".join(prompt_lines).strip()

    required = ("位置", "作用", "尺寸建议", "可直接使用的提示词")
    for label in required:
        if not fields.get(label, "").strip():
            raise ParseError(f"配图 {number} 缺少{label}")
    return fields


def _parse_headings(body: str) -> List[Dict[str, Any]]:
    headings: List[Dict[str, Any]] = []
    h2_index = 0
    for line in body.splitlines():
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        level = len(match.group(1))
        if level != 2:
            continue
        h2_index += 1
        text = match.group(2).strip()
        headings.append({"index": h2_index, "level": 2, "text": text})
    return headings


def _section_number_from_text(text: str) -> Optional[int]:
    patterns = (
        r"[“\"]([一二三四五六七八九十]+)[、.．]",
        r"第([一二三四五六七八九十]+)(?:章|节|部分)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return CN_NUMBERS.get(match.group(1))
    return None


def _heading_body(text: str) -> str:
    match = H2_NUMBER_RE.match(text)
    return match.group(2).strip() if match else text.strip()


def _choose_heading(position_text: str, headings: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    explicit = _section_number_from_text(position_text)
    if explicit is not None:
        return next((item for item in headings if item["index"] == explicit), None)

    for heading in headings:
        body = _heading_body(str(heading["text"]))
        if len(body) >= 4 and body in position_text:
            return heading

    position_words = set(re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", position_text))
    for heading in headings:
        heading_words = set(re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", str(heading["text"])))
        distinctive = (position_words & heading_words) - {"Agent", "AI"}
        if distinctive:
            return heading
    return None


def _make_anchor(
    kind: str,
    position_text: str,
    headings: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    if kind == "cover" or "正文最前面" in position_text:
        return {"heading_index": None, "heading_text": None, "placement": "cover"}

    heading = _choose_heading(position_text, headings)
    placement = "after_section"
    if "之前" in position_text or "中，" in position_text or "中," in position_text:
        placement = "review_within_section"
    return {
        "heading_index": heading["index"] if heading else None,
        "heading_text": heading["text"] if heading else None,
        "placement": placement if heading else "review_within_section",
    }


def parse_content(markdown: str) -> Dict[str, Any]:
    """Parse the supported source format into a stable content package."""

    source = _normalise(markdown)
    lines = source.split("\n")
    title_index, title = _first_h1(lines)
    illustration_index = _find_exact_heading(lines, ILLUSTRATION_HEADING, title_index + 1)
    layout_index = _find_exact_heading(lines, LAYOUT_HEADING, illustration_index + 1)

    body = "\n".join(lines[title_index + 1 : illustration_index]).strip()
    if not body:
        raise ParseError("文章正文为空")
    headings = _parse_headings(body)

    image_lines = lines[illustration_index + 1 : layout_index]
    image_starts: List[Tuple[int, int, str]] = []
    for index, line in enumerate(image_lines):
        match = IMAGE_HEADER_RE.match(line.strip())
        if match:
            image_starts.append((index, int(match.group(1)), match.group(2).strip()))
    if not image_starts:
        raise ParseError("配图与插图建议中没有配图任务")

    numbers = [number for _, number, _ in image_starts]
    if len(numbers) != len(set(numbers)):
        raise ParseError("配图编号重复")
    if numbers != list(range(1, len(numbers) + 1)):
        raise ParseError("配图编号必须从 1 开始连续递增")

    images: List[Dict[str, Any]] = []
    for offset, (start, number, name) in enumerate(image_starts):
        end = image_starts[offset + 1][0] if offset + 1 < len(image_starts) else len(image_lines)
        fields = _extract_fields(image_lines[start + 1 : end], number)
        kind = "cover" if "封面" in name or "正文最前面" in fields["位置"] else "inline"
        images.append(
            {
                "id": f"image-{number:02d}",
                "number": number,
                "name": name,
                "kind": kind,
                "position_text": fields["位置"],
                "purpose": fields["作用"],
                "aspect_ratio": fields["尺寸建议"],
                "prompt": fields["可直接使用的提示词"],
                "anchor": _make_anchor(kind, fields["位置"], headings),
            }
        )

    layout_instructions = _split_paragraphs(lines[layout_index + 1 :])
    if not layout_instructions:
        raise ParseError("发布与排版要求为空")

    return {
        "schema_version": 2,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "default_platforms": ["wechat", "xiaohongshu"],
        "title": title,
        "body_markdown": body,
        "headings": headings,
        "images": images,
        "layout_instructions": layout_instructions,
        "publish_options": {"declare_original": True},
    }


def _inline_markup(text: str) -> str:
    value = html.escape(text, quote=True)
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2" style="color:#1f5f8b;text-decoration:none;">\1</a>',
        value,
    )
    value = re.sub(r"`([^`]+)`", r'<code style="font-family:Menlo,monospace;background:#f2f5f7;padding:2px 4px;border-radius:3px;">\1</code>', value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    return value


def _image_marker(image: Mapping[str, Any]) -> str:
    review = ""
    if image["anchor"]["placement"] == "review_within_section":
        review = " · 需按语义复核位置"
    return (
        f'<section data-image-id="{html.escape(str(image["id"]))}" '
        'style="margin:24px 0;padding:12px;border:1px dashed #7aa8c4;color:#315a70;'
        'font-size:13px;text-align:center;background:#f4f9fc;">'
        f'待插入配图 {image["number"]}：{html.escape(str(image["name"]))}'
        f'{html.escape(review)}</section>'
    )


def _markers_by_section(images: Sequence[Mapping[str, Any]]) -> Dict[int, List[Mapping[str, Any]]]:
    result: Dict[int, List[Mapping[str, Any]]] = {}
    for image in images:
        if image["kind"] == "cover":
            continue
        index = image["anchor"].get("heading_index")
        if index is None:
            index = 10**9
        result.setdefault(int(index), []).append(image)
    return result


def _render_blocks(body: str, images: Sequence[Mapping[str, Any]]) -> str:
    lines = body.splitlines()
    rendered: List[str] = []
    markers = _markers_by_section(images)
    section_index = 0
    paragraph: List[str] = []
    list_items: List[Tuple[bool, str]] = []
    quote_lines: List[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = "<br>".join(_inline_markup(item.strip()) for item in paragraph)
            rendered.append(f'<p style="margin:0 0 16px;">{text}</p>')
            paragraph.clear()

    def flush_list() -> None:
        if not list_items:
            return
        ordered = list_items[0][0]
        tag = "ol" if ordered else "ul"
        items = "".join(f"<li>{_inline_markup(value)}</li>" for _, value in list_items)
        rendered.append(f'<{tag} style="margin:0 0 18px;padding-left:1.5em;">{items}</{tag}>')
        list_items.clear()

    def flush_quote() -> None:
        if quote_lines:
            text = "<br>".join(_inline_markup(item) for item in quote_lines if item)
            rendered.append(
                '<blockquote style="margin:18px 0;padding:12px 16px;border-left:3px solid #2c7ca6;'
                f'background:#f3f8fb;color:#315269;">{text}</blockquote>'
            )
            quote_lines.clear()

    def flush_all() -> None:
        flush_paragraph()
        flush_list()
        flush_quote()

    def append_section_markers(index: int) -> None:
        for image in markers.pop(index, []):
            rendered.append(_image_marker(image))

    for raw in lines:
        stripped = raw.strip()
        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            flush_all()
            level = len(heading_match.group(1))
            if level == 2:
                if section_index:
                    append_section_markers(section_index)
                section_index += 1
                rendered.append(
                    '<h2 style="margin:34px 0 18px;color:#154f73;font-size:20px;line-height:1.45;'
                    f'font-weight:700;">{_inline_markup(heading_match.group(2))}</h2>'
                )
            else:
                rendered.append(
                    '<h3 style="margin:26px 0 14px;color:#243746;font-size:17px;line-height:1.5;'
                    f'font-weight:700;">{_inline_markup(heading_match.group(2))}</h3>'
                )
            continue

        if stripped == "---":
            flush_all()
            rendered.append('<hr style="border:0;border-top:1px solid #dce5ea;margin:30px 0;">')
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            flush_list()
            quote_lines.append(stripped[1:].lstrip())
            continue

        unordered = re.match(r"^-\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.、]\s*(.+)$", stripped)
        if unordered or ordered:
            flush_paragraph()
            flush_quote()
            is_ordered = ordered is not None
            value = (ordered or unordered).group(1)
            if list_items and list_items[0][0] != is_ordered:
                flush_list()
            list_items.append((is_ordered, value))
            continue

        if not stripped:
            flush_all()
            continue

        flush_list()
        flush_quote()
        paragraph.append(stripped)

    flush_all()
    if section_index:
        append_section_markers(section_index)
    for index in sorted(markers):
        for image in markers[index]:
            rendered.append(_image_marker(image))
    return "\n".join(rendered)


def render_wechat_staging_html(package: Mapping[str, Any]) -> str:
    """Render a browser-copyable staging document without the article H1."""

    article = _render_blocks(str(package["body_markdown"]), package["images"])
    title = html.escape(str(package["title"]), quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · 微信排版暂存稿</title>
</head>
<body style="margin:0;background:#eef3f6;padding:32px 12px;">
  <article class="wechat-article">
    <section style="max-width:720px;margin:0 auto;padding:30px 26px;background:#ffffff;color:#303842;font-size:16px;line-height:1.8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;word-break:break-word;">
{article}
    </section>
  </article>
</body>
</html>
"""


def write_content_package(source_path: Path, output_dir: Path) -> Tuple[Path, Path]:
    """Write the shared JSON package and WeChat staging HTML."""

    source_path = source_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    markdown = source_path.read_text(encoding="utf-8")
    package = parse_content(markdown)
    output_dir.mkdir(parents=True, exist_ok=True)
    wechat_dir = output_dir / "wechat"
    wechat_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "content-package.json"
    html_path = wechat_dir / "article-staging.html"
    json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_wechat_staging_html(package), encoding="utf-8")
    return json_path, html_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="解析双平台素材并生成统一内容包")
    parser.add_argument("source", type=Path, help="UTF-8 Markdown 原稿")
    parser.add_argument("--output-dir", required=True, type=Path, help="运行输出目录")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        json_path, html_path = write_content_package(args.source, args.output_dir)
    except (OSError, UnicodeError, ParseError) as exc:
        print(f"准备文章失败：{exc}", file=sys.stderr)
        return 2
    print(json_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
