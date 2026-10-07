# v0.5.0 · 设置窗口与私人远程访问

发布日期：2026-10-07。下载：[GitHub Release](https://github.com/I-am-TonyWu/nasdaq-qdii-monitor/releases/tag/v0.5.0)。历史版本：[v0.4.5](https://github.com/I-am-TonyWu/nasdaq-qdii-monitor/releases/tag/v0.4.5)，保留其标签和原安装包。

## 修订

- 设置窗口拆分为运行与数据、自动任务、远程访问，采用内容自适应布局、统一 DPI 基准、可调窗口与滚动。修复旧窗口按钮/文字重叠和裁切，小窗口压缩页头留白。
- 时间计划改为对齐表格，端口、数据目录与采集操作独立分组。保留原网站配色方向与系统字体，减少重复说明。
- 内置官方 cloudflared 2026.10.0，构建时校验官方发布的 SHA-256 并保留 Apache-2.0 许可。
- 支持独立远程管理隧道、指定邮箱 Access、DNS 配置、DPAPI 密文、异步保护核对、连接恢复、暂停和退出清理。支持复用 codex-web 的管理 API Token，不共享隧道运行凭据。
- API 权限失败时保持禁用；Access 先于 DNS 配置，连接器强制验证 Access JWT；不自动覆盖无关资源。详见[远程访问说明](REMOTE_ACCESS.md)。

## 验证

| 范围 | 结果 |
| --- | --- |
| Python 后端 | 99 项本机回归通过；干净公开检出跳过 4 项本地快照检查 |
| 实际安装包 | 37 项 EXE/运行环境/数据/服务/任务验证通过 |
| 网页 | 16 项桌面与手机六栏目及图表联动检查通过 |
| 原生设置与远程保护 | 55 项检查通过，含 100/125/150/200% 显式缩放模拟、小窗口、秘密密文、策略限制、资源冲突、失败禁用与请求取消 |
| 看图 | 主机真实 EXE 打开复核；隔离看图评审一轮，没有发现重叠或控件内文字截断；小窗口空间建议已调整 |

现有管理 Token 的 DNS 读取真实返回 403。本机用户选择先发布客户端，云端配置稍后进行；`nasdaq.tonywu.link` 尚未启用。公网登录、隧道真实恢复、其他实体设备、Windows 重启/登录恢复和长时间运行未完成实测。显式缩放截图不等同于每种物理显示器的 Windows DPI 切换测试。

安装包和公开源码不包含个人邮箱配置、Token、隧道凭据、实际行情历史或聊天资料。每版提供独立 EXE、ZIP 与 SHA-256 校验文件；EXE 未签名。升级保留数据与私人配置，退出托盘后启动新版，再按需修复自动任务。

## English

v0.5.0 fixes clipped/overlapping native settings with responsive tabs, explicit DPI layout and scrolling. It adds bundled cloudflared, a dedicated private tunnel, mailbox-only Access, DNS setup and encrypted credentials. Reusing codex-web's management API token does not share its tunnel or modify its Access policy.

Validation: 99 local backend tests, 37 EXE checks, 16 browser checks and 55 native layout/protection checks passed. An independent static visual review found no overlap or control text clipping. Synthetic DPI checks and actual host-window inspection do not replace testing every physical display.

Live cloud setup is deferred: the existing token lacks DNS access. Real mailbox login, tunnel recovery, another device, reboot/login recovery and prolonged operation remain unverified. Release assets exclude personal configuration, credentials, market history and chat data. v0.4.5 remains available with its original assets.
