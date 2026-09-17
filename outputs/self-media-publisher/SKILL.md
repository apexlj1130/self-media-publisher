---
name: self-media-publisher
description: Use when preparing or publishing one source as both a WeChat Official Account article and a Xiaohongshu image note, including AI image generation, WeChat official-API drafts, visible Chrome filling, preview, confirmation, and publication.
---

# 公众号与小红书发布

## 概述

把一份带配图说明的 Markdown 素材默认准备成微信公众号长文和小红书图文。确定性脚本只负责解析和契约校验；模型负责平台改编、AI 图片质量和页面复核；用户负责登录挑战与正式发布授权。

未明确缩小范围时，目标平台固定为 `wechat` 和 `xiaohongshu`。微信公众号创建草稿走官方 API；小红书使用可见 Chrome 的正常 UI。两个平台分别预览、分别确认、分别发布。

## 工作流

1. 把原稿和运行产物放在任务工作目录，不写入 Skill 安装目录。运行：

   ```bash
   python3 <skill-dir>/scripts/prepare_content.py <source.md> --output-dir <run-dir>
   ```

   读取 `content-package.json` 和 `wechat/article-staging.html`。输入错误、语义位置明显含糊或目标平台不清楚时先解决，不开始外部写入。字段定义见 [运行包格式](references/运行包格式.md)。

2. 为公众号保留完整长文；为小红书重新组织标题、正文、标签和图片叙事。不要把公众号全文机械截断后直接发布。小红书包必须通过：

   ```bash
   python3 <skill-dir>/scripts/validate_xhs_package.py \
     --package <run-dir>/xiaohongshu/package.json \
     --expected-source-sha256 <source_sha256>
   ```

3. **REQUIRED SUB-SKILL:** Use `imagegen` for every WeChat cover, WeChat inline image, Xiaohongshu cover, and Xiaohongshu content image. 不得用 SVG、HTML/CSS 卡片、Canvas、截图拼接或程序化制图代替。逐张检查比例、中文、数字、流程方向、事实和安全区域；不合格就定向重生成。

4. 写入 `media-manifest.json`，运行媒体校验器。清单只接受绝对路径和存在的文件：

   ```bash
   python3 <skill-dir>/scripts/validate_media_manifest.py \
     --manifest <run-dir>/media-manifest.json \
     --package <run-dir>/content-package.json
   ```

5. 用户当次授权创建真实公众号草稿后，读取 [公众号 API 配置与草稿流程](references/公众号API配置与草稿流程.md)。调用 `wechat_draft.py create` 上传图片、创建草稿并回读；`verified_draft` 收据只证明草稿已创建并通过字段核对，不代表原创声明已开启或已发布。

6. 读取 [小红书浏览器发布流程](references/小红书浏览器发布流程.md)。用户当次授权填充真实小红书草稿后，使用可见 Chrome 正常 UI 上传图片、填写标题正文与标签，并现场复核顺序、裁切和手机端效果。停在发布前页面，不点击发布。

7. 对照 [双平台发布前复核清单](references/双平台发布前复核清单.md)：

   - 公众号在官方后台打开 API 草稿，完成移动端预览并勾选原创声明；其他设置保持默认。
   - 小红书确认图片顺序、正文、标签、可见范围和原创选项；其他设置保持默认。
   - 向用户报告每个平台的标题、图片数、当前指纹、草稿/预览状态和待处理异常。

8. 发布确认只绑定对应平台的当前内容和设置。用户只确认公众号时不得发布小红书，反之亦然；一句明确同时确认可以授权两端。确认后任一平台内容发生变化，只让该平台旧确认失效，必须重新预览和确认。

9. 获得有效确认后再做一次页面复核，每个平台的发布动作只触发一次。结果不明时先查平台成功提示、已发表记录或草稿状态；不得重复点击试探。

## 硬停止条件

- 扫码、验证码、短信、实名、安全确认、风控提示、原创资格异常：暂停并请用户接管。
- 浏览器或系统安全策略拒绝：完全停止该浏览器流程，不切换 CDP、扩展、脚本注入或其他自动化绕过。
- 图片乱码、关键信息错误、平台包无效或草稿回读不一致：不得进入发布确认。
- 微信写入请求状态未知：不得自动重试创建草稿；先人工核对草稿箱。
- 小红书禁止使用私有 API、Cookie 导出、xsec token、Headless、CDP、调试器权限、Shadow DOM 穿透、脚本注入、指纹伪装或高权限发布扩展。

## 数据边界

- 不把文章、图片、配置、token、Cookie、运行收据或真实账号数据放入 Skill、Git 或归档。
- 微信配置和 token 缓存必须位于 Skill 外且权限为 `0600`。
- 不把旧对话中的泛化授权当作当前草稿确认。
- 不把脚本通过、模型自评或预先生成的 `confirmed` 字段当作用户授权。
