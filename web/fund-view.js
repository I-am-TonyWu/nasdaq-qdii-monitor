'use strict';
function shareCount(){return data.funds.reduce((n,f)=>n+f.shares.length,0);}
function scopeNote(channel){
  if(channel.quota_scope!=='shared')return '';
  const map=new Map(data.funds.flatMap(f=>f.shares.map(s=>[s.code,s.share_class])));
  const classes=[...new Set((channel.scope_codes||[]).map(code=>map.get(code)).filter(Boolean))].sort();
  return `（${classes.join('/')||'份额'}总额度）`;
}
function quotaColumn(shares,kind){
  const entries=shares.flatMap(s=>s.channels.filter(c=>(c.channel_kind||(c.channel==='天天基金'?'distributor':'direct'))===kind).map(c=>({share:s,channel:c})));
  const available=entries.filter(e=>e.channel.purchasable);
  const confirmedShares=new Set(available.map(e=>e.share.code));
  const usable=[...available,...entries.filter(e=>!confirmedShares.has(e.share.code)&&e.channel.announcement_verified&&e.channel.announcement_limit!=null&&!['suspended','not_offered'].includes(e.channel.status))];
  if(!usable.length)return `<span class="quota-empty">${entries.length&&entries.every(e=>e.channel.status==='suspended')?'暂停':entries.length&&entries.every(e=>e.channel.status==='not_offered')?'未开放':'—'}</span>`;
  const groups=new Map();
  for(const e of usable){
    const c=e.channel,actual=Boolean(c.purchasable),value=actual?c.daily_limit:c.announcement_limit;
    const inclusive=actual?c.limit_inclusive:c.announcement_limit_inclusive;
    const manual=c.verification_basis==='user_confirmation';
    const key=[value,inclusive,scopeNote(c),manual,actual].join('|');
    if(!groups.has(key))groups.set(key,{value,inclusive,note:scopeNote(c),manual,actual,classes:new Set(),channels:new Set(),conflict:false});
    const g=groups.get(key);g.classes.add(e.share.share_class);g.channels.add(c.channel);g.conflict||=c.status==='minimum_conflict';
  }
  return [...groups.values()].sort((a,b)=>b.value-a.value).map(g=>{
    const classLabel=shares.length>1&&!g.note&&g.classes.size<shares.length?`（${[...g.classes].sort().join('/')}）`:'';
    const note=g.note||classLabel;
    return `<div class="quota-value" title="${esc(g.note?'每账户单日跨份额合并额度，非基金整体规模上限':g.actual?'具体渠道当前可买上限':'公告限额；实际受理状态未完成核验')}"><div class="quota-reading"><span class="quota-number">${g.inclusive===false?'＜':''}${num(g.value,0)}</span>${note?`<span class="quota-note">${esc(note)}</span>`:''}</div>${g.manual?'<small class="quota-evidence manual-tag">用户确认</small>':!g.actual?`<small class="quota-evidence">${g.conflict?'起购超限':'公告'}</small>`:''}</div>`;
  }).join('');
}
function percentRange(values){
  const good=values.filter(v=>v!=null&&Number.isFinite(v));
  if(!good.length)return '—';
  const lo=Math.min(...good),hi=Math.max(...good);
  return Math.abs(hi-lo)<.005?num(lo)+'%':num(lo)+'–'+num(hi)+'%';
}
function feeColumn(shares){
  const purchase=shares.flatMap(s=>s.channels.filter(c=>c.channel==='天天基金'&&c.method==='普通申购').map(c=>c.fee_percent));
  const annual=shares.map(s=>{const parts=['管理费率','托管费率','销售服务费率'].map(k=>{const m=String(s.fees?.[k]??'').match(/([\d.]+)\s*%/);return m?Number(m[1]):null;});return parts.every(v=>v!=null)?parts.reduce((a,b)=>a+b,0):null;});
  return `<span>${percentRange(purchase)}</span><small>年费 ${percentRange(annual)}</small>`;
}
function performanceColumns(shares){
  return `<div class="fund-cell numeric performance-cell" data-label="近一年收益">${percentRange(shares.map(s=>s.one_year_return))}</div><div class="fund-cell fee-cell performance-cell" data-label="费率">${feeColumn(shares)}</div><div class="fund-cell numeric performance-cell" data-label="跟踪误差">${percentRange(shares.map(s=>s.tracking_error))}</div>`;
}
function detailColumns(shares){
  return `<div class="fund-cell quota-cell" data-label="代销额度">${quotaColumn(shares,'distributor')}</div><div class="fund-cell quota-cell" data-label="直销额度">${quotaColumn(shares,'direct')}</div>${performanceColumns(shares)}`;
}
function fundPerformance(shares){
  return `<details class="fund-performance method-details"><summary>收益、费率与跟踪误差<span class="performance-chevron" aria-hidden="true">›</span></summary><div class="fund-performance-grid">${performanceColumns(shares)}</div></details>`;
}
function renderFundPreview(){
  const open=data.funds.filter(f=>f.verified_channels>0);
  $('fund-overview-note').textContent=`${open.length}只 · 人民币元`;
  $('fund-preview').innerHTML=open.length?`<div class="fund-preview-head"><span>基金</span><span>代销额度</span><span>直销额度</span></div>`+open.map(f=>`<a class="fund-preview-row" href="#funds"><div class="fund-preview-identity"><strong title="${esc(f.name)}">${esc(shortName(f.name))}</strong><small>${f.verified_shares}个可买份额${f.availability_basis==='user_confirmation'?' · 含用户确认渠道':''}</small></div><div class="fund-preview-quota" data-label="代销额度">${quotaColumn(f.shares,'distributor')}</div><div class="fund-preview-quota" data-label="直销额度">${quotaColumn(f.shares,'direct')}</div></a>`).join(''):'<div class="empty">暂无可购买基金</div>';
}
function channelHtml(c){
  const cap=c.purchasable?c.daily_limit:null;
  return `<div class="channel-card"><div class="channel-heading"><strong>${esc(c.channel)} · ${esc(c.method)}</strong>${c.verification_basis==='user_confirmation'?'<span class="badge manual">用户确认</span>':badge(c.status)}</div><div class="channel-data"><div>可买日上限<b>${cap==null?'—':(c.limit_inclusive===false?'＜':'')+num(cap,0)+'元'+esc(scopeNote(c))}</b></div><div>公告上限<b>${c.announcement_limit==null?'—':(c.announcement_limit_inclusive===false?'＜':'')+num(c.announcement_limit,0)+'元'+esc(scopeNote(c))}</b></div><div>起购<b>${num(c.minimum,0)}元</b></div></div><details class="channel-meta method-details"><summary>适用条件与核验记录</summary>${c.reason?`<p>${esc(c.reason)}</p>`:''}<p>${esc(c.conditions)}</p><p>${esc((c.combined_methods||[]).join('、'))}合并累计 · 生效 ${esc(c.effective_date||'待核验')}</p><p>${c.scope_basis==='user_default'?'跨份额规则采用用户指定默认：分别计算。':''}${c.verification_basis==='user_confirmation'?esc(c.confirmation_source):''}</p><p>核验 ${localDate(c.checked_at)} · ${link(c.status_evidence||c.evidence,c.verification_basis==='user_confirmation'?'管理人官网':'渠道页面')}${c.entry_url?' · '+link(c.entry_url,c.channel_kind==='direct'&&!c.purchasable?'管理人网站':'购买入口'):''}${(c.notice_evidence||[]).map((u,i)=>' · '+link(u,'公告'+(i+1))).join('')}</p><p>有效期至 ${localDate(c.valid_until)}</p></details></div>`;
}
function shareHtml(s){
  return `<details class="share-row"><summary class="share-summary fund-columns"><div class="share-identity"><button class="star ${favoriteCodes.has(s.code)?'saved':''}" type="button" data-star="${esc(s.code)}" aria-label="${favoriteCodes.has(s.code)?'取消自选':'加入自选'} ${esc(s.code)}" aria-pressed="${favoriteCodes.has(s.code)}">★</button><div><span class="share-code">${esc(s.code)} · ${esc(s.share_class)}</span><strong>${esc(s.name)}</strong></div></div>${detailColumns([s])}</summary><div class="share-mobile-performance"><div class="fund-performance-grid">${performanceColumns([s])}</div></div><details class="method-details share-channel-details"><summary>渠道与额度依据</summary>${s.channels.map(channelHtml).join('')}</details><details class="method-details share-information"><summary>基金资料与费用</summary><p>净值 ${num(s.nav,4)} · ${esc(s.nav_date||'未取得')}</p><p>近一年收益截至 ${esc(s.return_date||'未取得')} · ${esc(s.return_method||s.return_reason)}</p><p>管理 / 托管 / 销售服务费：${esc(s.fees?.['管理费率']||'—')} / ${esc(s.fees?.['托管费率']||'—')} / ${esc(s.fees?.['销售服务费率']||'—')}</p><p>实际跟踪误差：${esc(s.tracking_reason||'未取得')}${s.tracking_source?' · '+link(s.tracking_source,'报告'):''}</p><p>比较基准：${esc(s.benchmark||'待核验')} · ${link(s.profile_source,'基本资料')}</p></details></details>`;
}
function renderFunds(){
  $('fund-stats').innerHTML=[['基金',data.funds.length],['份额',shareCount()],['可买份额',data.funds.reduce((n,f)=>n+f.verified_shares,0)],['我的自选',favoriteCodes.size]].map(([s,n])=>`<div>${s}<b>${n}</b></div>`).join('');
  const q=$('fund-search').value.trim().toLowerCase(),index=$('fund-index').value,state=$('fund-state').value,only=$('favorites-only').checked;
  shownFunds=data.funds.filter(f=>{
    if(index!=='all'&&f.target!==index)return false;
    if(only&&!f.shares.some(s=>favoriteCodes.has(s.code)))return false;
    if(state==='open'&&!f.verified_channels)return false;
    if(state==='suspended'&&!f.shares.some(s=>s.channels.some(c=>c.status==='suspended')))return false;
    if(state==='unknown'&&!f.shares.some(s=>s.channels.some(c=>['unknown','expired'].includes(c.status))))return false;
    return !q||[f.name,f.company,f.target,...f.shares.flatMap(s=>[s.code,s.name])].join(' ').toLowerCase().includes(q);
  });
  $('fund-list').innerHTML=shownFunds.map(f=>`<details class="fund-row" ${q?'open':''}><summary class="fund-summary fund-columns"><div class="fund-title"><span class="chevron">›</span><span class="fund-name" title="${esc(f.name)}">${esc(shortName(f.name))}<small>${esc(f.target==='NDX100'?'NDX':f.target)} · ${f.verified_shares}/${f.shares.length}个可买份额<span class="fund-detail-hint"> · 展开详情</span></small></span></div>${detailColumns(f.shares)}</summary>${fundPerformance(f.shares)}${f.shares.map(shareHtml).join('')}</details>`).join('');
  $('fund-empty').hidden=shownFunds.length>0;
}
