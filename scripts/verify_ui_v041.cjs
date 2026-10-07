// End-to-end acceptance checks; visual evidence is produced by oil-ui shoot.mjs.
const { chromium } = require(process.argv[2]);
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let browser;
(async () => {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const out = path.resolve('data/revision-v041/browser'); fs.mkdirSync(out, { recursive: true });
  const results = [];
  const ready = page => page.waitForFunction(() => valuationView && document.getElementById('valuation-body').getAttribute('aria-busy') === 'false');
  const matchedCharts = async page => {
    const result = await page.evaluate(() => {
      const left = Chart.getChart('valuation-level-chart'), right = Chart.getChart('valuation-percentile-chart');
      return { left: left.data.labels, right: right.data.labels, percentile: right.data.datasets[0].data,
        current: valuationView.stats.percentile, width: left.width, years: valuationView.years,
        metric: valuationView.metric, dataset: valuationView.dataset };
    });
    assert.deepEqual(result.left, result.right); assert.ok(result.width > 200);
    return result;
  };
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const external=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:8765/'))external.push(r.url());});
    await page.goto('http://127.0.0.1:8765/?verify=0.4.1');
    await page.waitForFunction(() => !document.getElementById('reload').disabled);
    assert.equal(await page.locator('#error').isVisible(), false);
    assert.equal(await page.locator('.fund-preview-row').count(), await page.evaluate(()=>data.funds.filter(f=>f.verified_channels>0).length));
    assert.equal(await page.locator('.score-panel .badge.dark').count(),0);
    assert.match(await page.locator('.score-note').innerText(),/谨慎[\s\S]*正常[\s\S]*恐慌/);
    for(const key of ['NDX','NDXTMC','QQQ']){
      await page.locator('#price-instrument').selectOption(key);
      const t=await page.evaluate(k=>data.technicals[k],key);
      const text=await page.locator('#technical-inline').innerText();
      assert.equal(await page.locator('#technical-inline').getAttribute('data-instrument'),key);
      assert.match(text,/RSI\(6\)/);assert.ok(text.includes(t.rsi['6'].toFixed(2)));
      assert.ok(text.includes(t.ma200_distance.toFixed(2)));
      assert.ok(text.includes(t.drawdown_52w===null?'—':t.drawdown_52w.toFixed(2)));
      assert.match(await page.locator('#price-technical-date').innerText(),new RegExp(key));
      results.push({width,type:'technical',key,rsi6:t.rsi['6'],drawdown:t.drawdown_52w});
    }
    await page.locator('#price-instrument').selectOption('NDX');
    const caps=await page.locator('.fund-preview-row').allTextContents();
    assert.ok(caps.some(t=>t.includes('南方')&&t.includes('200')&&t.includes('10')&&t.includes('公告')));
    const southernDirect=await page.locator('.fund-preview-row').filter({hasText:'南方'}).locator(':scope > div').nth(2).innerText();
    assert.match(southernDirect,/200/);assert.match(southernDirect,/10/);assert.match(southernDirect,/A\/C/);assert.ok(!southernDirect.includes('1,000'));
    assert.ok(caps.some(t=>t.includes('大成')&&t.includes('100')&&t.includes('公告')));
    assert.ok(caps.some(t=>t.includes('华泰柏瑞')&&t.includes('A/C/I总额度')));
    await page.evaluate(()=>document.fonts.ready);
    const family=await page.locator('body').evaluate(el=>getComputedStyle(el).fontFamily);assert.match(family,/Inter Variable/);
    const contrast=await page.evaluate(()=>{
      const parse=color=>color.match(/[\d.]+/g).slice(0,3).map(Number);
      const luminance=rgb=>rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
      const ratio=(fg,bg)=>{const a=luminance(parse(fg)),b=luminance(parse(bg));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);};
      const cases=[['正文','--ink','--white'],['辅助文字','--muted','--bg'],['选中控件','--selected-ink','--teal-4'],['状态条','--selected-ink','--teal-3'],['红色数值','--red','--white'],['绿色数值','--green','--white'],['公告标记','--amber','--white']];
      return cases.map(([name,fg,bg])=>({name,foreground:cssColor(fg),background:cssColor(bg),ratio:ratio(cssColor(fg),cssColor(bg))}));
    });
    contrast.forEach(c=>assert.ok(c.ratio>=4.5,JSON.stringify(c)));results.push({width,type:'contrast',contrast});

    const cdp=await page.context().newCDPSession(page);await cdp.send('DOM.enable');
    const root=await cdp.send('DOM.getDocument');
    await cdp.send('CSS.enable');
    const numberNode=await cdp.send('DOM.querySelector',{nodeId:root.root.nodeId,selector:'.metric-value'});
    const fonts=await cdp.send('CSS.getPlatformFontsForNode',{nodeId:numberNode.nodeId});
    assert.ok(fonts.fonts.some(f=>f.isCustomFont&&f.familyName.includes('Inter')));
    const chineseNode=await cdp.send('DOM.querySelector',{nodeId:root.root.nodeId,selector:'#page-title'});
    const chinese=await cdp.send('CSS.getPlatformFontsForNode',{nodeId:chineseNode.nodeId});
    assert.ok(chinese.fonts.some(f=>!f.isCustomFont&&f.glyphCount>0));
    results.push({width,type:'fonts',latin:fonts.fonts,chinese:chinese.fonts});
    assert.equal(await page.evaluate(() => data.watchlist_count), 44);
    for (const [months, minimum] of [[1, 18], [3, 55], [12, 240], [60, 1200]]) {
      await page.locator(`[data-range="${months}"]`).click();
      const c = await page.evaluate(() => {
        const chart = Chart.getChart('price-chart');
        return { samples: chart.data.labels.length, finalTick: chart.scales.x.ticks.at(-1).value, width: chart.width };
      });
      assert.ok(c.samples >= minimum); assert.equal(c.finalTick, c.samples - 1); assert.ok(c.width > 200);
      results.push({ width, type: 'price', months, samples: c.samples });
    }
    await page.locator('#price-instrument').selectOption('NDXTMC');
    assert.match(await page.locator('#price-chart-caption').textContent(), /历史不足/);
    await page.locator('nav [data-view="style"]').click();
    for (const months of [1, 3, 12, 60]) {
      await page.locator(`[data-pair-range="${months}"]`).click();
      const c = await page.evaluate(() => {const chart=Chart.getChart('pair-chart'); return {
        samples:chart.data.labels.length, finalTick:chart.scales.x.ticks.at(-1).value,
        zero:chart.scales.y.ticks.some(t=>t.value===0),width:chart.width,
        counts:chart.data.datasets.map(d=>d.data.filter(v=>v!==null).length)};});
      assert.equal(c.finalTick, c.samples - 1); assert.ok(c.zero); assert.ok(c.width > 200);assert.equal(c.counts.length,5);assert.ok(c.counts[3]>0&&c.counts[4]>0);
      if (months === 60) assert.ok(c.counts[1] < c.counts[0]);
      results.push({ width, type: 'pair', months, samples: c.samples });
    }
    await page.locator('nav [data-view="valuation"]').click(); await ready(page);
    for (const years of [1, 3, 5, 10, 20, 0]) {
      await page.locator(`[data-years="${years}"]`).click();
      await page.waitForFunction(y => valuationView?.years === y && document.getElementById('valuation-body').getAttribute('aria-busy')==='false', years);
      const chart = await matchedCharts(page);
      assert.equal(await page.locator('#percentile-table-body tr').count(), 5);
      if (years === 20) assert.ok(chart.percentile.every(p => p === null));
      if (years > 0 && years < 20) {
        assert.equal(chart.percentile.at(-1), chart.current);
        assert.equal(await page.locator('.selected-period').getAttribute('data-window'), String(years));
      }
      results.push({ width, type: 'valuation', years, samples: chart.left.length, percentile: chart.current });
    }
    // The shared brush changes both chart domains; keyboard operation is also supported.
    await page.locator('#valuation-start').focus(); await page.keyboard.press('ArrowRight');
    const brushed=await matchedCharts(page);
    assert.ok(brushed.left.length < await page.evaluate(()=>valuationView.history.length));
    await page.locator('#valuation-reset').click();
    assert.equal((await matchedCharts(page)).left.length, await page.evaluate(()=>valuationView.history.length));
    // Rapid period switching may not commit a slower, obsolete response.
    await page.locator('[data-years="5"]').click(); await page.locator('[data-years="1"]').click();
    await page.waitForFunction(()=>valuationView?.years===1&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
    assert.equal((await matchedCharts(page)).years,1);
    await page.locator('[data-metric="forward"]').click();
    await page.waitForFunction(()=>valuationView?.metric==='forward'&&valuationView?.dataset==='publisher'&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
    assert.equal(await page.locator('#valuation-body').isVisible(),true);
    assert.equal(await page.locator('#valuation-periods').isVisible(),true);
    assert.equal(await page.locator('#forward-publisher-image').count(),0);
    assert.equal(await page.locator('#official-valuation-values').isVisible(),false);
    assert.match(await page.locator('#valuation-source-note').innerText(),/Dollar Liquidity.*18%/);
    assert.match(await page.locator('#valuation-summary').innerText(),/21.85/);
    assert.equal(await page.evaluate(()=>data.valuation.forward.value),23.87);
    assert.equal(await page.evaluate(()=>data.score.value),null);
    for(const years of [1,3,5,10,20,0]){
      await page.locator(`[data-years="${years}"]`).click();
      await page.waitForFunction(y=>valuationView?.years===y&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false',years);
      const sample=await matchedCharts(page);assert.equal(sample.dataset,'publisher');assert.ok(sample.left.length>200);
      if(years===1||years===3)assert.notEqual(sample.current,null);
      else assert.ok(sample.percentile.every(p=>p===null));
      results.push({width,type:'forward-direct',years,samples:sample.left.length,percentile:sample.current});
    }
    await page.locator('#valuation-start').focus();await page.keyboard.press('ArrowRight');
    assert.ok((await matchedCharts(page)).left.length<await page.evaluate(()=>valuationView.history.length));
    await page.locator('#valuation-reset').click();
    await page.locator('#valuation-dataset').selectOption('official');
    await page.waitForFunction(()=>valuationView?.metric==='forward'&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
    let chart=await matchedCharts(page); assert.equal(chart.left.length,1); assert.ok(chart.percentile.every(p=>p===null));
    assert.match(await page.locator('#valuation-summary').innerText(),/23.87/);
    await page.locator('[data-metric="pb"]').click(); await page.waitForFunction(()=>valuationView?.metric==='pb'&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
    assert.equal((await matchedCharts(page)).dataset,'reference');
    for(const metric of ['VXN','VIX','FGI']){
      await page.locator(`[data-metric="${metric}"]`).click();
      await page.waitForFunction(m=>valuationView?.metric===m&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false',metric);
      chart=await matchedCharts(page);assert.equal(chart.dataset,'official');
      assert.ok(chart.left.length>200);assert.equal(await page.locator('#valuation-dataset').isVisible(),false);
    }
    await page.locator('[data-metric="ttm"]').click();await ready(page);
    await page.locator('#valuation-dataset').selectOption('official');
    await page.waitForFunction(()=>valuationView?.dataset==='official'&&valuationView?.metric==='ttm'&&document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
    assert.match(await page.locator('#valuation-summary').innerText(),/34.68/);
    // A failed request must clear the previous source/period instead of presenting it as current.
    await page.route('**/api/valuation-view?**',route=>route.fulfill({status:503,body:'unavailable'}));
    await page.locator('[data-years="3"]').click();await page.waitForFunction(()=>!valuationView&&document.getElementById('valuation-loading').textContent.includes('失败'));
    assert.equal(await page.locator('#percentile-table-body tr').count(),0);
    await page.unroute('**/api/valuation-view?**');await page.locator('[data-years="1"]').click();await ready(page);
    await page.locator('nav [data-view="funds"]').click();
    assert.equal(await page.locator('.fund-row').count(),18);
    assert.equal(await page.locator('.share-row').count(),44);
    assert.deepEqual(await page.locator('.fund-table-head>span').allTextContents(),['基金 / 份额 · 金额为人民币元','代销额度','直销额度','近一年收益','费率','跟踪误差']);
    for(const code of ['019524','017091']){
      await page.locator('#fund-search').fill(code);assert.equal(await page.locator('.fund-row').count(),1);
      assert.match(await page.locator('#fund-list').innerText(),new RegExp(code));
    }
    await page.locator('#fund-search').fill('万家');assert.match(await page.locator('#fund-list').innerText(),/A\/C总额度/);
    await page.locator('#fund-search').fill('022525');
    const tianhong=await page.evaluate(()=>data.funds.flatMap(f=>f.shares).find(s=>s.code==='022525').channels.filter(c=>c.verification_basis==='user_confirmation'));
    assert.deepEqual(tianhong.map(c=>[c.channel,c.daily_limit,c.channel_kind,c.purchasable]),[['微信',100,'distributor',true],['京东金融',100,'distributor',true]]);
    await page.locator('#fund-search').fill('021000');
    const southern=await page.evaluate(()=>data.funds.flatMap(f=>f.shares).find(s=>s.code==='021000').channels.find(c=>c.verification_basis==='user_confirmation'));
    assert.equal(southern.daily_limit,200);assert.equal(southern.channel_kind,'direct');assert.equal(southern.purchasable,true);
    await page.locator('#fund-search').fill('');await page.locator('#fund-state').selectOption('open');
    assert.equal(await page.locator('.fund-row').count(),9);
    const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#export-csv').click()]);
    const csv=fs.readFileSync(await download.path(),'utf8');assert.match(csv,/渠道类型/);assert.match(csv,/微信/);assert.match(csv,/京东金融/);
    await page.locator('nav [data-view="macro"]').click();
    assert.equal(await page.locator('#macro-cards>.metric-card').count(),4);
    assert.equal(await page.evaluate(()=>Object.keys(data.series).some(k=>['CNY','CNH'].includes(k))),false);
    await page.locator('nav [data-view="history"]').click();
    await page.waitForFunction(()=>document.getElementById('source-list').textContent.includes('同日官源核对通过'));
    assert.match(await page.locator('#source-list').innerText(),/同日官源核对通过/);
    for(const view of ['valuation','style','overview']){await page.locator(`nav [data-view="${view}"]`).click();await page.waitForTimeout(80);}
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.close();
  }
  const page=await browser.newPage({viewport:{width:640,height:450},deviceScaleFactor:2});
  await page.goto('http://127.0.0.1:8765/#valuation');await ready(page);await matchedCharts(page);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({pass:true,results},null,2));
  await browser.close();console.log(JSON.stringify({pass:true,rangeChecks:results.length,viewports:[1280,390],zoom:200,out}));
})().catch(async error=>{console.error(error);if(browser)await browser.close();process.exitCode=1;});
