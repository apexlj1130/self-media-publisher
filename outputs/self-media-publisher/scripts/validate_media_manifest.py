#!/usr/bin/env python3
"""Validate the deterministic media-path contract for one publishing run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PackageValidationError(ValueError):
    """Raised when a run package violates an objective contract."""


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise PackageValidationError(f"{label}必须是 64 位小写 SHA-256")
    return value


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


def validate_media_manifest(
    data: Mapping[str, Any], package: Mapping[str, Any]
) -> Dict[str, Any]:
    """Return a normalized manifest or raise ``PackageValidationError``."""

    if data.get("schema_version") != 1:
        raise PackageValidationError("媒体清单 schema_version 必须为 1")
    if package.get("schema_version") != 2:
        raise PackageValidationError("统一内容包 schema_version 必须为 2")

    package_sha = _require_sha256(package.get("source_sha256"), "内容包源指纹")
    manifest_sha = _require_sha256(data.get("source_sha256"), "媒体清单源指纹")
    if manifest_sha != package_sha:
        raise PackageValidationError("媒体清单与内容包的源指纹不一致")

    images = package.get("images")
    if not isinstance(images, list) or not images:
        raise PackageValidationError("统一内容包缺少图片任务")
    image_ids = []
    for image in images:
        if not isinstance(image, Mapping) or not isinstance(image.get("id"), str):
            raise PackageValidationError("统一内容包包含无效图片 ID")
        image_ids.append(image["id"])
    if len(image_ids) != len(set(image_ids)):
        raise PackageValidationError("统一内容包图片 ID 重复")

    wechat = data.get("wechat")
    if not isinstance(wechat, Mapping):
        raise PackageValidationError("媒体清单缺少微信图片映射")
    missing = [image_id for image_id in image_ids if image_id not in wechat]
    extra = [image_id for image_id in wechat if image_id not in image_ids]
    if missing or extra:
        raise PackageValidationError(
            f"微信图片映射必须与内容包一致；缺少={missing}，多余={extra}"
        )
    normalized_wechat = {
        image_id: _existing_absolute_file(wechat[image_id], f"微信图片 {image_id}")
        for image_id in image_ids
    }

    xhs_images = data.get("xiaohongshu")
    if not isinstance(xhs_images, list) or not 1 <= len(xhs_images) <= 18:
        raise PackageValidationError("小红书图片必须为 1 至 18 张")
    normalized_xhs = [
        _existing_absolute_file(value, f"小红书图片 {index}")
        for index, value in enumerate(xhs_images, start=1)
    ]

    return {
        "schema_version": 1,
        "source_sha256": manifest_sha,
        "wechat": normalized_wechat,
        "xiaohongshu": normalized_xhs,
    }


def _load_mapping(path: Path, label: str) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise PackageValidationError(f"{label}必须是 JSON 对象")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验双平台媒体清单")
    parser.add_argument("--manifest", required=True, type=Path, help="媒体清单 JSON")
    parser.add_argument("--package", required=True, type=Path, help="统一内容包 JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = validate_media_manifest(
            _load_mapping(args.manifest, "媒体清单"),
            _load_mapping(args.package, "统一内容包"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, PackageValidationError) as exc:
        print(f"媒体清单校验失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
