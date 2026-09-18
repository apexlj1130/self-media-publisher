# 项目协作说明

## 项目目标

开发并验证个人 Codex Skill `self-media-publisher`。它默认把一份原始素材同时准备为微信公众号长文和小红书图文：公众号通过官方 API 创建草稿，小红书通过可见 Chrome Computer Use 填充和复核；任何正式发布都需要对应平台当前版本的明确确认。

## 项目结构

- `README.md`：面向公开用户的安装、配置、首跑和故障排查入口。
- `LICENSE`：项目 MIT 许可证。
- `docs/product/需求规格.md`：稳定需求与验收标准。
- `docs/功能设计.md`：用户流程、输入输出和双平台体验。
- `docs/技术架构设计.md`：模块边界、数据契约和安全闸门。
- `docs/决策记录.md`：关键产品与技术决策。
- `docs/实施计划.md`：当前批准设计的唯一实施计划。
- `docs/quality/交付总计划.md`：唯一进度看板和验证证据入口。
- `outputs/self-media-publisher/`：最终可交付 Skill 包。
- `work/`：真实运行素材和上游评估目录，不得加入交付提交。

## 工程约束

- 所有工作由主 Agent 完成，不使用子代理。
- 默认同时准备公众号和小红书；当次明确指定单平台时可以缩小范围。
- 所有平台图片均使用 Codex `imagegen`，不得使用 SVG、HTML/CSS 卡片或程序化制图替代。
- 微信公众号只通过官方 API 创建草稿；凭证和 token 不进入 Git 或 Skill 包。
- 小红书只使用可见 Chrome Computer Use，不安装高权限 XHS Bridge，不调用私有接口，不读取 Cookie，不使用 Headless、CDP、脚本注入或指纹伪装。
- 解析脚本只生成候选结构和样式，不拥有小红书改编、图片质量或页面排版决定权。
- 扫码、验证码、实名认证、原创资格和风险提示交由用户处理。
- 两个平台分别绑定内容指纹和确认；没有当前版本确认时只能停在草稿或预览。
- 浏览器安全策略拒绝是硬停止，不得换工具绕过。
- 离线测试不得登录真实平台、创建真实草稿或触发发布。

## 开发与验证

实现前阅读 `docs/product/需求规格.md`、`docs/功能设计.md`、`docs/技术架构设计.md`、`docs/实施计划.md` 和 `docs/quality/交付总计划.md`。

常用验证命令：

```bash
python3 -m unittest discover -s outputs/self-media-publisher/tests -p 'test_*.py' -v
python3 /Users/lee/.codex/skills/.system/skill-creator/scripts/quick_validate.py outputs/self-media-publisher
python3 /Users/lee/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/lee/.codex/skills/self-media-publisher
```

真实微信 API 草稿和小红书浏览器草稿测试均需要单独授权。

## 完成标准

- 原始来源、需求、实现、测试和交付状态在交付总计划中双向可追踪。
- 统一内容包默认包含两个平台，且合成样例解析结果稳定。
- 微信 API 适配器的 token、图片、草稿和回读边界有离线测试。
- 小红书发布包校验和安全浏览器流程不包含高风险绕过能力。
- 发布确认和防重复规则不能被脚本或旧确认绕过。
- 精确归档和个人安装副本通过测试、结构校验与隐私扫描。
