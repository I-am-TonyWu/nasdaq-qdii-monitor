# 纳指观察 · Nasdaq QDII Monitor

面向 Windows 的纳斯达克 100 / QDII 日常观察工具。提供本机只读网站、托盘控制、历史快照和自动采集任务。

[下载 Windows 程序 v0.4.5](https://github.com/I-am-TonyWu/nasdaq-qdii-monitor/releases/tag/v0.4.5) · [English](README.en.md) · [中文使用说明](desktop/README.zh-CN.md)

## 直接使用

1. 从 Releases 下载 `NasdaqQDII-0.4.5-Windows-x64.zip` 并解压。
2. 双击 `NasdaqQDII.exe`，首次启动会解压内置运行环境并采集数据，有快照后打开默认浏览器。
3. 右下角托盘右键，可立即采集、更新基金、补采、备份数据库和配置自动任务。

Windows 10/11 x64，.NET Framework 4.8。内置 Python 运行环境，普通使用无需安装开发工具。已有数据可离线查看；首次采集需要网络及可用的源站。

## 六个栏目

- **每日概览**：NDX、NDXTMC、QQQ走势，RSI(6)、52周高点回撤、综合观察分及可买基金。
- **估值与情绪**：TTM / Forward PE / PB / VXN / VIX / CNN FGI，联动历史曲线、历史分位与时间区间。
- **风格与技术**：VTV、CGDV、可口可乐、伯克希尔 A、罗素2000与 QQQ 的相对表现。
- **跨资产、基金与渠道、历史记录**：利率与黄金、44个人民币份额的渠道额度、历史快照与来源状态。

综合观察分保持 Forward PE 50% / VXN 30% / CNN FGI 20%。前瞻使用源站当日公布的5年分位，VXN使用3年分位，FGI使用当前值。缺少有效分项时显示缺失；尚未回测，不执行交易。

基金按“基金 → 份额 → 渠道”展示，代销与直销额度分列，共用额度单独注明。内置公告规则有有效日期，刷新时继续核对公告，不能把程序内历史额度理解为当前购买保证。

## 数据与存储

默认绑定 `127.0.0.1:8765`，网站接口只读。采集和文件写入通过本机命令及托盘执行。邮件任务默认仅保存预览。

运行文件位于 `%LOCALAPPDATA%/NasdaqQDII`，数据保存在独立工作目录。从项目发布目录首次启动时可识别已有项目，也可明确指定：

```powershell
.\NasdaqQDII.exe --home "D:\NasdaqMonitorData"
```

公开仓库和安装包不附带行情历史、提供方缓存、个人渠道确认、账号配置、密钥或聊天资料。[数据来源与口径](docs/DATA_SOURCES.md)说明发布方、代理序列与可得历史边界。源站的数据许可独立于程序代码，Dollar Liquidity 采集仅用于本机显示，不提供估值导出或公开分发。

## 从源码运行

Python 3.12，Windows x64。在项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 collect
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 serve
```

`config.example.json`可复制为 `config.local.json`；个人配置已忽略 Git。项目依赖锁定在 `requirements.lock`，采集失败保留旧值并标记失效，不填充虚构数据。

## 构建与验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File .\scripts\build-desktop.ps1
```

Windows自带 C# 编译器构建托盘，内嵌私有 Python 运行包。干净检出的单元测试无需下载行情；4项依赖本地采集快照的集成检查会跳过。私有快照不会提交到仓库。

实际 EXE 验证脚本 `scripts/verify_desktop.py`需要已构建 EXE 和本地快照。网页验证使用 Node.js、Playwright 和 Microsoft Edge，可通过 `NASDAQ_NODE`与 `NASDAQ_PLAYWRIGHT`指定运行路径。验证使用隔离数据、临时端口与临时任务，实际运行备份任务；不采集上游，不发送邮件。

v0.4.5在本机通过99项后端测试、35项封装检查和16项网页检查。[发布记录](docs/RELEASE-v0.4.5.md)列出覆盖与尚未实测的边界。[第三方组件与数据来源](THIRD_PARTY.md)保留许可和参考说明。
