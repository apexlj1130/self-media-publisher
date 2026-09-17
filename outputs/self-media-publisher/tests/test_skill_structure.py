#!/usr/bin/env python3
from __future__ import annotations

import re
import hashlib
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SOURCE_SHA256 = "a994539f38547e294d4f2caa13ce48179fd94c6a0c3fb3f7500aa8d9fc96e309"


class SkillStructureTest(unittest.TestCase):
    def test_required_files_exist(self):
        required = [
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/prepare_content.py",
            "scripts/validate_media_manifest.py",
            "scripts/validate_xhs_package.py",
            "scripts/wechat_draft.py",
            "references/运行包格式.md",
            "references/公众号API配置与草稿流程.md",
            "references/小红书浏览器发布流程.md",
            "references/双平台发布前复核清单.md",
            "references/开源项目与许可.md",
        ]
        missing = [item for item in required if not (SKILL_ROOT / item).is_file()]
        self.assertEqual(missing, [], f"缺少 Skill 文件：{missing}")

    def test_skill_links_resolve_and_has_no_scaffold_tokens(self):
        skill_path = SKILL_ROOT / "SKILL.md"
        self.assertTrue(skill_path.exists(), "SKILL.md 尚未实现")
        content = skill_path.read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)
        relative_links = [link for link in links if "://" not in link and not link.startswith("#")]
        missing = [link for link in relative_links if not (SKILL_ROOT / link).exists()]
        self.assertEqual(missing, [], f"无效相对链接：{missing}")
        self.assertNotRegex(content, r"\b(?:TODO|TBD|PLACEHOLDER)\b")

    def test_skill_metadata_and_safety_routes_are_unified(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        openai_yaml = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: self-media-publisher", skill)
        self.assertIn("目标平台固定为 `wechat` 和 `xiaohongshu`", skill)
        self.assertIn("wechat_draft.py create", skill)
        self.assertIn("可见 Chrome", skill)
        self.assertIn("浏览器或系统安全策略拒绝", skill)
        self.assertIn("$self-media-publisher", openai_yaml)

        xhs_reference = (
            SKILL_ROOT / "references" / "小红书浏览器发布流程.md"
        ).read_text(encoding="utf-8")
        for forbidden_capability in (
            "私有或逆向发帖 API",
            "导出 Cookie",
            "Headless",
            "CDP",
            "脚本注入",
            "指纹伪装",
        ):
            self.assertIn(forbidden_capability, xhs_reference)

    def test_skill_package_excludes_original_user_article(self):
        matching = []
        for path in SKILL_ROOT.rglob("*"):
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest == ORIGINAL_SOURCE_SHA256:
                    matching.append(str(path.relative_to(SKILL_ROOT)))
        self.assertEqual(matching, [], f"Skill 包含真实用户原稿：{matching}")

        fixture = SKILL_ROOT / "tests" / "fixtures" / "示例文章.md"
        self.assertIn(
            "synthetic fixture; no user data",
            fixture.read_text(encoding="utf-8"),
            "测试夹具必须明确为合成内容",
        )


if __name__ == "__main__":
    unittest.main()
