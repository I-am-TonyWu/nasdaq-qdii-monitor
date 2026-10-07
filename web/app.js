'use strict';
const $=(id)=>document.getElementById(id);
const esc=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const signed=(v,d=2)=>v==null?'—':(v>0?'+':'')+num(v,d);
const labels={available:'有数据',reference:'参考序列',fresh:'有效',stale:'过期',missing:'未取得',open:'开放',limited:'限额开放',suspended:'暂停',unknown:'待核验',expired:'已过期',not_offered:'该渠道未开放',minimum_conflict:'起购超限'};
const badge=(s)=>`<span class="badge ${esc(s)}">${esc(labels[s]||s)}</span>`;
const localDate=(s)=>{if(!s)return '未核验';const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(s));const v=Object.fromEntries(parts.map(p=>[p.type,p.value]));return `${v.year}-${v.month}-${v.day} ${v.hour}:${v.minute}:${v.second}`;};
const safeUrl=(url)=>{try{const u=new URL(url?.startsWith('//')?'https:'+url:url);return ['http:','https:'].includes(u.protocol)?u.href:'#';}catch{return '#';}};
const link=(url,label)=>`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
const instrumentLabel=key=>key==='NDX'?'纳斯达克100（NDX）':key;
const pairNames={VTV:'VTV',CGDV:'CGDV',KO:'可口可乐',BRKA:'伯克希尔 A',RUT:'罗素2000'};
const pairColors={VTV:'--teal',CGDV:'--blue',KO:'--amber',BRKA:'--violet',RUT:'--red'};
const unitLabel=unit=>({points:'点',USD:'美元','USD/oz':'美元/盎司','0-100':'0–100'}[unit]||unit||'');
const colorCache=new Map();
function cssColor(token){
  if(colorCache.has(token))return colorCache.get(token);
  const el=document.createElement('span');el.style.color=`var(${token})`;document.body.append(el);const color=getComputedStyle(el).color;el.remove();
  const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const context=canvas.getContext('2d');context.fillStyle=color;context.fillRect(0,0,1,1);
  const rgb=context.getImageData(0,0,1,1).data,normalized=`rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;colorCache.set(token,normalized);return normalized;
}
function alphaColor(color,alpha){const rgb=color.match(/[\d.]+/g);return rgb?.length>=3?`rgba(${rgb.slice(0,3).join(',')},${alpha})`:color;}
Chart.defaults.font.family=getComputedStyle(document.documentElement).getPropertyValue('--sans');
Chart.defaults.color=cssColor('--muted');
let data=null,range=3,pairRange=3,macroRange=12,charts={},shownFunds=[],loading=false;
const views={overview:['每日概览','市场、估值与可申购渠道，一处查看。'],valuation:['估值与情绪','指标走势与历史分位，共享观察区间。'],style:['风格与技术','观察趋势与相对表现，保留算法和数据日期。'],macro:['黄金 · 利率','观察黄金与收益率变化，不并入主评分。'],funds:['基金与渠道','基金主行展开份额，再查看具体渠道及适用条件。'],history:['历史记录','从第一天保存当时可见的数据，为后续研究留证据。']};
let favoriteCodes=new Set();
try{const stored=localStorage.getItem('nasdaq-favorites-v1');favoriteCodes=new Set(stored?JSON.parse(stored):[]);if(!stored)favoriteCodes=null;}catch{favoriteCodes=null;}
function storeFavorites(){try{localStorage.setItem('nasdaq-favorites-v1',JSON.stringify([...favoriteCodes]));}catch{}}

function calendarTicks(axis){
  const count=Math.min(window.innerWidth<600?4:7,axis.ticks.length);
  if(count<2)return;
  const original=axis.ticks;
  axis.ticks=[...new Set(Array.from({length:count},(_,i)=>Math.round(i*(original.length-1)/(count-1))))].map(i=>original[i]);
}

