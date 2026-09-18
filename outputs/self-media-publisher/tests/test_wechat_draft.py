#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import logging
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "wechat_draft.py"
SOURCE_SHA256 = "c" * 64
APP_SECRET = "replace-outside-skill"


def load_module():
    if not SCRIPT.exists():
        raise AssertionError("wechat_draft.py 尚未实现")
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("wechat_draft", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("无法加载 wechat_draft.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, status_code=200, content=None):
        self.payload = payload
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"没有为请求准备响应：{method} {url}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class WeChatDraftTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.cover = self.root / "cover.png"
        self.inline = self.root / "inline.png"
        self.cover.write_bytes(b"synthetic-cover")
        self.inline.write_bytes(b"synthetic-inline")
        self.config_path = self.root / "wechat.yaml"
        self.config_path.write_text(
            """default: main
accounts:
  main:
    name: 测试公众号
    app_id: wx-unit-test
    app_secret: replace-outside-skill
    author: 测试作者
""",
            encoding="utf-8",
        )
        os.chmod(self.config_path, 0o600)
        self.package_path = self.root / "content-package.json"
        self.manifest_path = self.root / "media-manifest.json"
        self.receipt_path = self.root / "wechat-receipt.json"
        self.cache_path = self.root / "token-cache.json"
        self.package_path.write_text(
            json.dumps(self.content_package(), ensure_ascii=False), encoding="utf-8"
        )
        self.manifest_path.write_text(
            json.dumps(self.media_manifest(), ensure_ascii=False), encoding="utf-8"
        )

    def content_package(self):
        return {
            "schema_version": 2,
            "source_sha256": SOURCE_SHA256,
            "default_platforms": ["wechat", "xiaohongshu"],
            "title": "测试公众号草稿",
            "body_markdown": "正文开头。\n\n## 一、测试章节\n\n正文内容。",
            "images": [
                {
                    "id": "image-01",
                    "number": 1,
                    "name": "封面",
                    "kind": "cover",
                    "anchor": {
                        "heading_index": None,
                        "heading_text": None,
                        "placement": "cover",
                    },
                },
                {
                    "id": "image-02",
                    "number": 2,
                    "name": "正文信息图",
                    "kind": "inline",
                    "anchor": {
                        "heading_index": 1,
                        "heading_text": "一、测试章节",
                        "placement": "after_section",
                    },
                },
            ],
            "publish_options": {"declare_original": True},
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

    def success_responses(self, readback_title="测试公众号草稿"):
        return [
            FakeResponse({"access_token": "token-value", "expires_in": 7200}),
            FakeResponse({"media_id": "cover-media-id"}),
            FakeResponse({"url": "http://mmbiz.qpic.cn/inline.png"}),
            FakeResponse({"media_id": "draft-media-id"}),
            FakeResponse(
                {
                    "news_item": [
                        {
                            "title": readback_title,
                            "content": (
                                '<p>正文</p><img src="https://mmbiz.qpic.cn/inline.png">'
                            ),
                        }
                    ]
                }
            ),
        ]

    def test_loads_single_account_config_without_exposing_secret(self):
        module = load_module()
        config = module.load_config(self.config_path)

        self.assertEqual(config.account_key, "main")
        self.assertEqual(config.account_name, "测试公众号")
        self.assertEqual(config.app_id, "wx-unit-test")
        self.assertEqual(config.author, "测试作者")
        self.assertNotIn(APP_SECRET, repr(config))

        logger_output = repr(config)
        logging.getLogger("wechat-draft-test").info("%s", config)
        self.assertNotIn(APP_SECRET, logger_output)

    def test_rejects_missing_credentials_and_broad_config_permissions(self):
        module = load_module()
        missing = self.root / "missing.yaml"
        missing.write_text("default: main\naccounts:\n  main:\n    app_id: wx-only\n", encoding="utf-8")
        os.chmod(missing, 0o600)
        with self.assertRaisesRegex(module.ConfigError, "app_id.*app_secret|app_secret"):
            module.load_config(missing)

        os.chmod(self.config_path, 0o644)
        with self.assertRaisesRegex(module.ConfigError, "0600"):
            module.load_config(self.config_path)

    def test_creates_and_reads_back_draft_with_exact_api_contract(self):
        module = load_module()
        transport = FakeTransport(self.success_responses())

        receipt = module.create_verified_draft(
            self.package_path,
            self.manifest_path,
            self.config_path,
            self.receipt_path,
            transport=transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )

        self.assertEqual(receipt["status"], "verified_draft")
        self.assertEqual(receipt["media_id"], "draft-media-id")
        self.assertEqual(receipt["image_count"], 2)
        self.assertEqual(receipt["source_sha256"], SOURCE_SHA256)
        self.assertNotIn("token-value", json.dumps(receipt))
        self.assertNotIn(str(self.root), self.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(self.cache_path.stat().st_mode), 0o600)

        paths = [urlparse(call["url"]).path for call in transport.calls]
        self.assertEqual(
            paths,
            [
                "/cgi-bin/token",
                "/cgi-bin/material/add_material",
                "/cgi-bin/media/uploadimg",
                "/cgi-bin/draft/add",
                "/cgi-bin/draft/get",
            ],
        )
        self.assertEqual(transport.calls[0]["method"], "GET")
        self.assertEqual(transport.calls[1]["params"]["type"], "image")
        self.assertEqual(transport.calls[2]["method"], "POST")

        draft_payload = json.loads(transport.calls[3]["data"].decode("utf-8"))
        article = draft_payload["articles"][0]
        self.assertEqual(article["title"], "测试公众号草稿")
        self.assertEqual(article["thumb_media_id"], "cover-media-id")
        self.assertIn("https://mmbiz.qpic.cn/inline.png", article["content"])
        self.assertNotIn("data-image-id", article["content"])
        self.assertNotIn(str(self.root), article["content"])

        readback_payload = json.loads(transport.calls[4]["data"].decode("utf-8"))
        self.assertEqual(readback_payload, {"media_id": "draft-media-id"})

    def test_40164_does_not_retry_or_disclose_secret(self):
        module = load_module()
        transport = FakeTransport(
            [FakeResponse({"errcode": 40164, "errmsg": "invalid ip 1.2.3.4"})]
        )
        config = module.load_config(self.config_path)
        client = module.WeChatDraftClient(
            config,
            transport=transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(module.WeChatAPIError, "40164") as caught:
            client.get_access_token()
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn(APP_SECRET, str(caught.exception))

    def test_token_5xx_retries_are_bounded(self):
        module = load_module()
        transport = FakeTransport(
            [
                FakeResponse({}, status_code=500),
                FakeResponse({}, status_code=502),
                FakeResponse({"access_token": "eventual-token", "expires_in": 7200}),
            ]
        )
        client = module.WeChatDraftClient(
            module.load_config(self.config_path),
            transport=transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )

        self.assertEqual(client.get_access_token(), "eventual-token")
        self.assertEqual(len(transport.calls), 3)

    def test_prefers_utf8_response_bytes_over_mojibake_response_json(self):
        module = load_module()
        correct_title = "开发传统软件和开发 Agent，到底有什么不一样？"
        mojibake_title = correct_title.encode("utf-8").decode("latin-1")
        raw_payload = {
            "news_item": [{"title": correct_title, "content": "<p>正文</p>"}]
        }
        transport = FakeTransport(
            [
                FakeResponse(
                    {
                        "news_item": [
                            {"title": mojibake_title, "content": "<p>æ­£æ</p>"}
                        ]
                    },
                    content=json.dumps(raw_payload, ensure_ascii=False).encode("utf-8"),
                )
            ]
        )
        client = module.WeChatDraftClient(
            module.load_config(self.config_path),
            transport=transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )
        client._token = "cached-token"
        client._expires_at = float("inf")

        readback = client.get_draft("draft-media-id")

        self.assertEqual(readback["news_item"][0]["title"], correct_title)

    def test_token_cache_is_invalidated_when_credentials_change(self):
        module = load_module()
        original_transport = FakeTransport(
            [FakeResponse({"access_token": "old-token", "expires_in": 7200})]
        )
        original = module.WeChatDraftClient(
            module.load_config(self.config_path),
            transport=original_transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )
        self.assertEqual(original.get_access_token(), "old-token")

        changed_config = module.WeChatConfig(
            account_key="main",
            account_name="测试公众号",
            app_id="wx-unit-test",
            app_secret="new-secret-after-reset",
            author="测试作者",
        )
        changed_transport = FakeTransport(
            [FakeResponse({"access_token": "new-token", "expires_in": 7200})]
        )
        changed = module.WeChatDraftClient(
            changed_config,
            transport=changed_transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )

        self.assertEqual(changed.get_access_token(), "new-token")
        self.assertEqual(len(changed_transport.calls), 1)

    def test_private_file_writer_does_not_chmod_existing_parent_directory(self):
        module = load_module()
        existing_parent = self.root / "shared-run-directory"
        existing_parent.mkdir(mode=0o755)
        os.chmod(existing_parent, 0o755)
        cache_path = existing_parent / "token-cache.json"
        transport = FakeTransport(
            [FakeResponse({"access_token": "token-value", "expires_in": 7200})]
        )
        client = module.WeChatDraftClient(
            module.load_config(self.config_path),
            transport=transport,
            cache_path=cache_path,
            sleep=lambda _: None,
        )

        client.get_access_token()

        self.assertEqual(stat.S_IMODE(existing_parent.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(cache_path.stat().st_mode), 0o600)

    def test_draft_create_5xx_is_not_retried_because_outcome_is_unknown(self):
        module = load_module()
        transport = FakeTransport(
            [
                FakeResponse({"access_token": "token-value", "expires_in": 7200}),
                FakeResponse({}, status_code=500),
            ]
        )
        client = module.WeChatDraftClient(
            module.load_config(self.config_path),
            transport=transport,
            cache_path=self.cache_path,
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(module.WeChatAPIError, "状态未知"):
            client.add_draft({"articles": []})
        draft_calls = [call for call in transport.calls if call["url"].endswith("/draft/add")]
        self.assertEqual(len(draft_calls), 1)

    def test_readback_mismatch_fails_without_creating_second_draft(self):
        module = load_module()
        transport = FakeTransport(self.success_responses(readback_title="被篡改的标题"))

        with self.assertRaisesRegex(module.DraftVerificationError, "标题"):
            module.create_verified_draft(
                self.package_path,
                self.manifest_path,
                self.config_path,
                self.receipt_path,
                transport=transport,
                cache_path=self.cache_path,
                sleep=lambda _: None,
            )

        draft_calls = [call for call in transport.calls if call["url"].endswith("/draft/add")]
        self.assertEqual(len(draft_calls), 1)
        self.assertFalse(self.receipt_path.exists())


if __name__ == "__main__":
    unittest.main()
