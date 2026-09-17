# 轻务架构说明

## 进程边界

```text
React UI
   │ Tauri invoke
   ▼
Rust 桥接层 ── Windows Credential Manager
   │ JSON Lines stdin/stdout
   ▼
Python sidecar
   ├─ SQLite 与事务模板
   ├─ 事实和文案版本
   ├─ OpenAIProvider
   ├─ 材料检查
   └─ 归档导出
```

应用不启动本地 HTTP 服务。Rust 启动一个长期运行的 sidecar，所有请求和响应都是单行 JSON。开发模式使用 `python -m qingwu_core.sidecar`；打包模式使用 PyInstaller 生成的 `qingwu-sidecar.exe`。

API Key 不跨越到 React。前端只发送 `use_saved_api_key: true`，Rust 在确实需要 AI 的调用中临时从 Credential Manager 读取并注入 sidecar 请求。Python 不记录请求正文和响应正文，`ai_runs` 只保存用途、模型、成功状态和错误码。

## 事实一致性

每项事务有不可变的事实快照序列：`facts-v1`、`facts-v2`……。字段状态为：

- `missing`：没有值；
- `extracted`：候选值，必须确认；
- `confirmed`：唯一允许进入渲染结果的状态；
- `changed`：确认后又被编辑，重新确认前不进入文案；
- `conflicting`：来源中存在冲突。

文案正文保存引用节点而不是关键事实文本。渲染发生在复制、预览和导出前。每个文案版本同时记录 `fact_version` 和 `used_fact_keys`；事实更新时取字段交集，只把受到影响的文案标为 `stale`。

## 离线与 AI

`offline_template` 是确定性降级路径。AI 生成文案时，受保护字段只以 `{{token}}` 和字段含义提供，模型不能自由改写值；返回后再校验必需 token。AI 结果一律从 `needs_review` 开始。

事实提取使用结构化 JSON Schema。相对日期保留 `original_text`，并带 `needs_date_confirmation`；服务只写入 `extracted`，绝不自动确认。

## 材料安全

材料导入只保存绝对来源路径、大小、扩展名和 SHA-256，不移动或修改源文件。检查时重新计算哈希，区分“移动或删除”和“内容变化”。归档复制前、复制后分别校验哈希；模板输出路径经过路径穿越检查。

## 提醒语义

Python 计算到期提醒，Rust 每分钟轮询并使用 Windows 通知。已发送记录的键由 `due_at|offset_minutes` 组成；重启不会重复发送。修改截止时间会清空对应待办的已发送记录。关闭窗口只隐藏到托盘，托盘菜单的“完全退出（停止提醒）”才结束进程。