function lineChart(id,rows,{color=cssColor('--teal'),label='',percent=false,spark=false}={}){
  if($(id)?.closest('.view')?.hidden)return;
  if(charts[id])charts[id].destroy();
  const canvas=$(id);if(!canvas||typeof Chart==='undefined')return;
  const context=canvas.getContext('2d');
  const gradient=context.createLinearGradient(0,0,0,300);gradient.addColorStop(0,alphaColor(color,.12));gradient.addColorStop(1,alphaColor(color,0));
  const long=rows.length>260;
  charts[id]=new Chart(canvas,{type:'line',data:{labels:rows.map(r=>r.date),datasets:[{label,data:rows.map(r=>r.value),borderColor:color,backgroundColor:gradient,borderWidth:spark?1.7:2,pointRadius:rows.length<2&&!spark?4:0,pointHoverRadius:spark?0:4,fill:true,tension:.12}]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{display:false},tooltip:{enabled:!spark,callbacks:{label:c=>`${label} ${num(c.parsed.y)}${percent?'%':''}`}}},scales:spark?{x:{display:false},y:{display:false}}:{x:{grid:{display:false},afterBuildTicks:calendarTicks,ticks:{autoSkip:false,maxRotation:0,color:cssColor('--muted'),font:{size:12},callback:function(value){const date=this.getLabelForValue(value);return long?date.slice(0,7):date.slice(5);}}},y:{position:'right',min:percent?0:undefined,max:percent?100:undefined,grid:{color:alphaColor(cssColor('--line'),.7)},border:{display:false},ticks:{maxTicksLimit:6,color:cssColor('--muted'),font:{size:12},callback:v=>num(v,percent?1:0)+(percent?'%':'')}}}}});
}

function rangeStart(end,months){
  const d=new Date(end+'T12:00:00Z'),day=d.getUTCDate();
  d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-months);
  const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();
  d.setUTCDate(Math.min(day,last));return d.toISOString().slice(0,10);
}
function inRange(rows,months,end=rows.at(-1)?.date){return end?rows.filter(r=>r.date>=rangeStart(end,months)&&r.date<=end):[];}
function spanText(rows,months){
  if(!rows.length)return '无历史数据';
  const cutoff=new Date(rangeStart(rows.at(-1).date,months)+'T12:00:00Z');cutoff.setUTCDate(cutoff.getUTCDate()+10);
  return `${rows[0].date} — ${rows.at(-1).date}${rows[0].date>cutoff.toISOString().slice(0,10)?' · 历史不足所选周期':''}`;
}

function metric(key,spark=false){
  const item=data.series[key]||{};
  const change=item.changes?.['1'];const isYield=['DGS2','DGS10','DFII10'].includes(key);
  return `<article class="metric-card"><div class="metric-head"><div>${esc(item.name||key)}<div class="metric-symbol">${esc(key==='NDX'?'NDX':item.symbol||key)}</div></div>${item.status==='fresh'?'':badge(item.status||'missing')}</div><div class="metric-value">${num(item.value)}<span class="metric-unit">${esc(unitLabel(item.unit))}</span></div><div class="metric-change ${change>0?'positive':change<0?'negative':''}">${signed(change)}${isYield?' bp':'%'}</div>${spark?`<div class="spark-wrap"><canvas id="spark-${key}" role="img" aria-label="${esc(item.name)}近期走势"></canvas></div>`:''}<div class="meta"><span>${esc(item.date||'无观察日')}</span></div></article>`;
}

