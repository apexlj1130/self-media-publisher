#!/usr/bin/env python3
"""Create and verify one WeChat Official Account draft through official APIs."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

import requests
import yaml

from prepare_content import render_wechat_staging_html
from validate_media_manifest import PackageValidationError, validate_media_manifest


API_BASE = "https://api.weixin.qq.com"
TOKEN_SAFETY_MARGIN_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RETRIES = 2


class ConfigError(RuntimeError):
    """Raised when the single-account configuration is missing or unsafe."""


class WeChatAPIError(RuntimeError):
    """Raised for HTTP or WeChat application-layer failures."""


class DraftVerificationError(RuntimeError):
    """Raised when a created draft cannot be verified by readback."""


@dataclass(frozen=True)
class WeChatConfig:
    account_key: str
    account_name: str
    app_id: str
    app_secret: str = field(repr=False)
    author: str = ""


class RequestsTransport:
    """Small injectable boundary around ``requests``."""

    def request(self, method: str, url: str, **kwargs: Any):
        return requests.request(method, url, **kwargs)


def _secure_mode(path: Path) -> bool:
    return path.stat().st_mode & 0o077 == 0


def load_config(path: Path) -> WeChatConfig:
    """Load the upstream-compatible single-account YAML configuration."""

    path = path.expanduser().resolve()
    if not path.is_file():
        raise ConfigError(f"公众号配置文件不存在：{path}")
    if not _secure_mode(path):
        raise ConfigError("公众号配置文件权限过宽；请执行 chmod 0600 后重试")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError("公众号配置文件无法读取") from exc
    if not isinstance(value, Mapping):
        raise ConfigError("公众号配置必须是 YAML 对象")
    accounts = value.get("accounts")
    if not isinstance(accounts, Mapping) or not accounts:
        raise ConfigError("公众号配置缺少 accounts")
    account_key = value.get("default")
    if account_key is None and len(accounts) == 1:
        account_key = next(iter(accounts))
    if not isinstance(account_key, str) or account_key not in accounts:
        raise ConfigError("公众号配置缺少有效的 default 单账号")
    account = accounts[account_key]
    if not isinstance(account, Mapping):
        raise ConfigError("公众号账号配置必须是对象")
    app_id = str(account.get("app_id") or "").strip()
    app_secret = str(account.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise ConfigError("公众号账号缺少 app_id 或 app_secret")
    return WeChatConfig(
        account_key=account_key,
        account_name=str(account.get("name") or account_key).strip(),
        app_id=app_id,
        app_secret=app_secret,
        author=str(account.get("author") or "").strip(),
    )


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    path = path.expanduser().resolve()
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent_existed:
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    descriptor = os.open(
        str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


class WeChatDraftClient:
    """Minimal official-API client with safe retry boundaries."""

    def __init__(
        self,
        config: WeChatConfig,
        transport: Optional[Any] = None,
        cache_path: Optional[Path] = None,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.config = config
        self.transport = transport or RequestsTransport()
        self.cache_path = (
            cache_path.expanduser().resolve()
            if cache_path is not None
            else Path("~/.cache/self-media-publisher/wechat-token.json")
            .expanduser()
            .resolve()
        )
        self.sleep = sleep
        self.retries = max(0, retries)
        self._token: Optional[str] = None
        self._expires_at = 0.0

    def _credential_fingerprint(self) -> str:
        material = f"{self.config.app_id}\0{self.config.app_secret}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        data: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        files: Optional[Mapping[str, Any]] = None,
        retry_transient: bool,
        unknown_on_failure: bool = False,
    ) -> Mapping[str, Any]:
        attempts = self.retries + 1 if retry_transient else 1
        for attempt in range(attempts):
            try:
                response = self.transport.request(
                    method,
                    f"{API_BASE}{path}",
                    params=dict(params or {}),
                    data=data,
                    headers=dict(headers or {}),
                    files=files,
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt + 1 < attempts:
                    self.sleep(1.5**attempt)
                    continue
                message = (
                    "微信写入请求结果未知，不得自动重试"
                    if unknown_on_failure
                    else "微信接口网络请求失败"
                )
                raise WeChatAPIError(message) from exc

            if 500 <= response.status_code < 600:
                if attempt + 1 < attempts:
                    self.sleep(1.5**attempt)
                    continue
                message = (
                    f"微信写入返回 HTTP {response.status_code}，状态未知，不得自动重试"
                    if unknown_on_failure
                    else f"微信接口返回 HTTP {response.status_code}"
                )
                raise WeChatAPIError(message)
            if not 200 <= response.status_code < 300:
                raise WeChatAPIError(f"微信接口返回 HTTP {response.status_code}")
            try:
                raw_content = getattr(response, "content", None)
                if isinstance(raw_content, bytes) and raw_content:
                    payload = json.loads(raw_content.decode("utf-8-sig"))
                else:
                    payload = response.json()
            except (TypeError, ValueError) as exc:
                raise WeChatAPIError("微信接口返回了无效 JSON") from exc
            if not isinstance(payload, Mapping):
                raise WeChatAPIError("微信接口返回值不是 JSON 对象")
            error_code = payload.get("errcode")
            if error_code not in (None, 0):
                error_message = str(payload.get("errmsg") or "未知错误")
                raise WeChatAPIError(f"微信接口失败 [{error_code}]: {error_message}")
            return payload
        raise WeChatAPIError("微信接口请求失败")

    def _load_cached_token(self) -> Optional[str]:
        if not self.cache_path.is_file() or not _secure_mode(self.cache_path):
            return None
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(value, Mapping):
            return None
        if value.get("account_key") != self.config.account_key:
            return None
        if value.get("credential_fingerprint") != self._credential_fingerprint():
            return None
        token = value.get("token")
        expires_at = value.get("expires_at")
        if (
            isinstance(token, str)
            and token
            and isinstance(expires_at, (int, float))
            and expires_at > time.time() + TOKEN_SAFETY_MARGIN_SECONDS
        ):
            self._token = token
            self._expires_at = float(expires_at)
            return token
        return None

    def get_access_token(self) -> str:
        if self._token and self._expires_at > time.time() + TOKEN_SAFETY_MARGIN_SECONDS:
            return self._token
        cached = self._load_cached_token()
        if cached:
            return cached
        payload = self._request_json(
            "GET",
            "/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": self.config.app_id,
                "secret": self.config.app_secret,
            },
            retry_transient=True,
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise WeChatAPIError("获取 access_token 失败：响应缺少 token")
        expires_in = payload.get("expires_in", 7200)
        if not isinstance(expires_in, (int, float)):
            expires_in = 7200
        self._token = token
        self._expires_at = time.time() + float(expires_in)
        _write_private_json(
            self.cache_path,
            {
                "account_key": self.config.account_key,
                "credential_fingerprint": self._credential_fingerprint(),
                "token": token,
                "expires_at": self._expires_at,
            },
        )
        return token

    def _upload_image(self, path: Path, endpoint: str, result_key: str) -> str:
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"图片文件不存在：{path}")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        params: Dict[str, str] = {"access_token": self.get_access_token()}
        if endpoint == "/cgi-bin/material/add_material":
            params["type"] = "image"
        with path.open("rb") as stream:
            payload = self._request_json(
                "POST",
                endpoint,
                params=params,
                files={"media": (path.name, stream, mime_type)},
                retry_transient=False,
                unknown_on_failure=True,
            )
        value = payload.get(result_key)
        if not isinstance(value, str) or not value:
            raise WeChatAPIError(f"微信图片上传响应缺少 {result_key}")
        return value

    def upload_cover(self, path: Path) -> str:
        return self._upload_image(path, "/cgi-bin/material/add_material", "media_id")

    def upload_content_image(self, path: Path) -> str:
        url = self._upload_image(path, "/cgi-bin/media/uploadimg", "url")
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        return url

    def add_draft(self, payload: Mapping[str, Any]) -> str:
        response = self._request_json(
            "POST",
            "/cgi-bin/draft/add",
            params={"access_token": self.get_access_token()},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            retry_transient=False,
            unknown_on_failure=True,
        )
        media_id = response.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise WeChatAPIError("创建草稿响应缺少 media_id")
        return media_id

    def get_draft(self, media_id: str) -> Mapping[str, Any]:
        return self._request_json(
            "POST",
            "/cgi-bin/draft/get",
            params={"access_token": self.get_access_token()},
            data=json.dumps({"media_id": media_id}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            retry_transient=True,
        )


def _read_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageValidationError(f"{label}无法读取") from exc
    if not isinstance(value, Mapping):
        raise PackageValidationError(f"{label}必须是 JSON 对象")
    return value


def _render_wechat_content(
    package: Mapping[str, Any], inline_urls: Mapping[str, str]
) -> str:
    document = render_wechat_staging_html(package)
    article_match = re.search(
        r'<article class="wechat-article">\s*(.*?)\s*</article>',
        document,
        flags=re.DOTALL,
    )
    if not article_match:
        raise DraftVerificationError("无法从暂存文档提取微信正文")
    content = article_match.group(1)
    for image_id, url in inline_urls.items():
        pattern = re.compile(
            rf'<section data-image-id="{re.escape(image_id)}".*?</section>',
            flags=re.DOTALL,
        )
        replacement = (
            '<p style="margin:24px 0;text-align:center;">'
            f'<img src="{html.escape(url, quote=True)}" '
            'style="max-width:100%;height:auto;display:block;margin:0 auto;">'
            "</p>"
        )
        content, count = pattern.subn(replacement, content, count=1)
        if count != 1:
            raise DraftVerificationError(f"微信正文缺少图片语义标记：{image_id}")
    if "data-image-id=" in content:
        raise DraftVerificationError("微信正文仍有未替换的图片语义标记")
    return content


def _verify_readback(
    readback: Mapping[str, Any], title: str, expected_urls: Sequence[str]
) -> None:
    items = readback.get("news_item")
    if not isinstance(items, list) or not items or not isinstance(items[0], Mapping):
        raise DraftVerificationError("微信草稿回读缺少 news_item")
    article = items[0]
    if article.get("title") != title:
        raise DraftVerificationError("微信草稿回读标题不一致")
    content = str(article.get("content") or "")
    missing = [url for url in expected_urls if url not in html.unescape(content)]
    if missing:
        raise DraftVerificationError("微信草稿回读缺少正文图片")


def create_verified_draft(
    package_path: Path,
    manifest_path: Path,
    config_path: Path,
    receipt_path: Path,
    *,
    transport: Optional[Any] = None,
    cache_path: Optional[Path] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Upload images, create one draft, verify it, then write a safe receipt."""

    package = _read_mapping(package_path, "统一内容包")
    manifest = validate_media_manifest(
        _read_mapping(manifest_path, "媒体清单"), package
    )
    config = load_config(config_path)
    client = WeChatDraftClient(
        config, transport=transport, cache_path=cache_path, sleep=sleep
    )

    images = package.get("images")
    assert isinstance(images, list)
    cover_images = [image for image in images if image.get("kind") == "cover"]
    if len(cover_images) != 1:
        raise PackageValidationError("微信公众号内容必须恰好包含一张封面图")
    cover_id = cover_images[0]["id"]
    cover_media_id = client.upload_cover(Path(manifest["wechat"][cover_id]))

    inline_urls: Dict[str, str] = {}
    for image in images:
        if image.get("kind") == "cover":
            continue
        image_id = image["id"]
        inline_urls[image_id] = client.upload_content_image(
            Path(manifest["wechat"][image_id])
        )
    content = _render_wechat_content(package, inline_urls)
    article: Dict[str, Any] = {
        "title": str(package["title"]),
        "content": content,
        "thumb_media_id": cover_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    if config.author:
        article["author"] = config.author
    media_id = client.add_draft({"articles": [article]})
    readback = client.get_draft(media_id)
    _verify_readback(readback, article["title"], list(inline_urls.values()))

    receipt: Dict[str, Any] = {
        "status": "verified_draft",
        "media_id": media_id,
        "account": config.account_name,
        "title": article["title"],
        "image_count": len(images),
        "source_sha256": package["source_sha256"],
    }
    _write_private_json(receipt_path, receipt)
    return receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通过微信官方 API 创建并回读公众号草稿")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="创建并验证一个公众号草稿")
    create.add_argument("--package", required=True, type=Path)
    create.add_argument("--manifest", required=True, type=Path)
    create.add_argument("--config", required=True, type=Path)
    create.add_argument("--receipt", required=True, type=Path)
    create.add_argument("--cache", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        receipt = create_verified_draft(
            args.package,
            args.manifest,
            args.config,
            args.receipt,
            cache_path=args.cache,
        )
    except (
        ConfigError,
        PackageValidationError,
        WeChatAPIError,
        DraftVerificationError,
        OSError,
    ) as exc:
        print(f"创建公众号草稿失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
