#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MEDIA_SCRIPT = SKILL_ROOT / "scripts" / "validate_media_manifest.py"
XHS_SCRIPT = SKILL_ROOT / "scripts" / "validate_xhs_package.py"
SOURCE_SHA256 = "a" * 64


def load_module(path: Path, name: str):
    if not path.exists():
        raise AssertionError(f"{path.name} 尚未实现")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载 {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PackageValidatorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.cover = self.root / "cover.png"
        self.inline = self.root / "inline.png"
        self.cover.write_bytes(b"synthetic-cover")
        self.inline.write_bytes(b"synthetic-inline")

    def content_package(self):
        return {
            "schema_version": 2,
            "source_sha256": SOURCE_SHA256,
            "images": [
                {"id": "image-01", "kind": "cover"},
                {"id": "image-02", "kind": "inline"},
            ],
        }

    def media_manifest(self):
        return {
            "schema_version": 1,
            "source_sha256": SOURCE_SHA256,
            "wechat": {
                "image-01": str(self.cover),
                "image-02": str(self.inline),
            },
            "xiaohongshu": [str(self.cover), str(self.inline)],
        }

    def xhs_package(self):
        return {
            "schema_version": 1,
            "source_sha256": SOURCE_SHA256,
            "title": "Agent 开发到底难在哪",
            "content": "代码少了，但运行时的不确定性没有消失。",
            "tags": ["AI", "Agent"],
            "images": [str(self.cover), str(self.inline)],
            "visibility": "公开可见",
            "declare_original": True,
        }

    def test_accepts_and_normalizes_media_manifest(self):
        module = load_module(MEDIA_SCRIPT, "validate_media_manifest")
        result = module.validate_media_manifest(
            self.media_manifest(), self.content_package()
        )

        self.assertEqual(result["wechat"]["image-01"], str(self.cover))
        self.assertEqual(result["xiaohongshu"], [str(self.cover), str(self.inline)])

    def test_rejects_invalid_media_manifest_contracts(self):
        module = load_module(MEDIA_SCRIPT, "validate_media_manifest_invalid")
        cases = []

        wrong_sha = self.media_manifest()
        wrong_sha["source_sha256"] = "b" * 64
        cases.append((wrong_sha, "源指纹"))

        missing_wechat = self.media_manifest()
        del missing_wechat["wechat"]["image-02"]
        cases.append((missing_wechat, "微信图片"))

        relative_path = self.media_manifest()
        relative_path["wechat"]["image-01"] = "cover.png"
        cases.append((relative_path, "绝对路径"))

        missing_path = self.media_manifest()
        missing_path["wechat"]["image-01"] = str(self.root / "missing.png")
        cases.append((missing_path, "不存在"))

        no_xhs_images = self.media_manifest()
        no_xhs_images["xiaohongshu"] = []
        cases.append((no_xhs_images, "小红书图片"))

        for manifest, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(module.PackageValidationError, message):
                    module.validate_media_manifest(manifest, self.content_package())

    def test_accepts_xhs_package_and_adds_fingerprint(self):
        module = load_module(XHS_SCRIPT, "validate_xhs_package")
        result = module.validate_xhs_package(
            self.xhs_package(), expected_source_sha256=SOURCE_SHA256
        )

        self.assertRegex(result["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["images"], [str(self.cover), str(self.inline)])

    def test_rejects_invalid_xhs_text_and_tags(self):
        module = load_module(XHS_SCRIPT, "validate_xhs_package_text")
        cases = []

        empty_title = self.xhs_package()
        empty_title["title"] = "   "
        cases.append((empty_title, "标题"))

        long_title = self.xhs_package()
        long_title["title"] = "长" * 21
        cases.append((long_title, "标题"))

        long_ascii_title = self.xhs_package()
        long_ascii_title["title"] = "a" * 41
        cases.append((long_ascii_title, "标题"))

        empty_content = self.xhs_package()
        empty_content["content"] = ""
        cases.append((empty_content, "正文"))

        long_content = self.xhs_package()
        long_content["content"] = "文" * 1001
        cases.append((long_content, "正文"))

        hash_tag = self.xhs_package()
        hash_tag["tags"] = ["#AI"]
        cases.append((hash_tag, "标签"))

        duplicate_tags = self.xhs_package()
        duplicate_tags["tags"] = ["AI", "AI"]
        cases.append((duplicate_tags, "标签"))

        for package, message in cases:
            with self.subTest(title=package["title"][:10], message=message):
                with self.assertRaisesRegex(module.PackageValidationError, message):
                    module.validate_xhs_package(package)

    def test_rejects_invalid_xhs_images_and_options(self):
        module = load_module(XHS_SCRIPT, "validate_xhs_package_options")
        cases = []

        no_images = self.xhs_package()
        no_images["images"] = []
        cases.append((no_images, "图片"))

        too_many_images = self.xhs_package()
        too_many_images["images"] = [str(self.cover)] * 19
        cases.append((too_many_images, "图片"))

        relative_image = self.xhs_package()
        relative_image["images"] = ["cover.png"]
        cases.append((relative_image, "绝对路径"))

        missing_image = self.xhs_package()
        missing_image["images"] = [str(self.root / "missing.png")]
        cases.append((missing_image, "不存在"))

        bad_visibility = self.xhs_package()
        bad_visibility["visibility"] = "所有人"
        cases.append((bad_visibility, "可见范围"))

        bad_original = self.xhs_package()
        bad_original["declare_original"] = "yes"
        cases.append((bad_original, "原创"))

        for package, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(module.PackageValidationError, message):
                    module.validate_xhs_package(package)

    def test_validator_clis_emit_json_and_use_exit_two_for_contract_errors(self):
        content_path = self.root / "content-package.json"
        manifest_path = self.root / "media-manifest.json"
        xhs_path = self.root / "xhs-package.json"
        content_path.write_text(json.dumps(self.content_package()), encoding="utf-8")
        manifest_path.write_text(json.dumps(self.media_manifest()), encoding="utf-8")
        xhs_path.write_text(json.dumps(self.xhs_package()), encoding="utf-8")

        media_result = subprocess.run(
            [
                sys.executable,
                str(MEDIA_SCRIPT),
                "--manifest",
                str(manifest_path),
                "--package",
                str(content_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(media_result.returncode, 0, media_result.stderr)
        self.assertEqual(json.loads(media_result.stdout)["source_sha256"], SOURCE_SHA256)

        xhs_result = subprocess.run(
            [
                sys.executable,
                str(XHS_SCRIPT),
                "--package",
                str(xhs_path),
                "--expected-source-sha256",
                SOURCE_SHA256,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(xhs_result.returncode, 0, xhs_result.stderr)
        self.assertRegex(json.loads(xhs_result.stdout)["fingerprint"], r"^[0-9a-f]{64}$")

        invalid = self.media_manifest()
        invalid["xiaohongshu"] = []
        manifest_path.write_text(json.dumps(invalid), encoding="utf-8")
        invalid_result = subprocess.run(
            [
                sys.executable,
                str(MEDIA_SCRIPT),
                "--manifest",
                str(manifest_path),
                "--package",
                str(content_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(invalid_result.returncode, 2)
        self.assertIn("小红书图片", invalid_result.stderr)


if __name__ == "__main__":
    unittest.main()