function renderOverview(){
  $('index-cards').innerHTML=['NDX','NDXTMC','QQQ'].map(k=>metric(k,true)).join('');
  $('sentiment-cards').innerHTML=['VXN','VIX','FGI'].map(k=>metric(k)).join('');
  ['NDX','NDXTMC','QQQ'].forEach(k=>lineChart('spark-'+k,(data.series[k]?.history||[]).slice(-25),{spark:true}));
  const score=data.score;
  $('score-display').innerHTML=`${num(score.value,1)}<span>/ 100</span>`;
  $('score-caption').textContent=score.value==null?'不可计算 · '+score.reasons.map(r=>r.split('：')[0]).join('、')+'待补齐':({caution:'谨慎区间',normal:'正常区间',fear:'恐慌区间'}[score.band]||'组合观察')+(score.components[0]?.percentile_origin==='publisher_reported'?' · PE采用源站5年分位':'');
  document.querySelectorAll('[data-score-band]').forEach(el=>el.classList.toggle('current-band',el.dataset.scoreBand===score.band));
  const marker=$('score-position');marker.hidden=score.value==null;
  if(score.value!=null)marker.style.left=Math.max(0,Math.min(100,score.value))+'%';
  $('score-scale').setAttribute('aria-label',score.value==null?'评分不可计算；谨慎小于30，正常30至小于70，恐慌70及以上':`当前${num(score.value,1)}分；谨慎小于30，正常30至小于70，恐慌70及以上`);
  $('score-components').innerHTML=score.components.map(c=>{
    const input=c.key==='fgi'?`当前指数 ${num(c.raw_value,1)}`:`${esc(c.percentile_window||'历史')}分位 ${num(c.percentile,1)}%`;
    return `<div class="score-line" data-score-key="${esc(c.key)}" title="${esc((c.source||'')+' · '+(c.percentile_origin==='publisher_reported'?'源站公布分位':'本站计算'))}"><div class="score-row"><span class="score-label">${esc(c.name)}</span><span class="score-standard">${c.points==null?'待更新':'标准化值 '+num(c.points,1)}</span></div><div class="score-input">${input} · 权重 ${num(c.weight*100,0)}%</div><div class="score-progress"><span style="width:${c.points??0}%"></span></div></div>`;
  }).join('');
  renderFundPreview();
  drawPrice();
}
function shortName(name){return name.replace('交易型开放式指数证券投资基金发起式联接基金','ETF联接').replace('交易型开放式指数证券投资基金联接基金','ETF联接').replace('交易型开放式指数证券投资基金','ETF').replace('证券投资基金','');}
function limitText(f){if(f.max_limits?.length)return f.max_limits.map(l=>`${l.inclusive===false?'＜':''}${num(l.value,0)} ${esc(l.currency)}`).join('<br>');return f.has_sentinel?'上限未知':'—';}
function drawPrice(){
  if(!data)return;
  const key=$('price-instrument').value,item=data.series[key]||{},t=data.technicals?.[key]||(key==='NDX'?data.technical:{}),rows=inRange(item.history||[],range);
  lineChart('price-chart',rows,{label:instrumentLabel(key)});
  $('price-chart').setAttribute('aria-label',instrumentLabel(key)+'收盘走势');
  $('price-empty').hidden=rows.length>0;$('price-chart-caption').textContent=spanText(rows,range)+' · '+unitLabel(item.unit);
  $('technical-inline').dataset.instrument=key;
  $('technical-inline').innerHTML=[['RSI(6)',t.rsi?.['6'],'','Wilder 日线RSI'],['距200日均线',t.ma200_distance,'%','最新收盘 / 200日均价 − 1'],['距52周盘中高点',t.drawdown_52w,'%',t.drawdown_reason||`高点 ${num(t.high_52w)} · ${t.high_52w_date} · ${t.high_52w_source}`]].map(([label,v,unit,title])=>`<div title="${esc(title)}"><span>${esc(label)}</span><b>${num(v)}${v==null?'':unit}</b></div>`).join('');
  $('price-technical-date').textContent=`${key} · ${t.date||'指标未取得'}${t.source_status==='fresh'?'':' · 缓存待更新'}`;
}

