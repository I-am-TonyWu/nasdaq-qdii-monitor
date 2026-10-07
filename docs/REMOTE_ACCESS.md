# 私人远程访问 / Private remote access

v0.5.0 新增 Windows 客户端内置的 Cloudflare 配置与连接功能。原网站继续只监听 `127.0.0.1`；Cloudflare 为允许的本人邮箱提供 HTTPS 登录入口。默认域名 `nasdaq.tonywu.link`，远程连接默认关闭。软件功能不代表取得上游数据的公开再分发授权。

## 配置

1. 打开托盘 → 设置与自动任务 → 远程访问。
2. 填入域名、账户 ID、域名区域 ID、Zero Trust 团队名和允许登录的邮箱。
3. 选择共用 codex-web 已加密保存的 API Token，或填写独立 Token。
4. 点击检查 Token，核对有效性、账户、域名和读取权限。
5. 点击配置并启用，完成 Access、独立隧道和 DNS 的创建及重新读取核对。

需要自定义 **用户 API Token**，资源范围限定为相应账户和域名区域：

| 资源 | 权限 |
| --- | --- |
| Account | Cloudflare Tunnel / Edit |
| Account | Access: Apps and Policies / Edit |
| Zone | DNS / Edit |
| Zone | Zone / Read |

其中隧道和 DNS 的创建权限见 [Cloudflare 官方隧道 API 指南](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel-api/)，Access 权限见 [创建 Access 应用 API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/methods/create/)。区域读取用于客户端核对域名与账户。

“检查 Token”不能单凭读取成功证明编辑权限。配置阶段会验证实际编辑操作；403 表示权限或资源范围不满足要求。新 Token 请在客户端输入，不发送到聊天，不写入源码。

## 与 codex-web 共用 Token

**可以共用管理 API Token，但不能共用隧道的运行 Token。** 本程序从当前 Windows 用户注册表中的 codex-web DPAPI 密文读取管理 Token；不覆盖它。若撤销或修改这个 Token，两款程序的管理操作都会受影响。

本程序建立独立的 Access 应用、策略和 remotely-managed tunnel，隧道 Token 只用于连接该隧道。API Token 与 tunnel Token 的区别见 [Cloudflare 官方说明](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/)。停止本程序不会关闭 codex-web。

## 保护与恢复

- 先建立指定邮箱 Allow 的 Access 应用，重新读取邮箱规则，才配置路由和 DNS。已有其他域名资源不会自动接管或覆盖。
- 连接器要求 Access JWT，校验团队和应用 audience；匿名请求不能到达本地网站。配置方式见 [Cloudflare origin Access 参数](https://developers.cloudflare.com/tunnel/reference/origin-parameters/#access)。
- 凭据以当前用户 DPAPI 密文保存在 `%LOCALAPPDATA%\NasdaqQDII\secrets`，通过子进程环境传给 cloudflared，不出现在命令行、日志和发布包中。
- 配置保存于 `%LOCALAPPDATA%\NasdaqQDII\remote.json`，含域名、邮箱与资源 ID，属于私人配置。部分成功时保存资源 ID，失败保持禁用，解决权限后可继续配置；请求超时后先在控制台核对，避免重复创建。
- 连接前重新核对 Access 和隧道路由，读取请求在后台运行，暂停/退出不会等待云端请求。cloudflared 由 Windows Job 管理，退出时只停止自身连接器。连接断开由连接器重连；进程退出后 30 秒重试。

已配置应用后，客户端不会覆盖云端 Access 白名单。如果更改邮箱导致本机与云端不一致，连接会停止；请先在 Cloudflare 核对当前应用，再同步私人配置，不要通过添加 Everyone/Bypass 绕过。

设备与托盘需持续运行。可启用 Windows 登录启动；关闭窗口不等于退出。暂停保留云端 Access/DNS。修改本机端口后，需要重新配置隧道。迁移时，DPAPI 密文不能直接给其他 Windows 用户使用，应重新配置 Token。

## 验证边界

本版通过构造 API 响应的保护、隔离资源、冲突拒绝、失败禁用、异步取消测试，以及实际 Windows EXE、布局和网页验证。已对现有 Token 进行真实只读检查，DNS 请求返回 403，云端设置尚未启用。真实邮箱登录、连接器恢复和另一设备访问尚未完成端到端验证，不能称为线上远程访问已通过。

## English

The Windows client configures a dedicated tunnel, mailbox-only Access application and proxied DNS record. Remote access is disabled by default. Reuse the current-user DPAPI-protected codex-web API token or enter an independent user API token with Tunnel Edit, DNS Edit, Zone Read and Access Apps/Policies Edit scoped to the relevant account and zone.

Management API tokens can be reused across applications; each tunnel has a distinct runtime token. Existing codex-web resources are never modified. Access is created and verified before DNS publication, and cloudflared also validates Access JWTs. Secrets are encrypted at rest and passed in process environment, not command arguments or release packages.

Local and synthetic verification does not establish live cloud operation. This release has not verified real mailbox login, tunnel recovery or another device end to end. Keep the computer/tray running, repair permissions before configuration, and reconfigure after changing the local port. Source-provider terms still apply.
