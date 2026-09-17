# 轻务 Qingwu

[![CI](https://github.com/Caspian315/QingWu/actions/workflows/ci.yml/badge.svg)](https://github.com/Caspian315/QingWu/actions/workflows/ci.yml)

> 围绕一项学生工作事务，只录入一次事实，辅助生成通知、提醒和推文，并一路管理待办、材料和最终归档。

轻务是面向团支书、班委、学生会和社团骨干的 Windows 本地事务工作台。它不是学校管理后台，也不是一个空白 AI 聊天框。每项工作都围绕同一个对象组织：

```text
事务
├── 事实底稿
├── 通知、提醒与推文
├── 时间线与待办
├── 材料
└── 检查与归档
```

时间、地点、联系人、金额等关键事实以 `{{fact.key}}` 引用节点进入文案。只有用户确认过的事实才会渲染；事实变化后，只让实际引用该字段的旧草稿进入 `stale` 状态。AI 能加速提取和写作，但没有 API Key、断网或 API 失败时，本地闭环仍然可用。

## 当前状态

仓库目前是 `v0.1.0` 的可运行实现基线，包含：

- Tauri 2 + React + TypeScript 桌面工作台和浏览器演示模式；
- Python 3.12 sidecar、SQLite 数据库和 JSON Lines 接口；
- 活动组织、材料收集、报销三个声明式 YAML 模板；
- 事实快照、确认状态、定向草稿过期和文案版本；
- 确定性离线文案与可选 OpenAI Responses API；
- 本地时间线、提醒去重、系统托盘和 Windows 通知；
- 材料槽位、SHA-256、缺项检查和 ZIP/HTML/PDF/DOCX 归档；
- 维护者 CLI、自动测试、CI、隐私与模板开发文档。

首版明确不自动发送群消息、不读取微信或 QQ、不自动发布公众号、不判断发票真伪，也不修改用户原文件。

已验证能力与尚未满足的发布门槛见 [v0.1.0 实现状态](docs/implementation-status.md)。当前状态是开发实现基线，不是正式发布版。

## 快速体验

### 只看界面和基础流程

浏览器演示模式把测试数据放在浏览器 `localStorage`，不会启动 Python，也不支持真实材料路径、Credential Manager 和归档写盘。

```powershell
npm install
npm run dev
```

访问终端显示的本地地址即可。正式构建：

```powershell
npm test
npm run build
```

### Python 核心与 CLI

维护者环境使用 Python 3.12：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
qingwu template validate .\templates\activity-organization.yaml
```

创建过事务后，事务标记目录位于轻务数据目录的 `affairs\<事务 ID>`。CLI 可检查和导出该目录：

```powershell
qingwu affair check "<事务目录>" --format human
qingwu affair check "<事务目录>" --format json
qingwu affair export "<事务目录>" --output ".\exports\事务名称.zip"
```

CLI 默认不会调用 AI。

### Windows 桌面版

需要 Node.js、Rust stable、Python 3.12 和 WebView2：

```powershell
npm install
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\build-sidecar.ps1 -Python ".\.venv\Scripts\python.exe"
npm run tauri dev
```

`build-sidecar.ps1` 使用 PyInstaller 生成无需终端用户安装 Python 的 sidecar，并拒绝使用 Python 3.12 之外的解释器。发布安装包前执行：

```powershell
.\scripts\build-cli.ps1 -Python ".\.venv\Scripts\python.exe"
npm run tauri build
```

## 数据与隐私

- 事务数据默认写入 `%LOCALAPPDATA%\Qingwu\qingwu.sqlite3`。
- OpenAI API Key 仅由 Rust 层保存到 Windows Credential Manager。
- AI 请求明确使用 `store: false`。
- 历史 DOCX/PDF 默认先在本地提取文本；原文件不上传、不修改。
- 归档包不包含 API Key、绝对路径、Windows 用户名、历史样本文本或 AI 原始请求/响应。
- 标记为 `sensitive` 的事实默认不进入 `qingwu-manifest.json`。

更多边界见 [隐私设计](docs/privacy.md) 与 [安全政策](SECURITY.md)。

## 目录结构

```text
src/                    React 工作台与浏览器演示适配器
src-tauri/              Tauri、托盘、通知、凭据与 sidecar 桥接
python/qingwu_core/     事务、事实、文案、材料、AI 与归档核心
templates/              三个内置事务模板
schemas/                事务模板 JSON Schema
python/tests/           核心行为测试
docs/                   架构、模板和发布说明
scripts/                sidecar 打包脚本
```

## 核心接口

桌面层通过一行一个 JSON 对象与 sidecar 通讯：

```json
{"id":1,"method":"affair.open","params":{"id":"affair_..."}}
```

已实现计划中的全部公共接口，包括 `profile.*`、`style.*`、`template.validate`、`affair.*`、`fact.*`、`draft.*`、`timeline.*` 和 `material.*`。额外提供 `template.list`、`affair.list`、`group.*`、`recipient.*` 与内部提醒轮询接口。

架构和安全理由见 [架构说明](docs/architecture.md)，模板字段见 [模板开发指南](docs/template-development.md)。

## 参与贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。不要把真实姓名、手机号、学号、票据、支付凭证、API Key 或组织内部材料提交到 issue、测试 fixture 或仓库。

## License

[MIT](LICENSE)