function renderStyle(){
  const t=data.technical;
  $('technical-cards').innerHTML=[6,14,24].map(p=>`<article class="metric-card"><div class="metric-head">NDX RSI(${p})${t.source_status==='fresh'?'':badge(t.source_status||'missing')}</div><div class="metric-value">${num(t.rsi?.[String(p)])}</div><p class="meta">${esc(t.date||'未取得')}</p></article>`).join('');
  $('style-technical-date').textContent='NDX · '+(t.date||'未取得')+(t.source_status==='fresh'?'':' · 待更新');
  $('pair-values').innerHTML=Object.entries(data.pairs).map(([key,p])=>`<div data-pair="${esc(key)}"><div class="submetric"><span class="pair-series-label"><i class="series-dot" style="--series-color:${cssColor(pairColors[key])}" aria-hidden="true"></i>${esc(pairNames[key]||key)} / QQQ</span><b class="${p.roc['35']>0?'positive':'negative'}">${signed(p.roc['35'])}%</b></div><div class="meta">${esc(p.date||'未取得')}${p.source_status==='fresh'?'':' · 待更新'}</div></div>`).join('');
  drawPairs();
}
function drawPairs(){
  if(!data||$('style').hidden)return;
  if(typeof Chart==='undefined')return;const existing=charts['pair-chart']||Chart.getChart($('pair-chart'));if(existing)existing.destroy();
  const keys=['VTV','CGDV','KO','BRKA','RUT'],colors=keys.map(k=>cssColor(pairColors[k]));
  const allDates=[...new Set(keys.flatMap(k=>(data.pairs[k]?.history||[]).map(r=>r.date)))].sort(),end=allDates.at(-1);
  const dates=end?allDates.filter(d=>d>=rangeStart(end,pairRange)):[];
  $('pair-caption').textContent=spanText(dates.map(date=>({date})),pairRange)+(pairRange===60?' · CGDV 自成立后首个有效ROC起显示':'');
  charts['pair-chart']=new Chart($('pair-chart'),{type:'line',data:{labels:dates,datasets:keys.map((k,i)=>{const m=new Map((data.pairs[k]?.history||[]).map(r=>[r.date,r.value]));return{label:pairNames[k]+'/QQQ',data:dates.map(d=>m.get(d)??null),borderColor:colors[i],borderWidth:2,pointRadius:0,tension:.12};})},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{position:'bottom',labels:{usePointStyle:true,font:{size:12},padding:20}},tooltip:{callbacks:{label:c=>`${c.dataset.label} ${signed(c.parsed.y)}%`}}},scales:{x:{grid:{display:false},afterBuildTicks:calendarTicks,ticks:{autoSkip:false,maxRotation:0,font:{size:12},callback:function(v){const d=this.getLabelForValue(v);return pairRange>=12?d.slice(0,7):d.slice(5);}}},y:{position:'right',suggestedMin:-1,suggestedMax:1,afterBuildTicks:axis=>{if(!axis.ticks.some(t=>t.value===0)){axis.ticks.push({value:0});axis.ticks.sort((a,b)=>a.value-b.value);}},grid:{color:c=>c.tick?.value===0?cssColor('--slate-9'):alphaColor(cssColor('--line'),.7),lineWidth:c=>c.tick?.value===0?1.5:.75},border:{display:false},ticks:{maxTicksLimit:6,autoSkip:false,color:c=>c.tick?.value===0?cssColor('--ink'):cssColor('--muted'),callback:v=>num(v,1)+'%',font:c=>({size:11,weight:c.tick?.value===0?'bold':'normal'})}}}}});
}
function renderMacro(){ $('macro-cards').innerHTML=['GOLD','DGS2','DGS10','DFII10'].map(k=>metric(k)).join('');drawMacro(); }
function drawMacro(){
  if(!data)return;
  const key=$('macro-instrument').value,item=data.series[key]||{},rows=inRange(item.history||[],macroRange);
  lineChart('macro-chart',rows,{label:item.name,color:cssColor('--blue')});
  $('macro-chart-caption').textContent=spanText(rows,macroRange)+' · '+unitLabel(item.unit);
  $('macro-caption').textContent=key==='GOLD'?'连续近月黄金期货，作为现货观察代理；移仓影响变化。':'美国财政部日频收益率；变化以基点表示。';
  $('macro-correlation').textContent=`与QQQ日收益相关：60个共同样本 ${num(item.qqq_correlation?.['60'])} / 120个共同样本 ${num(item.qqq_correlation?.['120'])}。${['DGS2','DGS10','DFII10'].includes(key)?'收益率采用日水平变化。':''}1 / 5 / 20次观测变化：${[1,5,20].map(n=>signed(item.changes?.[String(n)])).join(' / ')} ${['DGS2','DGS10','DFII10'].includes(key)?'bp':'%'}。`;
}

