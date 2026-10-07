import hashlib
import html
import json
import os
from pathlib import Path
import requests
from .calendar import now_iso,market_context
from .settings import DATA,CONFIG
from .storage import connect,latest,get_snapshot
from .presentation import for_display
from .fund_evidence import eligible

def fmt(value, digits=2):
    return '未取得' if value is None else f'{value:,.{digits}f}'

def render(snapshot):
    esc=html.escape
    context=snapshot.get('current_market',snapshot['market'])
    session=context['expected_us_session']
    lines=[f"纳斯达克与QDII早报 · {context['beijing_date']}",
           f"应更新至美国交易日：{session}；{context['session_note']}",f"快照：{snapshot['id']}；采集时间：{snapshot['generated_at']}"]
    for key in ('NDX','NDXTMC','QQQ','VXN','VIX','FGI','GOLD','DGS2','DGS10','DFII10'):
        item=snapshot['series'].get(key,{})
        lines.append(f"{item.get('name',key)}：{fmt(item.get('value'))}；日期 {item.get('date') or '未取得'}；状态 {item.get('status','missing')}；变化 {fmt(item.get('changes',{}).get('1'))}{'bp' if key in ('DGS2','DGS10','DFII10') else '%'}")
    t=snapshot['technical']
    lines.append(f"NDX RSI(6/14/24)：{' / '.join(fmt(t.get('rsi',{}).get(str(p))) for p in (6,14,24))}；200日均线距离 {fmt(t.get('ma200_distance'))}%；52周回撤 {fmt(t.get('drawdown_52w'))}%")
    for kind,label in (('forward','前瞻PE'),('ttm','TTM PE')):
        from .analytics import score_forward
        item=score_forward(snapshot) if kind=='forward' else snapshot['valuation'][kind]
        origin='源站公布' if item.get('percentile_origin')=='publisher_reported' else '本站计算'
        lines.append(f"{label}：{fmt(item.get('value'))}；5年分位 {fmt(item.get('percentile'))}%（{origin}）；日期 {item.get('date') or '未取得'}；来源 {item.get('source','未取得')}")
    lines.append('综合观察分：'+fmt(snapshot['score']['value']))
    lines.extend(snapshot['score']['reasons'])
    lines.append('初始规则50/30/20，尚未回测；TTM仅展示。')
    for key,item in snapshot['pairs'].items():
        lines.append(f"{key}/QQQ ROC(35)：{fmt(item['roc']['35'])}%；截至 {item.get('date') or '未取得'}")
    lines.append(f"基金目录 {len(snapshot['funds'])} 个主行，{sum(len(f['shares']) for f in snapshot['funds'])}个份额；已核验可买份额 {sum(f.get('verified_shares',0) for f in snapshot['funds'])} 个。")
    for fund in snapshot['funds']:
        for share in fund['shares']:
            for ch in share['channels']:
                if eligible(ch):
                    lines.append(f"{share['code']} {share['name']} · {ch['channel']} {ch['method']} · 日上限 {'小于' if ch.get('limit_inclusive') is False else ''}{fmt(ch.get('daily_limit'))} {ch['currency']} · {ch['quota_summary']} · 核验 {ch.get('checked_at')}")
    lines.append('额度表示具体渠道公开状态；不等于剩余额度。巨大平台哨兵不作为真实金额。')
    lines.extend(f"数据状态：{i['item']} {i['message']}" for i in snapshot['issues'])
    text='\n'.join(lines)
    body=''.join(f'<p>{esc(line)}</p>' for line in lines)
    url=CONFIG.get('public_url','')
    if url.startswith('https://'):
        body+=f'<p><a href="{esc(url,quote=True)}">查看监控网站</a></p>'
    markup=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>纳斯达克与QDII早报</title><style>body{{max-width:850px;margin:32px auto;padding:0 20px;font:16px/1.7 system-ui;color:#132d42}}p{{border-bottom:1px solid #e8edf2;padding:10px 0}}p:first-child{{font-size:26px;font-weight:700}}</style></head><body>{body}</body></html>'
    return text,markup

def freeze_report(report_date=None):
    snapshot=latest()
    if not snapshot:
        raise RuntimeError('请先采集数据')
    day=report_date or market_context()['beijing_date']
    reports=DATA/'reports';reports.mkdir(exist_ok=True)
    with connect() as con:
        existing=con.execute('SELECT * FROM reports WHERE report_date=?',(day,)).fetchone()
        if existing:
            snapshot=get_snapshot(existing['snapshot_id'])
            if not snapshot:
                raise RuntimeError('冻结快照丢失')
        else:
            snapshot=for_display(snapshot)
            con.execute('INSERT INTO reports(report_date,snapshot_id,created_at,status) VALUES(?,?,?,?)',(day,snapshot['id'],now_iso(),'preview'))
            # Save read-time statuses once. Later website refreshes cannot alter this report.
            (reports/f'{day}.json').write_text(json.dumps(snapshot,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    frozen=reports/f'{day}.json'
    if frozen.exists():
        snapshot=json.loads(frozen.read_text(encoding='utf-8'))
    text,markup=render(snapshot)
    (reports/f'{day}.txt').write_text(text,encoding='utf-8')
    (reports/f'{day}.html').write_text(markup,encoding='utf-8')
    return day,snapshot,text,markup

def send_report():
    url=CONFIG.get('worker_url')
    token=os.environ.get(CONFIG['worker_token_env'])
    if not url or not token:
        raise RuntimeError('邮件入口和本机令牌尚未配置；仅生成本机预览')
    if not url.startswith('https://'):
        raise RuntimeError('邮件入口必须使用HTTPS')
    day,snapshot,text,markup=freeze_report()
    with connect() as con:
        row=con.execute('SELECT status FROM reports WHERE report_date=?',(day,)).fetchone()
        if row['status'] in ('sent','sending','uncertain'):
            return 'skipped: '+row['status']
        con.execute("UPDATE reports SET status='sending' WHERE report_date=?",(day,))
    try:
        key=hashlib.sha256(('nasdaq-briefing:'+day).encode()).hexdigest()
        response=requests.post(url,headers={'Authorization':f'Bearer {token}','Idempotency-Key':key},
            json={'report_id':key,'date':day,'subject':f'纳斯达克与QDII早报 · {day}','text':text,'html':markup},timeout=(8,30))
        response.raise_for_status()
        if response.json().get('status') not in ('sent','already_sent'):
            raise ValueError('邮件端未确认发送状态')
    except Exception as exc:
        with connect() as con:
            con.execute("UPDATE reports SET status='uncertain',error=? WHERE report_date=?",(type(exc).__name__+': 请核验远端结果后人工处理',day))
        raise RuntimeError('发送结果待核验；已阻止自动重复发送') from None
    with connect() as con:
        con.execute("UPDATE reports SET status='sent',sent_at=? WHERE report_date=?",(now_iso(),day))
    return 'sent'
