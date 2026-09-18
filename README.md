# Self-Media Publisher

一个面向 Codex Desktop 的双平台自媒体发布 Skill：输入一份带配图说明的 Markdown，默认同时准备微信公众号长文和小红书图文。

- 微信公众号：由 Codex 生成封面和正文配图，通过微信官方 API 上传图片、创建草稿并回读核验。
- 小红书：由 Codex 改编标题、正文和图片叙事，再通过用户可见的 Chrome 正常页面完成填充与发布前复核。
- 发布安全：两个平台分别预览、分别确认。没有当前版本的明确确认，Skill 不会执行正式发布。

> 这不是无人值守群发工具。扫码、短信、验证码、实名认证、原创资格、风控提示和正式发布授权始终由用户处理。

## 能力与边界

| 平台 | 自动完成 | 需要用户参与 |
|---|---|---|
| 微信公众号 | 长文解析、AI 配图、移动端友好排版、官方 API 图片上传、草稿创建、草稿回读 | 配置开发接口、维护 IP 白名单、后台移动预览、原创声明、最终确认与发布 |
| 小红书 | 内容改编、AI 配图、发布包校验、可见 Chrome 页面填充和复核 | 登录与安全挑战、原创或权利承诺、最终确认与发布 |

本项目不使用小红书私有接口、Cookie 导出、Headless、CDP、脚本注入、指纹伪装或高权限发布扩展。浏览器安全策略拒绝时会停止，不会换工具绕过。

## 环境要求

- Codex Desktop，能够使用 Skills、`imagegen` 和可见 Chrome Computer Use。
- Chrome。
- Git。
- Python 3.9 或更高版本。
- Python 包：`requests`、`PyYAML`。
- 一个微信公众号和一个小红书账号。
- 微信公众号已获得所需的素材和草稿接口权限，并准备好 AppID、AppSecret。

当前 Skill 按单账号设计。平台权限与菜单可能随账号类型、认证状态和微信后台版本而不同。

## 安装

### macOS / Linux

```bash
git clone https://github.com/apexlj1130/self-media-publisher.git
cd self-media-publisher

python3 -m pip install --user requests PyYAML

CODEX_ROOT="${CODEX_HOME:-$HOME/.codex}"
SKILLS_ROOT="$CODEX_ROOT/skills"
mkdir -p "$SKILLS_ROOT"

if [ -e "$SKILLS_ROOT/self-media-publisher" ]; then
  echo "安装目标已存在，请先按下文的升级步骤备份旧版本。"
  exit 1
fi

cp -R outputs/self-media-publisher "$SKILLS_ROOT/self-media-publisher"
```

### Windows PowerShell

```powershell
git clone https://github.com/apexlj1130/self-media-publisher.git
Set-Location self-media-publisher

py -m pip install --user requests PyYAML

$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsRoot = Join-Path $CodexRoot "skills"
$SkillPath = Join-Path $SkillsRoot "self-media-publisher"
New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null

if (Test-Path $SkillPath) {
  throw "安装目标已存在，请先按下文的升级步骤备份旧版本。"
}

Copy-Item -Recurse ".\outputs\self-media-publisher" $SkillPath
```

安装完成后，新建一个 Codex 任务，让 Codex 重新发现 Skill。可以在提示词里明确写 `$self-media-publisher`。

### 验证安装

macOS / Linux：

```bash
CODEX_ROOT="${CODEX_HOME:-$HOME/.codex}"
SKILL_PATH="$CODEX_ROOT/skills/self-media-publisher"

python3 -m unittest discover -s "$SKILL_PATH/tests" -p 'test_*.py' -v
python3 "$CODEX_ROOT/skills/.system/skill-creator/scripts/quick_validate.py" "$SKILL_PATH"
```

Windows PowerShell：

```powershell
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillPath = Join-Path $CodexRoot "skills\self-media-publisher"

py -m unittest discover -s "$SkillPath\tests" -p "test_*.py" -v
py "$CodexRoot\skills\.system\skill-creator\scripts\quick_validate.py" $SkillPath
```

测试应全部通过，快速校验器应输出 `Skill is valid!`。如果本机没有 Codex 自带的 `skill-creator` 校验器，可以跳过第二条命令；单元测试仍应执行。

## 配置微信公众号

### 1. 获取 AppID 和 AppSecret

