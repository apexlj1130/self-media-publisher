# 项目协作说明

## 项目目标

维护公开 Codex Skill `self-media-publisher`。它默认把一份 Markdown 素材同时准备为微信公众号长文和小红书图文：公众号通过官方 API 创建并回读草稿，小红书通过可见 Chrome 正常页面填充和复核。正式发布始终需要对应平台当前版本的明确确认。

## 仓库结构

- `README.md`：公开安装、公众号配置、首次使用和故障排查入口。
- `LICENSE`：MIT 许可证。
- `outputs/self-media-publisher/`：Skill 的唯一源码和测试目录。
- `outputs/self-media-publisher.tar.gz`：发布归档；重新发布时必须由当前源码生成并验证一致性。
- `work/`：本地真实运行资料，不得加入 Git、Skill 或发布归档。

## 架构与安全边界

- 默认同时准备 `wechat` 和 `xiaohongshu`；用户当次可明确缩小到单平台。
- 所有平台图片均使用 Codex `imagegen`，不得用 SVG、HTML/CSS 卡片或程序化制图替代。
- 微信公众号只通过官方 API 创建草稿；AppSecret、token、真实文章和运行收据不得进入 Git 或 Skill。
- 小红书只使用可见 Chrome Computer Use，不使用私有接口、Cookie 导出、Headless、CDP、脚本注入、指纹伪装或高权限发布扩展。
- 解析与校验脚本只负责确定性结构，不替模型决定语义改编、图片质量或真实页面排版。
- 扫码、验证码、实名认证、原创资格、权利承诺和风险提示由用户处理。
- 两个平台分别绑定内容指纹和确认；内容或设置变化后，对应平台旧确认立即失效。
- 浏览器安全策略拒绝是硬停止，不得换工具绕过。
- 外部写入结果不明时先回读或人工核对，不重复提交试探。

## 修改约定

- 只修改 `outputs/self-media-publisher/` 中的 Skill 源码，不把个人安装副本当作源文件。
- 公共行为、依赖、配置路径或使用方式变化时，同步更新 `README.md` 和相关 `references/`。
- 不把真实账号、真实原稿、图片、Cookie、token、配置文件或运行产物加入测试夹具。
- 离线测试不得登录真实平台、创建真实草稿或触发正式发布。
- 真实微信草稿、小红书页面填充或正式发布需要用户对当次操作的明确授权。

## 验证命令

```bash
python3 -m unittest discover -s outputs/self-media-publisher/tests -p 'test_*.py' -v
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  outputs/self-media-publisher
```

若更新发布归档，还需在临时目录解压后确认其内容与 `outputs/self-media-publisher/` 一致，并在解压副本中重跑上述验证。

## 完成标准

- 完整离线测试和官方 Skill 快速校验通过。
- README、Skill 和参考文件之间没有失效链接或相互矛盾的公开说明。
- 凭证、真实内容、Cookie、token 和运行收据扫描无泄漏。
- 发布确认、防重复写入和浏览器安全边界没有被弱化。
