// Browser acceptance checks with the bundled Playwright runtime supplied as argv[2].
const { chromium } = require(process.argv[2]);
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let browser;
(async () => {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const out = path.resolve('data/revision-audit/browser'); fs.mkdirSync(out, { recursive: true });
  const results = [];
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:8765/?verify=0.2');
    await page.waitForFunction(() => !document.getElementById('reload').disabled);
    assert.equal(await page.locator('#error').isVisible(), false);
    for (const [months, minimum] of [[1, 18], [3, 55], [12, 240], [60, 1200]]) {
      await page.locator(`[data-range="${months}"]`).click();
      const chart = await page.evaluate(() => {
        const c = Chart.getChart('price-chart'); return { samples: c.data.labels.length, first: c.data.labels[0], last: c.data.labels.at(-1), finalTick:c.scales.x.ticks.at(-1).value, width: c.width, height: c.height };
      });
      assert.ok(chart.samples >= minimum, JSON.stringify(chart));
      assert.equal(chart.finalTick,chart.samples-1);
      assert.ok(chart.width > 200 && chart.height > 100);
      results.push({ width, chart: 'price', months, ...chart });
    }
    await page.locator('#price-instrument').selectOption('NDXTMC');
    assert.match(await page.locator('#price-chart-caption').textContent(), /历史不足/);
    await page.screenshot({ path: path.join(out, `overview-${width}.png`), fullPage: true });
    await page.locator('nav [data-view="style"]').click();
    for (const [months, minimum] of [[1,18],[3,55],[12,240],[60,1200]]) {
      await page.locator(`[data-pair-range="${months}"]`).click();
      const chart = await page.evaluate(() => { const c=Chart.getChart('pair-chart');return {samples:c.data.labels.length,first:c.data.labels[0],last:c.data.labels.at(-1),finalTick:c.scales.x.ticks.at(-1).value,zero:c.scales.y.ticks.some(t=>t.value===0),width:c.width,height:c.height,counts:c.data.datasets.map(d=>d.data.filter(v=>v!==null).length)};});
      assert.ok(chart.samples >= minimum); assert.equal(chart.finalTick,chart.samples-1); assert.ok(chart.zero); assert.ok(chart.width>200);
      if (months===60) assert.ok(chart.counts[1]<chart.counts[0]);
      results.push({ width, chart:'pair',months,...chart });
    }
    await page.screenshot({ path:path.join(out,`style-${width}.png`),fullPage:true });
    await page.locator('nav [data-view="valuation"]').click();
    await page.waitForFunction(()=>Chart.getChart('sentiment-chart')?.width>200);
    assert.equal(await page.locator('#valuation-panels').innerText().then(t=>t.includes('23.87')),true);
    await page.screenshot({ path:path.join(out,`valuation-${width}.png`),fullPage:true });
    await page.locator('nav [data-view="funds"]').click();
    assert.equal(await page.locator('.fund-row').count(),18);
    await page.locator('#fund-search').fill('019441');
    await page.locator('.share-row').first().locator(':scope > summary').click();
    assert.match(await page.locator('#fund-list').innerText(),/份额共用/);
    await page.screenshot({ path:path.join(out,`fund-${width}.png`),fullPage:true });
    await page.locator('#fund-search').fill('');
    await page.locator('#fund-state').selectOption('open');
    assert.equal(await page.locator('.fund-row').count(),6);
    for (const view of ['macro','style','overview','valuation','style']) {
      await page.locator(`nav [data-view="${view}"]`).click();
      await page.waitForTimeout(70);
    }
    assert.deepEqual(errors,[]);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    assert.equal(overflow,false);
    await page.close();
  }
  // 200% browser zoom uses a 640 CSS-pixel layout at a 1280 pixel display.
  const context=await browser.newContext({viewport:{width:640,height:450},deviceScaleFactor:2});
  const page=await context.newPage();await page.goto('http://127.0.0.1:8765/#style');
  await page.waitForFunction(()=>!document.getElementById('reload').disabled);
  await page.locator('[data-pair-range="60"]').click();
  await page.screenshot({path:path.join(out,'style-200percent.png'),fullPage:true});
  fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({pass:true,results},null,2));
  await browser.close();console.log(JSON.stringify({pass:true,rangeChecks:results.length,viewports:[1280,390],out}));
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exitCode=1;});
