# v0.4.5 · Windows 程序 / Windows desktop release

发布日期：2026-10-07。下载：[GitHub Releases](https://github.com/I-am-TonyWu/nasdaq-qdii-monitor/releases/tag/v0.4.5)。

## 交付

- 单个 Windows x64 EXE，内置 Python 3.12.14 和46个运行依赖。
- 托盘管理网站、采集、基金更新、补采、数据库备份、端口与登录启动。
- 自动任务安装与修复，保留正在运行的原项目服务任务；同目录原任务先备份XML，其他目录的同名任务拒绝覆盖。
- 稳定启动文件、版本运行目录与数据分开；已有项目可直接沿用数据。
- 中英使用说明、依赖清单和SHA-256校验文件。

## 验证

| 范围 | 已通过 |
| --- | --- |
| 本机后端回归 | 99项，包括本地快照检查 |
| 实际EXE验证 | 35项，包括5886个文件SHA-256核验、中文长路径、无需系统Python、单实例、端口冲突保护、服务生命周期与原服务保留 |
| 浏览器验证 | 16项；1440px和390px下六栏目、Forward PE双图同步和脚本错误 |
| Windows任务 | 隔离任务实际运行pythonw备份；重复修复与其他目录保护；临时任务已删除 |
| 文件交付 | EXE/ZIP摘要一致，ZIP内容核对通过；脚本经过Windows PowerShell 5.1解析并保留UTF-8 BOM |

公开源码的干净检出单元测试不要求行情缓存；4项使用本地快照的集成检查会显式跳过。测试夹具为构造数据，公开仓库不包含实际行情快照或个人渠道确认。

其他实体电脑、系统重启/登录恢复、长时间运行及设置窗口人工逐按钮验收尚未覆盖。设备登录、网络和源站可用性会影响定时采集。数据库备份仅包含SQLite库；完整迁移需另复制完整工作目录。

## English

The Windows x64 tray program embeds Python 3.12.14, manages the existing loopback dashboard, and separates runtime versions from working data. It preserves an attached original service on exit. Scheduled-task updates export existing same-home tasks before replacement and refuse tasks from another data home.

Local validation passed 99 backend tests, 35 actual EXE checks and 16 desktop/mobile browser checks. A clean public checkout skips four snapshot-dependent integration checks. Other physical PCs, reboot/login behavior and prolonged operation remain unverified.

This release excludes market history, provider caches, personal confirmations, configuration secrets and chat content. Provider data permissions remain applicable. Checksums accompany the release; the EXE is not code-signed.
