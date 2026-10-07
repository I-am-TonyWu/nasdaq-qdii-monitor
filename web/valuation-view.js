'use strict';
let valuationMetric='ttm',valuationDataset='reference',valuationYears=1,valuationView=null,valuationRequest=0;
const valuationNames={ttm:'PE (TTM)',forward:'Forward PE',pb:'PB',VXN:'VXN',VIX:'VIX',FGI:'CNN Fear & Greed'};
function renderValuation(){
  $('official-valuation-values').innerHTML=`<div class="official-origin"><span>发布快照</span><strong>WSJ / Birinyi</strong></div>${[['PE (TTM)',data.valuation.ttm],['Forward PE',data.valuation.forward]].map(([name,item])=>`<div class="official-stat"><span>${esc(name)}</span><b>${num(item.value)}<small>×</small></b><time datetime="${esc(item.date||'')}">${esc(item.date||'日期未知')}</time></div>`).join('')}`;
  if(!$('valuation').hidden)drawValuation();
}
function valuationText(id,value){const node=$(id);if(node)node.textContent=value;}
function valuationOptions(){
  const pe=['ttm','forward','pb'].includes(valuationMetric),select=$('valuation-dataset');
  select.hidden=!pe;
  const sourceGroup=select.closest('.valuation-source-group');if(sourceGroup)sourceGroup.hidden=!pe;
  if(valuationMetric==='forward'&&!['official','publisher'].includes(valuationDataset))valuationDataset='publisher';
  if(valuationMetric!=='forward'&&valuationDataset==='publisher')valuationDataset='reference';
  if(valuationMetric==='pb')valuationDataset='reference';
  if(!pe)valuationDataset='official';
  select.value=valuationDataset;
  for(const option of select.options)option.disabled=valuationMetric==='forward'&&option.value==='reference'||valuationMetric==='pb'&&option.value==='official'||valuationMetric!=='forward'&&option.value==='publisher';
  const publisher=valuationMetric==='forward'&&valuationDataset==='publisher';
  $('valuation-periods').hidden=false;$('valuation-body').hidden=false;
  $('official-valuation-values').hidden=false;
  $('valuation-source-note').hidden=!publisher;
  $('valuation-metrics').querySelectorAll('button').forEach(b=>{const on=b.dataset.metric===valuationMetric;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});
  $('valuation-periods').querySelectorAll('button').forEach(b=>{const on=Number(b.dataset.years)===valuationYears;b.classList.toggle('selected',on);b.setAttribute('aria-pressed',String(on));});
}
async function drawValuation(){
  if(!data||$('valuation').hidden)return;
  valuationOptions();
  const request=++valuationRequest;
  $('valuation-source-note').textContent='';
  valuationText('valuation-chart-source','正在读取所选来源…');
  $('valuation-body').setAttribute('aria-busy','true');$('valuation-loading').hidden=false;
  try{
    const query=new URLSearchParams({metric:valuationMetric,dataset:valuationDataset,years:valuationYears,snapshot_id:data.id});
    const response=await fetch('/api/valuation-view?'+query);
    if(!response.ok)throw Error('所选区间读取失败');
    const next=await response.json();if(request!==valuationRequest)return;
    valuationView=next;
    const size=next.history.length;
    for(const id of ['valuation-start','valuation-end']){$(id).max=Math.max(0,size-1);$(id).disabled=size<2;}
    $('valuation-start').value=0;$('valuation-end').value=Math.max(0,size-1);
    renderValuationWindow();renderPercentileTable();
    const publisher=next.dataset==='publisher';
    $('valuation-method').innerHTML=`<p>${link(next.source_url,next.source)} · ${publisher?'公开页面直接采集；本站取得近期日线与早期图表采样':next.frequency==='weekly'?'周频真实观测':'日频真实观测'}${next.reference?' · 独立参考，不参与正式评分':''}</p><p>${esc(next.reason||'中秩经验分布；历史曲线只使用该日期及之前的观测')}</p><p>日/周窗口按实际美国交易日历核验覆盖率；覆盖至少95%才显示本站计算分位。历史回填不冒充当时可知的预测。不同来源的当前值和历史分别展示，不拼接。</p>${publisher?'<p>当前5年、全部分位直接采用源站公布值，标注“源站”。综合观察分固定采用源站5年分位，与图表周期选择无关。历史分位曲线由本站重算；取得的采样不补为日线。此数据仅用于本机展示。</p>':''}`;
  }catch(error){if(request===valuationRequest){
    valuationView=null;
    for(const id of ['valuation-level-chart','valuation-percentile-chart'])if(charts[id]){charts[id].destroy();delete charts[id];}
    $('valuation-summary').innerHTML='';$('percentile-table-body').innerHTML='';$('percentile-position').innerHTML='';
    $('valuation-span').textContent='所选区间读取失败';$('valuation-method').innerHTML='';
    valuationText('valuation-chart-source','所选来源读取失败');
    valuationText('valuation-level-range','');valuationText('valuation-percentile-range','');
    if($('valuation-range-summary'))$('valuation-range-summary').innerHTML='';
    $('valuation-source-note').textContent='';
    $('valuation-loading').textContent=error.message;
    for(const id of ['valuation-start','valuation-end'])$(id).disabled=true;
    return;
  }}
  finally{if(request===valuationRequest)$('valuation-body').setAttribute('aria-busy','false');}
  if(request===valuationRequest){$('valuation-loading').hidden=true;$('valuation-loading').textContent='正在读取所选区间…';}
}
function renderValuationWindow(){
  if(!valuationView)return;
  const view=valuationView,start=Number($('valuation-start').value),end=Number($('valuation-end').value);
  const rows=view.history.slice(start,end+1),percentiles=view.percentile_history.slice(start,end+1);
  const first=rows[0],last=rows.at(-1);
  const published=view.reported_percentile;
  const usePublished=published&&start===0&&end===view.history.length-1&&last?.date===published.date;
  const p=usePublished?published.value:percentiles.at(-1)?.value;
  const percentileLabel=usePublished?(valuationYears?valuationYears+'年分位 · 源站':'全部分位 · 源站'):'历史分位 · 本站';
  const change=first&&last&&rows.length>1?(last.value/first.value-1)*100:null;
  const span=first?`${first.date} — ${last.date}`:'暂无历史';
  const period=valuationYears?`近${valuationYears}年`:'全部';
  const frequency=view.frequency==='weekly'?'周样本':'日样本';
  const unit=['ttm','forward','pb'].includes(view.metric)?'×':'点';
  const sourceName=view.dataset==='publisher'?'Dollar Liquidity':view.source;
  $('valuation-span').textContent=`${period} · ${span}${view.reference?' · 周频参考':view.dataset==='publisher'?' · 源站采集':''}`;
  valuationText('valuation-chart-source','图表来源 · '+sourceName);
  valuationText('valuation-level-unit','单位：'+unit);valuationText('valuation-percentile-unit','单位：%');
  valuationText('valuation-level-range',span);valuationText('valuation-percentile-range',span);
  $('valuation-level-title').textContent=['VXN','VIX','FGI'].includes(view.metric)?'指标走势':'估值走势';
  $('valuation-frequency').textContent=view.dataset==='publisher'?'近期日线 / 早期采样':view.reference?'周频参考':view.frequency==='weekly'?'周频发布':'日频';
  $('valuation-percentile-title').textContent=`${valuationYears?'滚动'+valuationYears+'年':'累计'}${frequency}分位`;
  const levelLabel=valuationNames[view.metric];
  if(view.dataset==='publisher'){
    const published=view.publisher_summary;
    $('valuation-source-note').textContent=`${published?.percentile_5y!=null?`源站5年分位 ${num(published.percentile_5y,0)}% · `:''}长历史图为本站采样${view.status==='stale'?' · 本次数据已过期':''}`;
  }
  $('valuation-summary').innerHTML=[[levelLabel,num(last?.value)],[percentileLabel,p==null?'—':num(p,1)+'%'],['区间位置',p==null?(view.dataset==='publisher'?'本站未重算':'历史不足'):p<=20?'低位':p>=80?'高位':'中间'],['区间变动',change==null?'—':signed(change)+'%']].map(([label,value],i)=>`<article class="valuation-stat ${i===0?'primary-stat':''}"><span>${esc(label)}</span><b class="${i===2?'status-word':''}">${esc(value)}${i===0?`<small>${unit}</small>`:''}</b></article>`).join('');
  lineChart('valuation-level-chart',rows,{label:valuationNames[view.metric]});
  lineChart('valuation-percentile-chart',percentiles,{color:cssColor('--blue'),label:'历史分位',percent:true});
  for(const id of ['valuation-level-chart','valuation-percentile-chart']){
    const chart=charts[id];if(!chart)continue;
    for(const axis of ['x','y'])chart.options.scales[axis].ticks.font.size=13;
    chart.update('none');
  }
  if($('valuation-range-summary'))$('valuation-range-summary').innerHTML=`<div><span>区间起点</span><b>${num(first?.value)}<small>${unit}</small></b></div><span class="range-direction" aria-hidden="true">→</span><div><span>区间终点</span><b>${num(last?.value)}<small>${unit}</small></b></div>`;
  $('valuation-level-empty').hidden=rows.length>=2;
  $('valuation-level-empty').textContent=rows.length?'仅有1个观测，尚无连续历史':'此类历史尚未取得';
  $('valuation-percentile-empty').hidden=percentiles.some(r=>r.value!=null);
  $('valuation-percentile-empty').textContent=view.dataset==='publisher'?`历史分位曲线尚未取得${usePublished?`；当前分位${num(p,0)}%由源站公布`:''}`:view.stats.reason||'历史覆盖不足，分位暂不可算';
  $('percentile-position').innerHTML=`<div><span>${usePublished?percentileLabel:'当前'+frequency+'分位'+(view.reference?' · 参考':' · 本站')}</span><b>${p==null?'—':num(p,1)+'%'}</b></div><div class="percentile-scale">${p==null?'':`<i style="left:${Math.max(0,Math.min(100,p))}%"></i>`}</div><div class="percentile-labels"><span>0% 低位</span><span>50%</span><span>100% 高位</span></div>`;
  $('valuation-brush-dates').textContent=span;
}
function renderPercentileTable(){
  const view=valuationView;
  $('percentile-table-label').textContent=(view.frequency==='weekly'?'周样本':'日样本')+(view.reference?' · 参考':view.dataset==='publisher'?' · 样本与覆盖率为本站取得数':'' );
  $('percentile-table-body').innerHTML=[1,3,5,10,20].map(year=>{
    const w=view.windows[String(year)],s=view.dataset==='publisher'?view.publisher_summary:null;
    const reported=year===5&&s?.percentile_5y!=null,p=reported?s.percentile_5y:w.percentile;
    const tag=reported?'<small>源站公布</small>':'';
    const missingPercentile=p==null&&!w.available?'<small class="percentile-unavailable">覆盖不足</small>':'';
    return `<tr class="${year===valuationYears?'selected-period':''}" data-window="${year}"><th>${year}年</th><td>${p==null?'—':num(p,1)+'%'}${tag}${missingPercentile}</td><td>${num(reported?s.minimum_5y:w.minimum)}${tag}</td><td>${num(reported?s.maximum_5y:w.maximum)}${tag}</td><td>${w.samples}</td><td>${num(w.coverage_ratio*100,1)}%${w.available?'':view.dataset==='publisher'?'<small>本地采样</small>':'<small>不足</small>'}</td></tr>`;
  }).join('');
}
function initValuation(){
  const tableScroll=$('percentile-table-body').closest('.table-scroll');
  if(tableScroll&&!$('percentile-scroll-hint')){
    const hint=document.createElement('p');hint.id='percentile-scroll-hint';
    hint.textContent='左右滑动查看最高值、样本与覆盖率';
    tableScroll.before(hint);tableScroll.setAttribute('aria-describedby',hint.id);
  }
  $('valuation-metrics').addEventListener('click',event=>{const button=event.target.closest('[data-metric]');if(!button)return;valuationMetric=button.dataset.metric;if(valuationMetric==='ttm')valuationDataset='reference';if(valuationMetric==='forward')valuationDataset='publisher';drawValuation();});
  $('valuation-periods').addEventListener('click',event=>{const button=event.target.closest('[data-years]');if(!button)return;valuationYears=Number(button.dataset.years);drawValuation();});
  $('valuation-dataset').addEventListener('change',event=>{valuationDataset=event.target.value;drawValuation();});
  for(const id of ['valuation-start','valuation-end'])$(id).addEventListener('input',()=>{let start=Number($('valuation-start').value),end=Number($('valuation-end').value);if(start>end){if(id==='valuation-start')$('valuation-end').value=start;else $('valuation-start').value=end;}renderValuationWindow();});
  $('valuation-reset').addEventListener('click',()=>{if(!valuationView)return;$('valuation-start').value=0;$('valuation-end').value=Math.max(0,valuationView.history.length-1);renderValuationWindow();});
}
