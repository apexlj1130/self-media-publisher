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
SCRIPT = SKILL_ROOT / "scripts" / "prepare_content.py"
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "示例文章.md"


class PrepareContentTest(unittest.TestCase):
    def load_module(self):
        self.assertTrue(SCRIPT.exists(), "prepare_content.py 尚未实现")
        spec = importlib.util.spec_from_file_location("prepare_content", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def parse_sample(self):
        module = self.load_module()
        markdown = SAMPLE.read_text(encoding="utf-8")
        return module, module.parse_content(markdown)

    def test_parses_sample_article_contract(self):
        _, package = self.parse_sample()

        self.assertEqual(
            package["title"],
            "用于测试的 Agent 可观测性文章",
        )
        self.assertEqual(package["schema_version"], 2)
        self.assertEqual(package["default_platforms"], ["wechat", "xiaohongshu"])
        self.assertRegex(package["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(package["images"]), 5)
        self.assertEqual(package["images"][0]["kind"], "cover")
        self.assertEqual(package["images"][1]["anchor"]["heading_index"], 1)
        self.assertEqual(package["images"][2]["anchor"]["heading_index"], 3)
        self.assertEqual(package["images"][3]["anchor"]["heading_index"], 4)
        self.assertEqual(package["images"][4]["anchor"]["heading_index"], 7)
        self.assertTrue(package["publish_options"]["declare_original"])
        self.assertNotIn("# 配图与插图建议", package["body_markdown"])
        self.assertNotIn(f"# {package['title']}", package["body_markdown"])
        self.assertTrue(
            any(
                "不要把正文切成大量一句一段的碎片" in item
                for item in package["layout_instructions"]
            )
        )

    def test_rejects_missing_illustration_section(self):
        module = self.load_module()
        with self.assertRaisesRegex(module.ParseError, "配图与插图建议"):
            module.parse_content("# 标题\n\n正文")

    def test_rejects_duplicate_image_number(self):
        module = self.load_module()
        markdown = """# 标题

正文。

# 配图与插图建议

## 配图 1：封面
**位置：** 正文最前面。
**作用：** 封面。
**尺寸建议：** 2.35:1。
**可直接使用的提示词：**
> 提示词一。

## 配图 1：正文图
**位置：** 第一章节之后。
**作用：** 解释。
**尺寸建议：** 16:9。
**可直接使用的提示词：**
> 提示词二。

## 给 Codex 的发布与排版要求
保持克制。
"""
        with self.assertRaisesRegex(module.ParseError, "重复"):
            module.parse_content(markdown)

    def test_rejects_missing_prompt(self):
        module = self.load_module()
        markdown = """# 标题

正文。

# 配图与插图建议

## 配图 1：封面
**位置：** 正文最前面。
**作用：** 封面。
**尺寸建议：** 2.35:1。

## 给 Codex 的发布与排版要求
保持克制。
"""
        with self.assertRaisesRegex(module.ParseError, "提示词"):
            module.parse_content(markdown)

    def test_renders_wechat_staging_html(self):
        module, package = self.parse_sample()
        rendered = module.render_wechat_staging_html(package)

        self.assertIn('<article class="wechat-article">', rendered)
        self.assertNotIn("<h1", rendered)
        self.assertIn('data-image-id="image-02"', rendered)
        self.assertIn('data-image-id="image-03"', rendered)
        self.assertIn('data-image-id="image-04"', rendered)
        self.assertIn('data-image-id="image-05"', rendered)
        self.assertIn("font-size:16px", rendered)
        self.assertIn("line-height:1.8", rendered)
        self.assertIn("<blockquote", rendered)
        self.assertIn("需按语义复核位置", rendered)

    def test_unordered_list_keeps_bullet_and_text_in_same_mobile_flow(self):
        module, package = self.parse_sample()
        rendered = module.render_wechat_staging_html(package)

        self.assertIn(
            '<ul style="margin:0 0 18px;padding-left:1.5em;"><li>工具调用；</li>',
            rendered,
        )
        self.assertNotIn("display:inline-block", rendered)
        self.assertNotRegex(rendered, r"<p[^>]*>\s*[•·]\s*</p>")

    def test_writes_package_and_cli_outputs(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            json_path, html_path = module.write_content_package(SAMPLE, output_dir)

            self.assertEqual(json_path.name, "content-package.json")
            self.assertEqual(html_path.name, "article-staging.html")
            self.assertEqual(html_path.parent.name, "wechat")
            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            package = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(package["images"]), 5)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(SAMPLE),
                    "--output-dir",
                    temp_dir,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(Path(temp_dir).resolve()), result.stdout)


if __name__ == "__main__":
    unittest.main()
