# 公众号 API 配置与草稿流程

## 配置

配置必须位于 Skill 和 Git 之外，例如：

```text
~/.config/self-media-publisher/wechat.yaml
```

配置兼容 `jiji262/wechat-publisher` 的单账号结构：

```yaml
default: main
accounts:
  main:
    name: 公众号显示名
    app_id: your-app-id
    app_secret: your-app-secret
    author: 作者名
```

设置权限：

```bash
chmod 0600 ~/.config/self-media-publisher/wechat.yaml
```

不得在对话、日志、命令行回显、Git 或运行收据中输出 `app_secret` 和 access token。token 默认缓存到 `~/.cache/self-media-publisher/wechat-token.json`，文件和父目录使用私有权限。

## 创建并回读草稿

只有用户当次授权创建真实公众号草稿后运行：

```bash
python3 <skill-dir>/scripts/wechat_draft.py create \
  --package <run-dir>/content-package.json \
  --manifest <run-dir>/media-manifest.json \
  --config ~/.config/self-media-publisher/wechat.yaml \
  --receipt <run-dir>/wechat/receipt.json
```

固定顺序：

1. 校验内容包、媒体清单和配置权限。
2. 获取或复用 access token。
3. 通过永久素材接口上传一张封面。
4. 通过正文图片接口上传每张正文图并取得微信 CDN URL。
5. 把 HTML 图片语义标记替换为 CDN 图片。
6. 调用 `draft/add` 创建普通图文草稿。
7. 调用 `draft/get` 回读标题与正文图片 URL。
8. 只有回读一致才写 `verified_draft` 收据。

token 获取和只读回读可对连接失败、超时或 5xx 做有限重试。上传和 `draft/add` 是非幂等写入；响应未知时不自动重试，以免产生重复永久素材或重复草稿。

## 常见停止条件

- `40164`：当前公网出口 IP 不在微信 API 白名单。直接停止，请用户核对后台白名单和当前微信 API 请求的实际出口；不得自动循环重试。
- 配置权限不是 `0600`：停止并修正权限。
- 上传返回结果未知：停止，先在素材库核对。
- `draft/add` 返回结果未知：停止，先在草稿箱按标题和时间核对。
- 回读标题或图片不一致：保留草稿但标记验收失败，不创建第二份草稿。

## 原创、移动端预览与发布

官方草稿 API 不证明后台的原创声明已经开启。创建草稿后仍要在可见 Chrome 中打开 `mp.weixin.qq.com` 的当前草稿：

1. 核对公众号身份、标题、正文、封面和图片数量。
2. 用平台预览检查手机端段落、无序列表、图片宽度和封面裁切。
3. 勾选原创声明；若出现额外承诺、资质或权利提示，停止并请用户处理。
4. 其他选项保持后台默认值。
5. 内容或设置有变更时，重新预览并废弃旧确认。
6. 只有当前版本获得明确确认后，才触发一次发布并读取平台结果。