async function renderHistory(){
  if(!$('history-list').children.length)$('history-list').innerHTML='<p class="meta" role="status">正在读取历史快照…</p>';
  const quality={verified_transmission:'同日官方核对通过',official_aux_missing:'官方有效 · 辅源新日未齐',official_single_source:'官方单源',distributor_only:'分发器数据',pending_official:'待官方核对',conflict:'信源冲突'};
  const frequencies={daily:'日频',weekly:'周频',monthly:'月频',quarterly:'季频'};
  const sourceName=s=>({'Nasdaq / FRED':'纳斯达克 / FRED','Nasdaq via FRED':'纳斯达克经FRED','US Treasury / FRED':'美国财政部 / FRED','US Treasury':'美国财政部','Federal Reserve via FRED':'美联储经FRED','Eastmoney':'东方财富'}[s]||s||'未取得');
  const description=key=>['NDX','NDXTMC','RUT'].includes(key)?'价格指数收盘':['QQQ','VTV','CGDV','KO','BRKA'].includes(key)?'收盘价格':['VXN','VIX'].includes(key)?'波动率收盘':key==='FGI'?'恐惧与贪婪指数':key==='GOLD'?'连续近月黄金期货':'美国国债收益率';
  function row(name,key,item,summary,statusNote=''){
    const records=(item.checks||[]).map(c=>`<p>${esc((c.providers||[]).join(' / '))} · ${esc({passed:'通过',missing:'未齐',conflict:'冲突'}[c.result]||c.result)} · ${esc(c.samples??'')}个同日样本 · 截至 ${esc(c.through||'—')}</p>`).join('');
    return `<div class="source-row" role="row"><span role="cell">${esc(name)}${name===key?'':`<small class="meta">${esc(key)}</small>`}</span><span role="cell">${link(item.source_url,sourceName(item.source))}<small class="meta">${esc(summary)}</small><details class="method-details"><summary>来源与核对记录</summary><p>${esc(item.method||item.method_id||'原始数据说明未取得')}</p>${records}${records?'<p>同一发布机构的传播核对。</p>':''}${item.reason?`<p>${esc(item.reason)}</p>`:''}</details></span><span class="source-date" role="cell">${esc(item.date||'未取得')}</span><span class="source-status" role="cell">${badge(item.status||'missing')}${statusNote?`<small class="meta">${esc(statusNote)}</small>`:''}</span></div>`;
  }
  const section=name=>`<div class="source-section-row" role="row"><span role="cell" aria-colspan="4">${esc(name)}</span></div>`;
  let rows=section('行情与情绪')+Object.entries(data.series).map(([k,i])=>row(i.name||k,k,i,(frequencies[i.frequency]||'日频')+' · '+description(k),quality[i.verification_status]||'未完成核对')).join('');
  rows+=section('估值发布快照 · WSJ / Birinyi');
  rows+=Object.entries(data.valuation).map(([k,v])=>row(k==='forward'?'WSJ前瞻PE':'WSJ TTM PE',k==='forward'?'Forward PE':'PE TTM',v,`${frequencies[v.frequency]||'周频'} · ${v.samples||0}个真实样本`,'独立发布口径')).join('');
  rows+=section('估值历史参考 · 不计入评分')+Object.entries(data.valuation_references||{}).map(([k,v])=>row(k==='ttm'?'TTM历史参考':'PB历史参考',k.toUpperCase(),{...v,status:'reference'},`周频 · ${(v.history||[]).length}个真实样本`,'独立参考，不计入评分')).join('');
  rows+=section('综合评分的前瞻PE来源')+Object.entries(data.valuation_publisher||{}).map(([k,v])=>row('前瞻PE评分来源','Forward PE',v,`5年分位 ${num(v.percentile,0)}% · 源站公布`,'当前评分所选来源')).join('');
  $('source-list').innerHTML=`<div class="source-table" role="table" aria-label="当前数据状态"><div class="source-table-head" role="row">${['数据名称','来源与口径','观察日期','状态'].map(s=>`<span role="columnheader">${s}</span>`).join('')}</div>${rows}</div>`;
  const active=data.update_issues||data.issues.filter(i=>i.kind!=='history'),history=data.history_limitations||data.issues.filter(i=>i.kind==='history');
  $('history-quality-summary').textContent=`${active.length}项待更新 · ${history.length}项历史缺口`;
  const issue=i=>`<div class="issue"><span class="badge ${i.kind==='history'?'stale':'unknown'}">${i.kind==='history'?'历史缺口':i.kind==='verification'?'待核对':'待更新'}</span>${esc(({forward:'WSJ Forward PE',ttm:'WSJ TTM PE'})[i.item]||i.item)} · ${esc(i.message)}</div>`;
  $('issues-list').innerHTML=(active.length?active.map(issue).join(''):'<p class="meta">当前行情与评分数据已更新。</p>')+(history.length?`<details class="method-details"><summary>${history.length}项历史缺口</summary>${history.map(issue).join('')}</details>`:'');
  try{const r=await fetch('/api/history');if(!r.ok)throw Error();const records=await r.json();$('history-list').innerHTML=records.map(r=>`<div class="history-row"><div>${localDate(r.created_at)}<br><span class="snapshot-code">${esc(r.id)}</span></div><span>美国 ${esc(r.session)}</span><span>观察分 ${num(r.score,1)}</span><a class="text-link" href="/api/history/${r.id}" target="_blank" rel="noopener">查看快照</a></div>`).join('')||'<div class="empty">暂无历史快照</div>';}catch{$('history-list').textContent='历史记录读取失败，可稍后刷新。';}
}

