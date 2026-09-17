#!/usr/bin/env python3
"""Validate an objective Xiaohongshu publishing-package contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_VISIBILITY = {"公开可见", "仅自己可见", "仅互关好友可见"}


class PackageValidationError(ValueError):
    """Raised when a Xiaohongshu package violates an objective contract."""


def _title_width(text: str) -> int:
    """Count CJK/full-width characters as two and ASCII as one."""

    return sum(1 if ord(character) < 128 else 2 for character in text)


def _existing_absolute_file(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackageValidationError(f"{label}不能为空")
    path = Path(value)
    if not path.is_absolute():
        raise PackageValidationError(f"{label}必须使用绝对路径")
    normalized = path.resolve()
    if not normalized.is_file():
        raise PackageValidationError(f"{label}不存在：{normalized}")
    return str(normalized)


def validate_xhs_package(
    data: Mapping[str, Any], expected_source_sha256: Optional[str] = None
) -> Dict[str, Any]:
    """Return a normalized package plus deterministic content fingerprint."""

    if data.get("schema_version") != 1:
        raise PackageValidationError("小红书包 schema_version 必须为 1")

    source_sha256 = data.get("source_sha256")
    if not isinstance(source_sha256, str) or not SHA256_RE.fullmatch(source_sha256):
        raise PackageValidationError("小红书包源指纹必须是 64 位小写 SHA-256")
    if expected_source_sha256 is not None and source_sha256 != expected_source_sha256:
        raise PackageValidationError("小红书包与统一内容包的源指纹不一致")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise PackageValidationError("小红书标题不能为空")
    title = title.strip()
    if _title_width(title) > 40:
        raise PackageValidationError("小红书标题超过 20 个全角字符的等效上限")

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise PackageValidationError("小红书正文不能为空")
    content = content.strip()
    if len(content) > 1000:
        raise PackageValidationError("小红书正文不得超过 1000 个字符")

    tags = data.get("tags")
    if not isinstance(tags, list) or not 1 <= len(tags) <= 10:
        raise PackageValidationError("小红书标签必须为 1 至 10 个")
    normalized_tags = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            raise PackageValidationError("小红书标签不能为空")
        normalized = tag.strip()
        if "#" in normalized or "\n" in normalized or len(normalized) > 20:
            raise PackageValidationError("小红书标签不得包含 #、换行或超过 20 个字符")
        normalized_tags.append(normalized)
    if len(normalized_tags) != len(set(normalized_tags)):
        raise PackageValidationError("小红书标签不得重复")

    images = data.get("images")
    if not isinstance(images, list) or not 1 <= len(images) <= 18:
        raise PackageValidationError("小红书图片必须为 1 至 18 张")
    normalized_images = [
        _existing_absolute_file(value, f"小红书图片 {index}")
        for index, value in enumerate(images, start=1)
    ]

    visibility = data.get("visibility")
    if visibility not in ALLOWED_VISIBILITY:
        raise PackageValidationError("小红书可见范围不受支持")
    declare_original = data.get("declare_original")
    if not isinstance(declare_original, bool):
        raise PackageValidationError("小红书原创选项必须是布尔值")

    normalized_result: Dict[str, Any] = {
        "schema_version": 1,
        "source_sha256": source_sha256,
        "title": title,
        "content": content,
        "tags": normalized_tags,
        "images": normalized_images,
        "visibility": visibility,
        "declare_original": declare_original,
    }
    canonical = json.dumps(
        normalized_result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    normalized_result["fingerprint"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    return normalized_result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验小红书发布包")
    parser.add_argument("--package", required=True, type=Path, help="小红书发布包 JSON")
    parser.add_argument("--expected-source-sha256", help="统一内容包源指纹")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        data = json.loads(args.package.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise PackageValidationError("小红书发布包必须是 JSON 对象")
        result = validate_xhs_package(data, args.expected_source_sha256)
    except (OSError, UnicodeError, json.JSONDecodeError, PackageValidationError) as exc:
        print(f"小红书发布包校验失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
