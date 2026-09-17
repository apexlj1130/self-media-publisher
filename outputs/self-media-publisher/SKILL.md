---
name: wechat-article-publisher
description: Use when preparing or publishing a single long-form article with AI-generated images to a WeChat Official Account through Chrome.
---

# 微信公众号文章发布

## 概述

把带配图说明的 Markdown 长文整理为微信公众号单篇图文。确定性脚本负责候选结构，AI 负责图片与语义判断，Chrome Computer Use 负责真实页面复核；脚本结果不能替代页面判断或用户发布授权。

首版不处理多图文合集、转载、视频号、小程序内容或多账号选择。

## 工作流

1. 在任务工作目录保存用户原稿。运行：

   ```bash
   python3 <skill-dir>/scripts/prepare_article.py <source.md> --output-dir <run-dir>
   ```

   读取 `article-package.json` 和 `article-staging.html`。解析失败、配图编号异常或重要位置含糊时，先解决输入问题，不进入公众号后台。

2. **REQUIRED SUB-SKILL:** Use `imagegen` for every cover and inline image. 按清单逐张生成，不得用 SVG、HTML 画布或程序化信息图代替。检查比例、主题、文字、数字、流程方向和关键信息；不合格就定向修订。无法得到可发布图片时报告未完成。

3. 开始浏览器操作前读取 [浏览器发布流程](references/浏览器发布流程.md)。使用用户当前 Chrome 配置，只操作微信公众号官方后台。扫码、验证码、安全确认、账号选择或原创资格异常出现时暂停，请用户接管。

4. 将暂存 HTML 的正文高效转入微信原生编辑器，标题单独填写。按每张图的 `position_text` 和正文语义插入图片；`anchor` 只是候选。Computer Use 必须在真实页面中检查并移动偏差图片，不能因脚本已有位置就跳过判断。

5. 排版完成后读取 [发布前复核清单](references/发布前复核清单.md)，从头到尾复核，保存草稿并进入预览。停下并向用户说明当前标题、图片数量、封面和原创声明状态，等待当前草稿的明确“确认发布”。

6. 确认只绑定当前文章、草稿和内容版本。确认后若正文、图片、封面或发布设置发生变化，旧确认立即失效。获得有效确认后再做一次最终复核，勾选原创声明，其他选项沿用后台默认值，然后只点击一次发布。

7. 点击后以平台成功提示、已发表记录或草稿状态作为结果证据。响应不明时先核对状态；不得通过重复点击来试探是否成功。

## 运行边界

- 不读取、保存或代填密码、验证码、Cookie。
- 不把文章内容、图片或账号数据写进 Skill 安装目录。
- 不把旧对话中的泛化授权当作本次发布确认。
- 不用固定屏幕坐标作为可复用定位规则；每次依据可访问性信息、可见文字和最新截图重新观察。
- 用户只要求准备或排版时，终点是已保存草稿或预览，不得自行扩大到发布。
