# v0.1.0 发布检查清单

## 自动检查

- [x] `python -m pytest`（Python 3.12 候选构建：23 passed）
- [ ] `npm test`
- [ ] `npm run build`
- [ ] `cargo check --manifest-path src-tauri/Cargo.toml`
- [x] 三个内置模板通过 `qingwu template validate`
- [ ] PyInstaller sidecar 能在无 Python 的 Windows 10/11 x64 环境启动
- [ ] NSIS/MSI、便携包和 CLI 计算 SHA-256

Python 3.12 CLI 与 sidecar 的构建来源、验证结果和 SHA-256 见 [v0.1.0 Python 候选产物记录](v0.1.0-python-artifacts.md)。

## 端到端场景

- [ ] 活动组织至少 3 次
- [ ] 材料收集至少 3 次
- [ ] 报销整理至少 2 次
- [ ] 相对日期必须人工确认
- [ ] 事实修改只让相关草稿过期
- [ ] 断网和 API 失败仍可走完事务闭环
- [x] 休眠恢复、重启和修改截止时间后不重复提醒（见 [Windows 提醒测试矩阵](windows-reminder-validation.md)）
- [ ] 中文、长路径、文件移动、内容变化、重复文件、磁盘不足和输出冲突
- [ ] 导出前后材料 SHA-256 一致

## 隐私与安全

- [ ] 数据库、日志、归档中搜索不到测试 API Key
- [ ] 归档 manifest 不含绝对路径、用户名和敏感事实值
- [ ] 历史样本文本删除后风格卡仍可使用
- [ ] 路径穿越 fixture 被拒绝
- [ ] 测试 fixture 不含真实个人信息或票据

## 真实用户门槛

- [ ] 至少 6 名目标用户，覆盖团支书、班委和社团成员
- [ ] 5 分钟内从上级通知创建事务、确认事实并生成首版通知
- [ ] 记录完成时间、文案修改次数、事实错误、漏项和错提醒
- [ ] 所有阻断问题修复或明确推迟并写入 CHANGELOG

## 发布资料

- [ ] GitHub、npm、PyPI、域名和商标同名检查
- [ ] README、LICENSE、CHANGELOG、CONTRIBUTING、SECURITY 完整
- [ ] 版本号在 npm、Python、Tauri、Cargo 中一致
- [ ] 为 `v0.1.0` 创建带校验和的 GitHub Release