function selectView(){
  const requested=location.hash.slice(1),view=views[requested]?requested:'overview';
  document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==view);
  document.querySelectorAll('nav a').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  if(innerWidth<=850){const active=document.querySelector('nav a.active'),nav=active.parentElement;nav.scrollLeft+=active.getBoundingClientRect().left-nav.getBoundingClientRect().left-(nav.clientWidth-active.offsetWidth)/2;}
  $('page-title').textContent=views[view][0];$('crumb').textContent=views[view][0];$('page-subtitle').textContent=views[view][1];
  requestAnimationFrame(updateNavHint);
  if(data)requestAnimationFrame(()=>{if(view==='history')renderHistory();if(view==='valuation')drawValuation();if(view==='style')drawPairs();if(view==='macro')drawMacro();if(view==='overview'){drawPrice();['NDX','NDXTMC','QQQ'].forEach(k=>lineChart('spark-'+k,(data.series[k]?.history||[]).slice(-25),{spark:true}));}Object.values(charts).forEach(chart=>{if(!chart.canvas.closest('.view')?.hidden)chart.resize();});});
}
async function load(){
  if(loading)return;
  loading=true;
  $('reload').disabled=true;
  try{
    const response=await fetch('/api/snapshot');if(!response.ok)throw new Error(response.status===503?'尚无采集快照，请在本机运行采集。':'快照读取失败。');data=await response.json();
    if(favoriteCodes===null)favoriteCodes=new Set(data.funds.flatMap(f=>f.shares.map(s=>s.code)));
    $('error').hidden=true;
    const market=data.current_market||data.market;
    $('header-date').textContent=market.beijing_date+' · 北京时间';
    const quality=data.quality_counts||{updates:data.issues.length,history:0};
    $('statusbar').innerHTML=`<span class="status-summary"><span>交易日 <strong>${esc(market.expected_us_session)}</strong></span><span>行情 <strong>${data.fresh_count}/${data.source_count}</strong></span></span><span class="status-meta"><time datetime="${esc(data.generated_at)}" title="北京时间">快照 ${localDate(data.generated_at)}</time><a href="#history" data-quality="updates" class="quality-tag ${quality.updates?'alert':''}">${quality.updates}项待更新</a><a href="#history" data-quality="history" class="quality-tag ${quality.history?'attention':''}">${quality.history}项历史缺口</a></span>`;
    $('snapshot-id').textContent='快照 '+data.id;
    renderOverview();renderValuation();renderStyle();renderMacro();renderFunds();selectView();
  }catch(e){$('error').textContent=e.message;$('error').hidden=false;$('statusbar').textContent='本机数据未就绪';}finally{loading=false;$('reload').disabled=false;}
}
function exportCsv(){
  const rows=[['基金','代码','份额','币种','跟踪指数','渠道','申购方式','状态','渠道日上限','公告上限','渠道含上限','公告含上限','份额规则','合并交易','核验时间','渠道证据','公告证据','渠道类型','核验依据','跨份额规则依据','近一年收益(%)','收益日期','申购费率(%)','实际跟踪误差(%)']];
  shownFunds.forEach(f=>f.shares.forEach(s=>s.channels.forEach(c=>rows.push([f.name,s.code,s.share_class,s.currency,f.target,c.channel,c.method,labels[c.status]||c.status,c.daily_limit??'',c.announcement_limit??'',c.limit_inclusive===false?'不含':'含',c.announcement_limit_inclusive===false?'不含':'含',c.quota_summary,(c.combined_methods||[]).join('/'),c.checked_at??'',c.status_evidence||c.evidence,(c.notice_evidence||[]).join(' '),c.channel_kind,c.verification_basis||'public_evidence',c.scope_basis||'announcement',s.one_year_return??'',s.return_date??'',c.fee_percent??'',s.tracking_error??'']))));
  const field=(v)=>'"'+(/^[=+\-@]/.test(String(v))?"'":'')+String(v).replace(/"/g,'""')+'"';
  const blob=new Blob(['\uFEFF'+rows.map(r=>r.map(field).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='QDII渠道-'+data.market.beijing_date+'.csv';a.click();URL.revokeObjectURL(url);
}
$('reload').addEventListener('click',load);
$('price-instrument').addEventListener('change',drawPrice);
$('macro-instrument').addEventListener('change',drawMacro);
document.querySelectorAll('[data-macro-range]').forEach(b=>b.addEventListener('click',()=>{macroRange=Number(b.dataset.macroRange);document.querySelectorAll('[data-macro-range]').forEach(el=>{el.classList.toggle('selected',el===b);el.setAttribute('aria-pressed',String(el===b));});drawMacro();}));
document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{range=Number(b.dataset.range);document.querySelectorAll('[data-range]').forEach(el=>el.classList.toggle('selected',el===b));drawPrice();}));
document.querySelectorAll('[data-pair-range]').forEach(b=>b.addEventListener('click',()=>{pairRange=Number(b.dataset.pairRange);document.querySelectorAll('[data-pair-range]').forEach(el=>el.classList.toggle('selected',el===b));drawPairs();}));
['fund-search','fund-index','fund-state','favorites-only'].forEach(id=>$(id).addEventListener(id==='fund-search'?'input':'change',renderFunds));
$('fund-list').addEventListener('click',event=>{const button=event.target.closest('[data-star]');if(!button)return;event.preventDefault();event.stopPropagation();const code=button.dataset.star;if(favoriteCodes.has(code))favoriteCodes.delete(code);else favoriteCodes.add(code);storeFavorites();button.classList.toggle('saved',favoriteCodes.has(code));button.setAttribute('aria-pressed',String(favoriteCodes.has(code)));button.setAttribute('aria-label',(favoriteCodes.has(code)?'取消自选':'加入自选')+' '+code);$('fund-stats').lastElementChild.querySelector('b').textContent=favoriteCodes.size;if($('favorites-only').checked)renderFunds();});
$('export-csv').addEventListener('click',exportCsv);
function updateNavHint(){const nav=document.querySelector('.sidebar nav'),atEnd=nav.scrollLeft+nav.clientWidth>=nav.scrollWidth-3;nav.classList.toggle('nav-end',atEnd);$('nav-scroll-hint').textContent=atEnd?'← 滑动查看栏目':nav.scrollLeft>3?'← 左右滑动栏目 →':'滑动查看栏目 →';$('nav-scroll-hint').hidden=nav.scrollWidth<=nav.clientWidth+3;}
document.querySelector('.sidebar nav').addEventListener('scroll',updateNavHint,{passive:true});
window.addEventListener('resize',updateNavHint);
window.addEventListener('hashchange',selectView);
initValuation();selectView();load();
setInterval(()=>{if(document.visibilityState==='visible')load();},300000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')load();});
window.addEventListener('focus',()=>{if(document.visibilityState==='visible')load();});
