// Verify the repaired scheduler output through the API and actual page refresh behavior.
const { chromium } = require(process.argv[2]);
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let browser;
(async () => {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const out = path.resolve('data/revision-v043/browser'); fs.mkdirSync(out, { recursive: true });
  const results = [];
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:8765/?verify=0.4.3#overview');
    await page.waitForFunction(() => data && !loading);
    const s = await page.evaluate(() => data);
    assert.equal(s.version, '0.4.3'); assert.equal(s.fresh_count, s.source_count);
    assert.equal(s.quality_counts.updates, 0); assert.equal(s.quality_counts.history, 2);
    assert.equal(s.update_issues.length, 0);
    for (const key of ['VXN', 'VIX']) {
      assert.equal(s.series[key].date, s.current_market.expected_us_session);
      assert.equal(s.series[key].verification_status, 'verified_transmission');
    }
    const pe = s.valuation_publisher.forward;
    assert.equal(pe.date, s.current_market.expected_us_session); assert.ok(pe.score_ready);
    const expectedScore = .5 * (100 - pe.percentile) + .3 * s.series.VXN.percentile + .2 * (100 - s.series.FGI.value);
    assert.ok(Math.abs(s.score.value - expectedScore) < 1e-9);
    assert.match(await page.locator('#score-display').innerText(), new RegExp(s.score.value.toFixed(1).replace('.', '\\.')));
    assert.match(await page.locator('#statusbar').innerText(), /0项待更新 · 2项历史缺口/);
    assert.equal(await page.locator('#error').isVisible(), false);
    for (const key of ['NDX', 'NDXTMC', 'QQQ']) {
      const t = s.technicals[key]; assert.notEqual(t.drawdown_52w, null);
      await page.locator('#price-instrument').selectOption(key);
      assert.equal(await page.locator('#technical-inline').getAttribute('data-instrument'), key);
      assert.ok((await page.locator('#technical-inline').innerText()).includes(t.drawdown_52w.toFixed(2)));
    }
    // A resumed tab refreshes immediately; concurrent focus events share one in-flight request.
    let requests = 0;
    await page.route('**/api/snapshot', async route => {
      requests += 1; await new Promise(resolve => setTimeout(resolve, 200)); await route.continue();
    });
    await Promise.all([
      page.waitForResponse(r => r.url().endsWith('/api/snapshot')),
      page.evaluate(() => { for (let i = 0; i < 5; i++) window.dispatchEvent(new Event('focus')); })
    ]);
    await page.waitForFunction(() => !loading); assert.equal(requests, 1);
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    assert.equal(requests, 1);
    await Promise.all([
      page.waitForResponse(r => r.url().endsWith('/api/snapshot')),
      page.evaluate(() => {
        Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
        document.dispatchEvent(new Event('visibilitychange'));
      })
    ]);
    await page.waitForFunction(() => !loading); assert.equal(requests, 2);
    await page.locator('nav [data-view="valuation"]').click();
    await page.locator('[data-metric="forward"]').click();
    await page.waitForFunction(() => valuationView?.metric === 'forward' && document.getElementById('valuation-body').getAttribute('aria-busy') === 'false');
    assert.equal(await page.evaluate(() => valuationView.date), pe.date);
    assert.ok((await page.locator('#valuation-summary').innerText()).includes(pe.value.toFixed(2)));
    await page.locator('nav [data-view="history"]').click();
    await page.waitForFunction(() => document.querySelectorAll('#issues-list .issue').length === 2);
    assert.equal(await page.locator('#issues-list .issue').count(), 2);
    assert.ok((await page.locator('#issues-list').innerText()).split('\n').every(t => t.includes('历史缺口')));
    await page.locator('nav [data-view="overview"]').click();
    assert.deepEqual(errors, []); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(out, `overview-${width}.png`), fullPage: true });
    results.push({ width, snapshot: s.id, session: pe.date, forward: pe.value, percentile5y: pe.percentile,
      score: s.score.value, quality: s.quality_counts, resumeRequests: requests,
      drawdown: Object.fromEntries(Object.entries(s.technicals).map(([k, t]) => [k, t.drawdown_52w])) });
    await page.close();
  }
  fs.writeFileSync(path.join(out, 'checks.json'), JSON.stringify({ pass: true, results }, null, 2));
  await browser.close(); console.log(JSON.stringify({ pass: true, results, out }));
})().catch(async error => { console.error(error); if (browser) await browser.close(); process.exitCode = 1; });
