# 数据来源与口径 / Data sources and methods

| 数据 | 来源与使用方式 |
| --- | --- |
| NDX / NDXTMC | Nasdaq 官方最新值与 FRED 历史，Yahoo及东方财富用于回退或核对；保留发布方和分发器，Nasdaq与FRED不当作独立发布方 |
| QQQ及其他价格序列 | Yahoo Chart，实际观察日期与盘中高点独立保存；ETF不冒充指数正式估值 |
| VXN / VIX | Cboe官方CSV优先，Yahoo分别核对；两指数保持分开 |
| 当前正式PE | WSJ / Birinyi，按该表日期和脚注分开TTM as-reported与Forward operating；不拼接不同盈利口径 |
| Forward PE展示与评分 | Dollar Liquidity公开页面的独立序列与当日5年分位；近期日线、长历史图表采样和原站报告样本数分别记录 |
| TTM / PB历史参考 | 独立周频参考，与正式WSJ发布值分组；周频不复制为日频 |
| 情绪 | CNN Fear & Greed，当前值用于评分 |
| 利率、黄金 | 美国财政部/FRED名义及实际收益率；黄金为近月期货代理，移仓会影响收益 |
| 基金份额及渠道 | 管理人公告与天天基金实际产品页；公告上限、当前受理状态、起购金额及份额共用关系分别记录 |

源站发布时间可能晚于北京时间晨间窗口。失败、迟到、休市、修订与历史缺口分别显示，缓存读取时重新检查有效期。来源不足时不补造分位或评分。

NDXTMC和CGDV的历史可得范围受发布起点及成立日限制。1/3/5/10/20年选项展示实际可得数据，不生成成立前历史。估值序列口径不能通过最高/最低值或不同来源拼接成完整经验分布。

用户自行确认的渠道保存在私有 `config/manual_channels.json`，不随公开仓库或安装包分发，也不会通过自动采集延长确认时间。

Data methods, observation dates, collection timestamps and provider identities remain explicit. A missing or stale input stays missing; genuine weekly observations are not duplicated into daily history. Public software distribution does not grant permission to redistribute provider data.

第三方组件许可和具体来源链接见[THIRD_PARTY.md](../THIRD_PARTY.md)。
