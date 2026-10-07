# 第三方依赖与参考

- **Chart.js 4.5.1**：用于实际历史数据图表，MIT；本地文件`web/vendor/chart.umd.js`，保留`web/vendor/Chart-LICENSE.md`。来源 https://www.chartjs.org/ 和 https://github.com/chartjs/Chart.js 。
- **FastAPI 0.142.2 / Uvicorn 0.54.0 / Requests 2.34.2**：本机只读服务和HTTP访问；各项目许可证随Python发行包安装。
- **AKShare 1.19.1**：调用`fund_purchase_em`取得天天基金申购状态；MIT。https://github.com/akfamily/akshare 。该函数原HTTP请求无超时，本项目放在有75秒总超时的子进程中运行。
- **exchange-calendars 4.13.2 / tzdata 2026.5**：美国交易日、节假日、提前收盘和夏令时。
- **curl_cffi 0.16.3**：公开行情、公告和估值页面的TLS兼容传输。
- **agent-browser 0.38.2**：仅作为忽略Git的本机验证工具，Apache-2.0，不是产品运行依赖。

设计及采集方式参考：

- https://github.com/zhouminghan/qdii-tracker （MIT）：基金表、折叠层级与采集模块参考。本版独立实现界面，不采用其“纳指科技”排除规则，不复制整仓前端，不让浏览器直连上游。
- https://github.com/aiten2/qdii-purchase-limits （MIT）：份额/渠道/证据与变化记录设计参考；本版独立实现公告规则与逐份额更新监测。
- https://www.wsj.com/market-data/stocks/peyields ：WSJ / Birinyi Associates公布的NASDAQ 100当前PE，周频、有该表自身日期；脚注明确TTM as-reported及forward operating。
- https://github.com/siblisresearch/global-equity-valuations-api ：Siblis官方免费API说明；独立保存稀疏历史参照，不拼接WSJ分位，不访问付费接口。数据口径、使用与再展示须遵循提供方条款。
- Cboe官方CSV优先取得VXN/VIX日线CLOSE，Yahoo Chart分别核对；Nasdaq官方最新页/FRED历史和财政部XML同样分别保留发布方及分发器来源。
- 管理人正式公告采用东方财富公开披露的原公告文本核对，证据保留原PDF链接；天天基金实际产品页用于普通申购/定投入口和起购金额，目录接口仅作初筛。公告与产品页虽是不同文件，不能称为两家独立数据商互证。

- 股叉叉 https://guchacha.com/index-valuation/NDX ：仅作独立周频TTM/PB参考，底层细则及自动同步用途待核验，不混入WSJ、不参与评分；同日重复采集使用低频缓存。
- BeautifulSoup 4.15.0：公开HTML表结构解析，MIT，许可证随发行包安装。

软件许可证与行情、基金数据的公开再展示权是两件事。本机试采不意味着可以公开复制所有上游数据。没有复制未声明许可项目的代码。

本地Chart.js文件SHA-256：`ecc3cd1eeb8c34d2178e3f59fd63ec5a3d84358c11730af0b9958dc886d7652a`。

## v0.4 字体、配色与外部展示

- Inter Variable 5.3.0：来自 `@fontsource-variable/inter`，OFL-1.1；字体许可保存在 `web/vendor/ui/inter/LICENSE`，只自托管 Latin 正常体的可变字重，中文明确使用系统字体回退。
- Radix Colors 3.0.0：MIT；只引入 Slate、Teal、Blue、Red、Amber、Violet 色阶，许可保存在 `web/vendor/ui/radix/LICENSE`。包版本、SHA-512 完整性和资源 SHA-256 见 `web/vendor/ui/asset-manifest.json`，可用 `scripts/vendor_ui_assets.py` 重现。
- [Dollar Liquidity 纳斯达克100 Forward PE](https://dollarliquidity.com/en/valuation/nasdaq-100-forward-pe)：v0.4.1按用户要求直接解析公开页面JSON，保存独立估值序列、日期与来源证据，由本机图表展示。v0.4.2综合评分改用源站公布的当前5年分位；近期日线和早期图表采样分别识别，原站报告样本数与本机取得数分别记录。当前分位与历史曲线的采集能力分开，不拼接WSJ、不导出估值文件。此估值数据[许可](https://dollarliquidity.com/en/license)为仅展示、不可再分发；当前服务只监听127.0.0.1，抓取序列标记`local_display_only`，没有公开分发授权。

## v0.5 远程连接器

- Cloudflared 2026.10.0（Windows amd64）：Apache-2.0。官方发布 https://github.com/cloudflare/cloudflared/releases/tag/2026.10.0 ，官方 EXE SHA-256 `86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c`。构建时校验摘要，运行包保留 `cloudflared/LICENSE` 和 `cloudflared/version.json`。私人远程访问功能不改变上游数据许可，不构成公开再分发授权。
