# v0.1.0 实现状态

更新日期：2026-09-19

这份文件区分“仓库中已经实现并在开发机验证的能力”和“正式发布前仍需完成的门槛”。它不是发布公告，不能替代真实用户试用、干净机器测试或安装包验收。

## 已实现并已验证

- 三个声明式事务模板均可加载和校验：活动组织、材料收集、报销。
- 事实字段支持 `missing`、`extracted`、`confirmed`、`changed`、`conflicting` 状态和事实快照版本。
- 只有 `confirmed` 事实会进入可发布渲染；缺失事实保留明确占位。
- 草稿记录事实版本与引用字段；相关事实变化时，旧草稿会标记为 `stale`，历史版本不会被覆盖。
- 支持离线通知、提醒和推文结构，以及可选的 OpenAI Responses API 事实提取、文案生成和风格卡生成。
- AI 请求设置 `store: false`；API Key 设计为仅由 Rust 层访问 Windows Credential Manager。
- 支持风格样本导入预览、疑似个人信息提示、可编辑风格卡和提取文本删除。
- 支持事务待办、提醒偏移、截止时间变化后的提醒状态重置和提醒去重。
- Windows 11 已验证 24 小时、2 小时、到期、重启、休眠恢复、权限拒绝、开机启动关闭和完全退出提醒矩阵。
- 支持材料槽位、文件哈希、文件变化、重复文件、扩展名与文件签名不一致、缺项及报销凭证检查。
- 支持 ZIP、JSON、HTML、PDF 和 DOCX 归档输出，并在导出时重新检查源材料哈希。
- React 浏览器演示模式、Python sidecar、维护者 CLI 和 PyInstaller 打包链路均已运行验证。

本轮本机验证结果：

```text
python -m pytest       34 passed
npm test               17 passed
npm run build          passed
GitHub Windows cargo check passed
冻结 CLI                0.1.0，可正确输出中文
冻结 sidecar            JSON Lines 请求与中文响应正常
```

## 当前验证边界

- GitHub Actions 和 Windows 开发机均已通过 `cargo check`，本机已完成 `tauri dev` 桌面联调；最终 `tauri build` 安装包推迟到 issue #17。
- Python 3.12 sidecar 和 CLI 已按仓库脚本重建并记录文件大小与 SHA-256。
- 尚未在无 Node.js、Python、Rust 的干净 Windows 10/11 x64 机器上验收 NSIS、MSI、便携包和 CLI。
- 提醒矩阵已完成 Windows 11 开发桌面验证；最终安装包仍需在 issue #17 恢复后重复提醒冒烟测试。
- 材料归档的磁盘空间不足场景仍有失败输出清理和中文提示问题，见 issue #7。
- 尚未完成至少 6 名目标用户、3 次活动组织、3 次材料收集和 2 次报销整理的试用门槛。
- GitHub、npm、PyPI、域名和商标同名检查尚未完成，`CHANGELOG.md` 的发布日期仍为 `TBD`。

## 发布判定

当前仓库适合继续开发、代码审查和试用准备，但不应标记为正式发布的 `v0.1.0`。只有 [发布检查清单](release-checklist.md) 中的自动检查、干净机器测试、真实用户门槛和发布资料均完成后，才能创建 Git 标签和 GitHub Release。