1. 登录 [微信公众平台](https://mp.weixin.qq.com/)。
2. 在左侧进入“设置与开发” → “开发接口管理”。
3. 记录 AppID；按后台要求启用或重置 AppSecret。
4. 检查当前公众号是否具有素材管理和草稿相关接口权限。

微信后台可能调整菜单名称；找不到时可在后台搜索“开发接口管理”“AppID”或“AppSecret”。AppSecret 通常只在生成或重置时展示，请立即保存到本机私密配置，不要粘贴到聊天、Issue、日志或 Git。

### 2. 配置 API IP 白名单

仍在“开发接口管理”中找到 IP 白名单，把调用微信 API 时实际使用的公网出口 IPv4 加入白名单。

这里要注意：

- 白名单不是电脑的局域网地址，例如 `192.168.x.x`。
- 开启 VPN 或代理后，微信接口看到的可能是代理出口 IP，而不是本地运营商出口 IP。
- 如果 Clash 规则让微信 API 域名走 `DIRECT`，通常使用本地网络出口；如果走代理，则使用代理节点出口。
- 如果接口返回 `40164`，错误信息里微信实际看到的 IP 是本次请求最可靠的依据。把它与当前白名单核对后再更新，不要持续重试。
- 动态公网 IP 变化后，需要同步更新白名单。

### 3. 创建本机私密配置

配置必须放在仓库和 Skill 安装目录之外。

macOS / Linux：

```bash
mkdir -p "$HOME/.config/self-media-publisher"
cp outputs/self-media-publisher/tests/fixtures/公众号配置.example.yaml \
  "$HOME/.config/self-media-publisher/wechat.yaml"
chmod 0600 "$HOME/.config/self-media-publisher/wechat.yaml"
```

Windows PowerShell：

```powershell
$ConfigRoot = Join-Path $HOME ".config\self-media-publisher"
New-Item -ItemType Directory -Force -Path $ConfigRoot | Out-Null
Copy-Item ".\outputs\self-media-publisher\tests\fixtures\公众号配置.example.yaml" (Join-Path $ConfigRoot "wechat.yaml")
```

然后只在本机编辑 `wechat.yaml`：

```yaml
default: main
accounts:
  main:
    name: 公众号显示名
    app_id: your-app-id
    app_secret: your-app-secret
    author: 作者名
```

macOS / Linux 必须保持配置权限为 `0600`。Skill 默认把短期 access token 缓存在 `~/.cache/self-media-publisher/wechat-token.json`，该文件同样不会进入 Git；AppID 或 AppSecret 变化后，旧缓存会自动失效。

> 如果 AppSecret 曾经出现在聊天、终端录屏、Issue 或 Git 中，请先在微信后台重置，再继续配置。

## 登录小红书

小红书不需要在配置文件中保存密码、Cookie 或 token。第一次运行时：

1. 让 Skill 打开小红书创作服务平台的可见 Chrome 页面。
2. 由你完成扫码、短信、验证码、实名或设备确认。
3. 登录成功后告诉 Codex 继续。
4. Skill 会用正常页面操作填充图片、标题、正文和标签，并停在发布按钮之前供你复核。

建议使用专门用于发布的 Chrome Profile，但不要求迁移现有登录态。

## 准备输入素材

输入文件是 UTF-8 Markdown。最简单的做法是复制并修改[合成示例文章](outputs/self-media-publisher/tests/fixtures/示例文章.md)。文件需要包含：

- 一个一级标题和完整正文；
- `# 配图与插图建议` 章节；
- 从 1 开始连续编号的配图任务；
- 每张图的“位置”“作用”“尺寸建议”“可直接使用的提示词”；
- `## 给 Codex 的发布与排版要求` 章节。

最小结构如下：

```markdown
# 文章标题

正文内容……

# 配图与插图建议

## 配图 1：文章封面

**位置：** 正文最前面。

**作用：** 概括文章主题。

**尺寸建议：** 微信封面优先约 2.35:1。

**可直接使用的提示词：**

> 生成一张……

## 给 Codex 的发布与排版要求

使用专业技术长文样式，正文插图紧跟相应观点，完成后停在预览等待确认。
```

所有公众号和小红书图片都由 Codex `imagegen` 生成。解析脚本只给出候选插图位置；Codex 仍会根据文章语义和真实页面效果做最终复核与调整。

## 第一次使用

把素材文件附加到 Codex，然后发送：

```text
$self-media-publisher

请把附件文章同时准备为微信公众号和小红书。所有封面和正文配图都使用 AI 生图；公众号创建草稿，小红书填充到发布前预览。两个平台都不要正式发布，等我检查确认。
```

推荐流程：

1. Codex 解析原稿，生成统一内容包。
2. Codex 保留公众号长文，并为小红书重新组织标题、正文、标签和图片叙事。
3. Codex 使用 `imagegen` 生成并逐张检查双平台图片。
4. 在你明确授权创建真实公众号草稿后，Skill 调用微信官方 API，创建草稿并回读。
5. 在你明确授权填充小红书后，Skill 使用可见 Chrome 完成页面填充和复核。
6. 你分别检查两个平台的当前版本。
7. 只有你对当前平台版本明确说“确认发布”，Skill 才能执行该平台的一次正式发布。

运行产生的文章、图片、内容包和收据应放在当前任务的工作目录，不要写进 Skill 安装目录或提交到本仓库。

## 常见问题

### Codex 没有识别 `$self-media-publisher`

- 确认目录为 `${CODEX_HOME:-$HOME/.codex}/skills/self-media-publisher/SKILL.md`。
- 新建一个 Codex 任务后再试。
- 运行上面的安装验证命令。

### 提示缺少 `requests` 或 `yaml`

重新安装 Python 依赖：

```bash
python3 -m pip install --user requests PyYAML
```

Windows 使用 `py -m pip install --user requests PyYAML`。

### 微信配置权限错误

macOS / Linux 运行：

```bash
chmod 0600 "$HOME/.config/self-media-publisher/wechat.yaml"
```

不要通过放宽权限绕过检查。

### 微信返回 `40164 invalid ip`

停止当前创建操作，使用错误信息里的实际出口 IP 更新微信 API 白名单。确认 VPN/Clash 对微信 API 域名究竟走 `DIRECT` 还是代理后再试。

### 微信返回接口无权限

在微信后台检查公众号类型、认证状态和接口权限。换 AppSecret 或重复请求不能解决账号本身缺少权限的问题。

### 微信上传或创建草稿后结果不明

不要立刻重试。永久素材上传和 `draft/add` 不是安全的幂等操作；先在素材库和草稿箱按标题、时间核对，避免产生重复素材或重复草稿。

### 微信草稿已创建，但原创声明没有勾选

这是正常边界。官方草稿 API 的成功不代表原创声明已完成。请在微信后台打开当前草稿，完成移动端预览和原创声明，再对当前版本确认发布。如果 Codex 的浏览器安全策略拒绝访问，请由你手工完成这一步。

### 小红书要求登录、验证码或风险确认

由你在可见 Chrome 中处理，完成后再让 Codex 继续。Skill 不会读取验证码、导出 Cookie 或使用绕过手段。

### AI 图片里有错字、错误数字或裁切异常

不要进入发布确认。让 Codex 定向重生成该图，并重新检查当前平台图片顺序、裁切和内容指纹。

## 升级

先在仓库执行 `git pull --ff-only`，再备份旧安装并复制新版本。

macOS / Linux：

```bash
CODEX_ROOT="${CODEX_HOME:-$HOME/.codex}"
SKILLS_ROOT="$CODEX_ROOT/skills"
BACKUP_PATH="$SKILLS_ROOT/self-media-publisher.backup-$(date +%Y%m%d-%H%M%S)"

mv "$SKILLS_ROOT/self-media-publisher" "$BACKUP_PATH"
cp -R outputs/self-media-publisher "$SKILLS_ROOT/self-media-publisher"
```

Windows PowerShell：

```powershell
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$SkillsRoot = Join-Path $CodexRoot "skills"
$SkillPath = Join-Path $SkillsRoot "self-media-publisher"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path $SkillsRoot "self-media-publisher.backup-$Timestamp"

Move-Item $SkillPath $BackupPath
Copy-Item -Recurse ".\outputs\self-media-publisher" $SkillPath
```

升级不会修改仓库外的微信配置。复制完成后重新运行安装验证。

## 开发与验证

```bash
python3 -m unittest discover -s outputs/self-media-publisher/tests -p 'test_*.py' -v
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  outputs/self-media-publisher
```

更多运行与安全边界：

- [开源项目与许可说明](outputs/self-media-publisher/references/开源项目与许可.md)
- [双平台发布前复核清单](outputs/self-media-publisher/references/双平台发布前复核清单.md)

## 安全说明

- 不要把 AppSecret、access token、Cookie、验证码、真实文章运行包或发布收据提交到 Git。
- 不要把旧对话中的授权当作当前草稿的发布确认。
- 任一平台内容、图片、标签、可见范围或原创设置变化后，该平台旧确认立即失效。
- 外部写入结果未知时先回读或人工核对，不通过重复点击或重复请求试探。
- 本项目不会替你判断素材版权或原创资格；遇到平台权利声明时由账号持有人确认。

## License

[MIT](LICENSE)
