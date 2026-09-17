# 事务模板开发指南

事务模板是声明式 YAML，不能包含 Python、JavaScript、PowerShell、Shell、命令或其他可执行内容。当前 schema 版本为 `1`。

## 最小模板

```yaml
schema_version: 1
id: example-workflow
version: 1.0.0
title: 示例事务
description: 一个最小示例
license: MIT
min_app_version: 0.1.0

facts: []
stages: []
tasks: []
documents: []
material_slots: []
groups: []
archive: {}
```

使用 CLI 校验：

```powershell
qingwu template validate .\templates\example-workflow.yaml
```

## 事实字段

```yaml
- key: deadline
  label: 截止时间
  type: datetime
  required: true
  protected: true
  sensitive: false
```

`key` 在同一模板内唯一。`protected` 表示该值应通过引用节点进入文案。`sensitive` 表示默认不把值写进归档 manifest。支持 `text`、`textarea`、`date`、`time`、`datetime`、`integer`、`decimal`、`currency`、`select` 和 `checkbox`。

## 文案

```yaml
- id: deadline_reminder
  title: 截止前提醒
  kind: reminder
  required_facts: [collection_name, deadline]
  offline_template: |
    {{collection_name}}将于{{deadline}}截止，请及时提交。
```

缺失或未确认的节点渲染为 `【待填写：字段名称】`。不要把关键时间、地点、联系人、金额或数量硬编码在模板正文中。

## 待办

```yaml
- id: send_reminder
  title: 发送截止前提醒
  stage: remind
  relative_to: deadline
  offset_minutes: -1440
  reminders: [1440, 120, 0]
```

`relative_to` 必须引用同一模板的事实字段，`stage` 必须存在。无法解析或尚未确认时，待办保留但没有自动截止时间。

## 材料槽位

```yaml
- id: photos
  title: 活动照片
  required: true
  min_items: 3
  max_items: null
  extensions: [.jpg, .jpeg, .png]
  filename_keywords: [活动, 合影, 现场]
  output_path: materials/03-活动照片
```

扩展名和文件名只用于确定性推荐；用户最终确认槽位。`output_path` 必须是安全相对路径，不能包含盘符或 `..`。

## 可重复项目

报销等事务可以在 `groups` 中声明可重复项目，并为每个实例配置自己的事实和材料槽位。校验器会逐项检查必填用途、日期、金额、票据和支付凭证，不判断票据真实性。

## 兼容性

- 模板升级必须修改 `version`；
- `schema_version` 发生不兼容变化时才递增；
- 已发布模板不要删除或改变既有 key 的含义；
- 新字段优先设为可选，避免破坏旧事务；
- 提交模板时增加一个从创建到归档的端到端 fixture。
