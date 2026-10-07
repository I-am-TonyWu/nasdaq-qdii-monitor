// Behaviour and measured-layout verification. oil-ui shoot.mjs owns screenshots.
'use strict';
const { chromium } = require(process.argv[2]);
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const baselineMode = process.argv.includes('--baseline');
const out = path.resolve('outputs/ui-v044');
const base = process.env.NASDAQ_UI_URL || 'http://127.0.0.1:8765';
const favoritesKey = 'nasdaq-favorites-v1';
const routes = ['overview', 'valuation', 'style', 'macro', 'funds', 'history'];
const checks = [], metrics = [];
let browser;
function check(name, value, details = null) {
  checks.push({ name, passed: Boolean(value), details });
}
function approx(a, b, epsilon = 1e-6) { return a === b || Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= epsilon; }
function fmt(value, decimals = 2) { return value == null ? '—' : Number(value).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }); }
async function ready(page) {
  await page.waitForFunction(() => typeof data !== 'undefined' && data && !document.getElementById('reload').disabled);
  await page.evaluate(() => document.fonts.ready);
}
async function valuationReady(page) {
  await page.waitForFunction(() => typeof valuationView !== 'undefined' && valuationView && document.getElementById('valuation-body').getAttribute('aria-busy') === 'false');
}
async function go(page, route) {
  await page.locator(`nav a[data-view="${route}"]`).click();
  await page.waitForFunction(r => !document.getElementById(r).hidden, route);
  if (route === 'valuation') await valuationReady(page);
  if (route === 'history') await page.waitForFunction(() => document.querySelectorAll('#history-list .history-row').length > 0 || /暂无历史|尚无|历史记录读取失败/.test(document.querySelector('#history-list').textContent));
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(100);
}
async function measure(page, route, width, height) {
  return page.evaluate(({ route, width, height }) => {
    const rect = element => {
      if (!element || !element.getClientRects().length) return null;
      const r = element.getBoundingClientRect(), s = getComputedStyle(element);
      return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height, font: Number.parseFloat(s.fontSize), weight: s.fontWeight, lineHeight: s.lineHeight };
    };
    const selectors = { topbar: '.topbar', heading: '.page-heading', status: '#statusbar', indexCards: '#index-cards', priceChart: '#price-chart', pricePanel: '#price-chart', score: '.score-panel', scoreNumber: '#score-display', preview: '#fund-preview', valuationToolbar: '.valuation-toolbar', valuationSummary: '#valuation-summary', valuationLevel: '#valuation-level-chart', valuationPercentile: '#valuation-percentile-chart', valuationTable: '.percentile-panel', styleCards: '#technical-cards', pairChart: '#pair-chart', macroCards: '#macro-cards', macroChart: '#macro-chart', fundList: '#fund-list', sourceList: '#source-list', historyList: '#history-list' };
    const elements = Object.fromEntries(Object.entries(selectors).map(([key, selector]) => [key, rect(document.querySelector(selector))]));
    if (elements.pricePanel) elements.pricePanel = rect(document.querySelector('#price-chart').closest('.panel'));
    const keyFonts = {};
    for (const selector of ['.panel h2', '.metric-head', '.metric-value', '.metric-change', '.metric-unit', '.score-row', '.score-formula', '.quota-note', '.quota-value', '.quota-evidence', '.fund-name', '.fund-name small', '.share-code', '.fund-cell small', '.chart-controls button', '.metric-tabs button', '.period-tabs button']) {
      const visible = [...document.querySelectorAll(selector)].filter(e => e.getClientRects().length);
      if (visible.length) keyFonts[selector] = [...new Set(visible.map(e => Number.parseFloat(getComputedStyle(e).fontSize)))];
    }
    const previewRows = [...document.querySelectorAll('.fund-preview-row')].filter(e => e.getClientRects().length).map(row => ({ row: rect(row), children: [...row.children].map(rect) }));
    return { route, viewport: { width, height }, elements, keyFonts, indexCardHeights: [...document.querySelectorAll('#index-cards .metric-card')].filter(e => e.getClientRects().length).map(e => rect(e).height), rsiCardHeights: [...document.querySelectorAll('#technical-cards .metric-card')].filter(e => e.getClientRects().length).map(e => rect(e).height), macroCardRects: [...document.querySelectorAll('#macro-cards .metric-card')].filter(e => e.getClientRects().length).map(rect), previewRows, innerWidth, clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, overflow: document.documentElement.scrollWidth > innerWidth + 1, documentHeight: document.documentElement.scrollHeight };
  }, { route, width, height });
}
async function collectMeasurements(page, width, height) {
  for (const route of routes) {
    await go(page, route);
    metrics.push(await measure(page, route, width, height));
  }
}
async function chartState(page, id) {
  return page.evaluate(id => {
    const chart = Chart.getChart(id);
    return chart && { labels: chart.data.labels, datasets: chart.data.datasets.map(d => ({ label: d.label, data: d.data, color: d.borderColor })), width: chart.width, height: chart.height, area: chart.chartArea, ticks: chart.scales.y?.ticks.map(t => t.value) || [] };
  }, id);
}
async function verifyOverview(page, width, api) {
  await go(page, 'overview');
  const value = api.score.value, scoreText = await page.locator('#score-display').innerText();
  check(`${width}: score equals current API`, scoreText.includes(fmt(value, 1)), { displayed: scoreText, expected: value });
  const calculated = api.score.components.every(c => c.points != null) ? api.score.components.reduce((sum, c) => sum + c.points * c.weight, 0) : null;
  check(`${width}: score formula preserves actual inputs`, approx(calculated, value), { calculated, api: value });
  const marker = page.locator('#score-position');
  check(`${width}: score scale has actual position`, await marker.count() > 0 && (value == null ? !await marker.isVisible() : approx(await marker.evaluate(e => Number.parseFloat(e.style.left)), value, 0.15)), { value });
  check(`${width}: score bands preserve thresholds`, await page.locator(`[data-score-band="${api.score.band}"]`).count() === 1 || value == null);
  const scoreParts = await page.locator('#score-components').innerText();
  for (const c of api.score.components) {
    check(`${width}: score component ${c.key}`, scoreParts.includes(c.name) && scoreParts.includes(fmt(c.weight * 100, 0)), { key: c.key, weight: c.weight, points: c.points });
    const row = page.locator(`#score-components [data-score-key="${c.key}"]`);
    check(`${width}: ${c.key} component has stable identity`, await row.count() === 1);
    if (await row.count()) {
      const shown = await row.innerText();
      check(`${width}: ${c.key} standardized value displayed`, c.points == null ? /待更新|不可计算|—/.test(shown) : shown.includes(fmt(c.points, 1)) || shown.includes(fmt(c.points, 0)), { shown, points: c.points });
      const progress = await row.locator('.score-progress > span').evaluate(e => Number.parseFloat(e.style.width));
      check(`${width}: ${c.key} bar represents normalized points`, approx(progress, c.points ?? 0, 0.15), { progress, points: c.points });
    }
  }
  const details = page.locator('.score-panel details');
  check(`${width}: calculation has explicit expandable entry`, await details.count() > 0);
  if (await details.count()) { await details.first().locator('summary').click(); check(`${width}: calculation remains available`, /0\.5|0\.50|50%/.test(await details.first().innerText())); await details.first().locator('summary').click(); }
  const count = await page.locator('.fund-preview-row').count(), actual = api.funds.filter(f => f.verified_channels > 0).length;
  check(`${width}: preview preserves available funds`, count === actual || count < actual && (await page.locator('#overview').innerText()).includes(String(actual)), { displayed: count, available: actual });
  check(`${width}: preview links to complete list`, (await page.locator('#overview a[href="#funds"]').count()) > 0);
  for (const key of ['NDX', 'NDXTMC', 'QQQ']) {
    await page.locator('#price-instrument').selectOption(key);
    const t = api.technicals[key], text = await page.locator('#technical-inline').innerText();
    check(`${width}: ${key} synchronized technicals`, (await page.locator('#technical-inline').getAttribute('data-instrument')) === key && text.includes('RSI(6)') && text.includes(fmt(t.rsi['6'])) && text.includes(fmt(t.ma200_distance)) && text.includes(fmt(t.drawdown_52w)) && (await page.locator('#price-technical-date').innerText()).includes(t.date), { technical: t });
    for (const months of [1, 3, 12, 60]) {
      await page.locator(`[data-range="${months}"]`).click();
      const chart = await chartState(page, 'price-chart');
      const expected = await page.evaluate(({ key, months }) => inRange(data.series[key].history, months), { key, months });
      check(`${width}: ${key} price ${months} months`, chart.width > 200 && JSON.stringify(chart.labels) === JSON.stringify(expected.map(r => r.date)) && JSON.stringify(chart.datasets[0].data) === JSON.stringify(expected.map(r => r.value)), { count: chart.labels.length, start: chart.labels[0], end: chart.labels.at(-1) });
    }
  }
  await page.locator('#price-instrument').selectOption('NDX');
  await page.locator('[data-range="3"]').click();
}
async function verifyValuation(page, width, api) {
  await go(page, 'valuation');
  for (const metric of ['ttm', 'forward', 'pb', 'VXN', 'VIX', 'FGI']) {
    await page.locator(`[data-metric="${metric}"]`).click(); await valuationReady(page);
    for (const years of [1, 3, 5, 10, 20, 0]) {
      await page.locator(`[data-years="${years}"]`).click(); await valuationReady(page);
      const view = await page.evaluate(() => valuationView), left = await chartState(page, 'valuation-level-chart'), right = await chartState(page, 'valuation-percentile-chart');
      check(`${width}: valuation ${metric}/${years} shared chart range`, JSON.stringify(left.labels) === JSON.stringify(right.labels) && JSON.stringify(left.labels) === JSON.stringify(view.history.map(r => r.date)) && JSON.stringify(left.datasets[0].data) === JSON.stringify(view.history.map(r => r.value)) && left.width > 200 && right.width > 200, { dataset: view.dataset, samples: view.history.length });
      check(`${width}: valuation ${metric}/${years} table preserved`, (await page.locator('#percentile-table-body tr').count()) === 5 && (years === 0 || (await page.locator(`#percentile-table-body tr[data-window="${years}"]`).getAttribute('class') || '').includes('selected-period')));
      const leftSpan = await page.locator('#valuation-level-range').innerText(), rightSpan = await page.locator('#valuation-percentile-range').innerText();
      check(`${width}: valuation ${metric}/${years} chart date labels synchronized`, leftSpan === rightSpan && (!view.history.length || leftSpan.includes(view.history[0].date) && leftSpan.includes(view.history.at(-1).date)), { leftSpan, rightSpan });
      for (const window of [1, 3, 5, 10, 20]) {
        const published = window === 5 && view.dataset === 'publisher' && view.publisher_summary?.percentile_5y != null;
        const expected = published ? view.publisher_summary.percentile_5y : view.windows[String(window)].percentile;
        const displayed = await page.locator(`#percentile-table-body tr[data-window="${window}"] td`).first().innerText();
        check(`${width}: valuation ${metric}/${years} ${window}y table percentile`, displayed.includes(expected == null ? '—' : fmt(expected, 1) + '%') && (!published || /源站/.test(displayed)), { expected, displayed });
      }
    }
    await page.locator('[data-years="1"]').click(); await valuationReady(page);
  }
  await page.locator('[data-metric="forward"]').click(); await valuationReady(page);
  await page.locator('#valuation-dataset').selectOption('official'); await valuationReady(page);
  await go(page, 'overview'); await go(page, 'valuation');
  check(`${width}: Forward chosen source survives navigation`, await page.locator('#valuation-dataset').inputValue() === 'official' && (await page.evaluate(() => valuationView.dataset)) === 'official');
  await page.locator('#valuation-dataset').selectOption('publisher'); await valuationReady(page);
  const publisher = await page.evaluate(() => valuationView), summary = await page.locator('#valuation-summary').innerText();
  check(`${width}: publisher uses its own latest value`, summary.includes(fmt(publisher.history.at(-1)?.value)), { displayed: summary, current: publisher.history.at(-1)?.value });
  check(`${width}: formal snapshot remains separate`, await page.locator('#official-valuation-values').isVisible() && /WSJ/.test(await page.locator('#official-valuation-values').innerText()));
  const official = await page.locator('#official-valuation-values').innerText();
  check(`${width}: formal values retain their own dates`, ['ttm', 'forward'].every(k => official.includes(fmt(api.valuation[k].value)) && (!api.valuation[k].date || official.includes(api.valuation[k].date))), { official });
  check(`${width}: chart provenance belongs to selected source`, (await page.locator('#valuation-chart-source').innerText()).includes(publisher.source.replace(/\s*\(.*/, '')) && await page.locator(`#valuation-method a[href="${publisher.source_url}"]`).count() > 0, { source: publisher.source });
  const before = await chartState(page, 'valuation-level-chart');
  if (before.labels.length > 3) {
    await page.locator('#valuation-start').evaluate(el => { el.value = '2'; el.dispatchEvent(new Event('input', { bubbles: true })); });
    const left = await chartState(page, 'valuation-level-chart'), right = await chartState(page, 'valuation-percentile-chart');
    check(`${width}: brush synchronizes both charts`, JSON.stringify(left.labels) === JSON.stringify(right.labels) && left.labels[0] === before.labels[2] && left.labels.length === before.labels.length - 2);
    await page.locator('#valuation-reset').click();
    check(`${width}: brush reset restores range`, JSON.stringify((await chartState(page, 'valuation-level-chart')).labels) === JSON.stringify(before.labels));
  }
  await page.locator('[data-metric="ttm"]').click(); await valuationReady(page);
  if (width < 600) {
    const scrolling = page.locator('.percentile-panel .table-scroll');
    check(`${width}: table has explicit visible horizontal-scroll hint`, await page.locator('#percentile-scroll-hint').isVisible() && /滑动|滚动/.test(await page.locator('#percentile-scroll-hint').innerText()) && (await scrolling.getAttribute('aria-describedby')) === 'percentile-scroll-hint');
    const columns = await scrolling.locator('thead th').allTextContents();
    check(`${width}: percentile table keeps six comparison columns`, JSON.stringify(columns.map(s => s.trim())) === JSON.stringify(['区间', '历史分位', '最低值', '最高值', '样本', '覆盖率']), { columns });
    const horizontal = await scrolling.evaluate(e => ({ client: e.clientWidth, scroll: e.scrollWidth }));
    const firstBefore = await scrolling.locator('thead th').first().boundingBox();
    await scrolling.evaluate(e => { e.scrollLeft = e.scrollWidth; });
    const movement = await scrolling.evaluate(e => ({ left: e.scrollLeft, max: e.scrollWidth - e.clientWidth, rectangle: { left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right } }));
    const firstAfter = await scrolling.locator('thead th').first().boundingBox(), lastAfter = await scrolling.locator('thead th').last().boundingBox();
    check(`${width}: table last column horizontally reachable`, horizontal.scroll <= horizontal.client || movement.left > 0 && Math.abs(movement.left - movement.max) <= 2 && lastAfter.x + lastAfter.width <= movement.rectangle.right + 2, { horizontal, movement, lastAfter });
    check(`${width}: table period column stays fixed`, Math.abs(firstBefore.x - firstAfter.x) <= 2, { firstBefore, firstAfter });
    await scrolling.evaluate(e => { e.scrollLeft = 0; });
  }
}
async function verifyStyleMacroHistory(page, width, api) {
  await go(page, 'style');
  const keys = ['VTV', 'CGDV', 'KO', 'BRKA', 'RUT'];
  for (const months of [1, 3, 12, 60]) {
    await page.locator(`[data-pair-range="${months}"]`).click();
    const chart = await chartState(page, 'pair-chart');
    check(`${width}: style ${months} months five identities/zero axis`, chart.datasets.length === keys.length && chart.ticks.includes(0) && chart.width > 200);
    const expected = await page.evaluate(months => {
      const keys = ['VTV', 'CGDV', 'KO', 'BRKA', 'RUT'], dates = [...new Set(keys.flatMap(k => data.pairs[k].history.map(r => r.date)))].sort(), end = dates.at(-1);
      return dates.filter(d => d >= rangeStart(end, months));
    }, months);
    check(`${width}: style ${months} months common dates`, JSON.stringify(chart.labels) === JSON.stringify(expected));
    const identities = await page.evaluate(() => [...document.querySelectorAll('#pair-values [data-pair]')].map(e => e.dataset.pair));
    check(`${width}: style ${months} result identity colors`, JSON.stringify(identities) === JSON.stringify(keys), { identities });
    const matchedResults = await page.evaluate(keys => keys.map(k => {
      const result = document.querySelector(`#pair-values [data-pair="${k}"]`), value = data.pairs[k].roc['35'];
      return result && result.textContent.includes(value == null ? '—' : num(value) + '%');
    }), keys);
    check(`${width}: style ${months} latest values match identities`, matchedResults.every(Boolean) && new Set(chart.datasets.map(d => d.color)).size === keys.length, { matchedResults, colors: chart.datasets.map(d => d.color) });
    const dotColors = await page.evaluate(keys => {
      const normalized = color => { const c = document.createElement('canvas'); c.width = c.height = 1; const x = c.getContext('2d'); x.fillStyle = color; x.fillRect(0, 0, 1, 1); return [...x.getImageData(0, 0, 1, 1).data].slice(0, 3).join(','); };
      const chart = Chart.getChart('pair-chart');
      return keys.map((key, i) => {
        const dot = document.querySelector(`#pair-values [data-pair="${key}"] .series-dot`);
        return dot && normalized(getComputedStyle(dot).backgroundColor) === normalized(chart.data.datasets[i].borderColor);
      });
    }, keys);
    check(`${width}: style ${months} dots match curve colors`, dotColors.every(Boolean), { dotColors });
  }
  await page.locator('[data-pair-range="3"]').click();
  await go(page, 'macro');
  for (const key of ['GOLD', 'DGS2', 'DGS10', 'DFII10']) {
    await page.locator('#macro-instrument').selectOption(key);
    for (const months of [1, 3, 12, 60]) {
      await page.locator(`[data-macro-range="${months}"]`).click();
      const chart = await chartState(page, 'macro-chart'), expected = await page.evaluate(({ key, months }) => inRange(data.series[key].history, months), { key, months });
      check(`${width}: macro ${key}/${months} data retained`, JSON.stringify(chart.datasets[0].data) === JSON.stringify(expected.map(r => r.value)) && JSON.stringify(chart.labels) === JSON.stringify(expected.map(r => r.date)), { samples: chart.labels.length, first: chart.labels[0], last: chart.labels.at(-1) });
      const caption = await page.locator('#macro-chart-caption').innerText();
      check(`${width}: macro ${key}/${months} date caption retained`, !expected.length || caption.includes(expected[0].date) && caption.includes(expected.at(-1).date), { caption });
    }
  }
  await page.locator('#macro-instrument').selectOption('GOLD'); await page.locator('[data-macro-range="12"]').click();
  await go(page, 'history');
  check(`${width}: history labels are Chinese`, !/\bavailable\b|\bfresh\b|\bstale\b/.test(await page.locator('#source-list').innerText()));
  check(`${width}: history has snapshot or explicit empty state`, await page.locator('#history-list .history-row').count() > 0 || /暂无|尚无/.test(await page.locator('#history-list').innerText()));
  check(`${width}: history sources retain expandable evidence`, await page.locator('#source-list details').count() > 0 && await page.locator('#source-list a[href^="https://"]').count() > 0);
  const historyResponse = await page.request.get(base + '/api/history');
  const historyRecords = await historyResponse.json(), visibleRows = await page.locator('#history-list .history-row').count();
  check(`${width}: history rows loaded and match API`, historyResponse.ok() && visibleRows === historyRecords.length, { rows: visibleRows, apiRecords: historyRecords.length });
  const groups = await page.locator('#source-list .source-section-row').allTextContents();
  check(`${width}: source purpose groups are explicit`, groups.length === 4 && /行情.*情绪/.test(groups[0]) && /WSJ/.test(groups[1]) && /参考.*不计入评分/.test(groups[2]) && /评分.*前瞻PE/.test(groups[3]), { groups });
  const sourceRows = await page.locator('#source-list .source-row').count(), expectedRows = Object.keys(api.series).length + Object.keys(api.valuation).length + Object.keys(api.valuation_references || {}).length + Object.keys(api.valuation_publisher || {}).length;
  check(`${width}: source grouping preserves all data rows`, sourceRows === expectedRows, { sourceRows, expectedRows });
}
async function verifyFunds(page, width, api) {
  await go(page, 'funds');
  const fieldOrder = await page.locator('#fund-list > .fund-row').first().locator(':scope > summary > .fund-cell').evaluateAll(cells => cells.map(c => c.dataset.label));
  check(`${width}: fund comparison column order preserved`, JSON.stringify(fieldOrder) === JSON.stringify(['代销额度', '直销额度', '近一年收益', '费率', '跟踪误差']), { fieldOrder });
  const saved = await page.evaluate(k => localStorage.getItem(k), favoritesKey);
  try {
    await page.locator('#fund-search').fill(''); await page.locator('#favorites-only').uncheck();
    const indexes = await page.locator('#fund-index option').evaluateAll(options => options.map(o => o.value));
    const states = await page.locator('#fund-state option').evaluateAll(options => options.map(o => o.value));
    for (const index of indexes) for (const state of states) {
      await page.locator('#fund-index').selectOption(index); await page.locator('#fund-state').selectOption(state);
      const expected = api.funds.filter(f => (index === 'all' || f.target === index) && (state !== 'open' || f.verified_channels > 0) && (state !== 'suspended' || f.shares.some(s => s.channels.some(c => c.status === 'suspended'))) && (state !== 'unknown' || f.shares.some(s => s.channels.some(c => ['unknown', 'expired'].includes(c.status)))));
      check(`${width}: fund filter ${index}/${state}`, await page.locator('#fund-list > .fund-row').count() === expected.length, { expected: expected.length });
    }
    await page.locator('#fund-index').selectOption('all'); await page.locator('#fund-state').selectOption('all');
    const share = api.funds.flatMap(f => f.shares).find(s => s.channels.length > 0);
    await page.locator('#fund-search').fill(share.code);
    check(`${width}: fund code search works`, (await page.locator('#fund-list').innerText()).includes(share.code));
    const star = page.locator(`[data-star="${share.code}"]`), was = await star.getAttribute('aria-pressed');
    await star.click();
    check(`${width}: favorite toggles`, await star.getAttribute('aria-pressed') !== was);
    const toggled = await page.evaluate(k => localStorage.getItem(k), favoritesKey);
    await page.reload(); await ready(page); await go(page, 'funds'); await page.locator('#fund-search').fill(share.code);
    check(`${width}: favorite persists reload`, await page.locator(`[data-star="${share.code}"]`).getAttribute('aria-pressed') !== was && (await page.evaluate(k => localStorage.getItem(k), favoritesKey)) === toggled);
    const shareRow = page.locator('.share-row').filter({ has: page.locator(`[data-star="${share.code}"]`) });
    await shareRow.locator(':scope > summary').click();
    await shareRow.locator('.share-channel-details > summary').click();
    const channels = shareRow.locator('.channel-card');
    check(`${width}: share channels preserved`, await channels.count() === share.channels.length);
    await channels.first().locator('.channel-meta > summary').click();
    const links = await channels.first().locator('.channel-meta a').evaluateAll(nodes => nodes.map(a => a.href));
    check(`${width}: channel original evidence entries retained`, links.length > 0 && links.every(url => /^https?:\/\//.test(url)));
    const docs = shareRow.locator('.share-information > summary');
    await docs.click();
    check(`${width}: share documents/fees accessible`, /管理.*托管.*销售服务费/.test(await shareRow.locator('.share-information').innerText()));
    if (width < 600) {
      const performance = page.locator('.fund-performance > summary').first();
      check(`${width}: mobile financial details have clear entry`, await performance.count() > 0 && await performance.isVisible());
      if (await performance.count()) { await performance.click(); check(`${width}: mobile financial details accessible`, /收益[\s\S]*费率[\s\S]*跟踪误差/.test(await performance.locator('..').innerText())); }
      check(`${width}: mobile share financial details visible after open`, await shareRow.locator('.share-mobile-performance').isVisible());
    }
    await page.locator('#fund-search').fill(''); await page.locator('#favorites-only').check();
    const expectedFavorites = await page.evaluate(() => data.funds.filter(f => f.shares.some(s => favoriteCodes.has(s.code))).length);
    check(`${width}: favorites-only filter uses current choices`, await page.locator('#fund-list > .fund-row').count() === expectedFavorites);
    const downloadPromise = page.waitForEvent('download'); await page.locator('#export-csv').click();
    const download = await downloadPromise; check(`${width}: channel export remains available`, /\.csv$/.test(download.suggestedFilename())); await download.cancel();
  } finally {
    await page.evaluate(({ k, saved }) => { if (saved == null) localStorage.removeItem(k); else localStorage.setItem(k, saved); }, { k: favoritesKey, saved });
    await page.reload(); await ready(page);
    check(`${width}: original favorites restored`, (await page.evaluate(k => localStorage.getItem(k), favoritesKey)) === saved);
  }
}
function verifyMeasuredLayout(before) {
  for (const item of metrics) {
    const w = item.viewport.width, label = `${w}/${item.route}`;
    check(`${label}: no page horizontal overflow`, !item.overflow, { innerWidth: item.innerWidth, scrollWidth: item.scrollWidth });
    if (item.route === 'overview') {
      const bounds = w < 600 ? [80, 96] : [148, 168];
      check(`${label}: quote card target height`, item.indexCardHeights.every(h => h >= bounds[0] - 1 && h <= bounds[1] + 1), { heights: item.indexCardHeights, target: bounds });
      check(`${label}: score number remains readable focal point`, item.elements.scoreNumber.font >= 48 && item.elements.scoreNumber.font <= 56, { font: item.elements.scoreNumber.font });
      if (w < 600) {
        check(`${label}: core score precedes trend`, item.elements.scoreNumber.y < item.elements.priceChart.y);
        check(`${label}: score appears within first viewport`, item.elements.scoreNumber.y < item.viewport.height, { y: item.elements.scoreNumber.y });
        check(`${label}: preview name above two quota columns`, item.previewRows.every(r => r.children.length === 3 && r.children[0].width >= r.row.width - 2 && r.children[1].y >= r.children[0].y + r.children[0].height - 1 && Math.abs(r.children[1].y - r.children[2].y) <= 1));
      }
    }
    if (w >= 1200 && item.route === 'style') check(`${label}: compact RSI card heights`, item.rsiCardHeights.every(h => h >= 111 && h <= 133), { heights: item.rsiCardHeights });
    if (w >= 1200 && item.route === 'macro') check(`${label}: four macro cards share row`, item.macroCardRects.length === 4 && new Set(item.macroCardRects.map(r => Math.round(r.y))).size === 1);
    if (w >= 1200 && item.route === 'valuation') check(`${label}: paired plot canvases align`, Math.abs(item.elements.valuationLevel.y - item.elements.valuationPercentile.y) <= 2 && Math.abs(item.elements.valuationLevel.height - item.elements.valuationPercentile.height) <= 2, { left: item.elements.valuationLevel, right: item.elements.valuationPercentile });
    for (const [selector, fonts] of Object.entries(item.keyFonts)) {
      if (selector === '.metric-unit') continue; // secondary units may remain 12px.
      check(`${label}: readable ${selector}`, fonts.every(px => px >= 13), { fonts });
    }
    const previous = before?.metrics?.find(b => b.route === item.route && b.viewport.width === w);
    if (previous && item.route === 'overview') {
      check(`${label}: overview core content moved earlier`, item.elements.scoreNumber.y < previous.elements.scoreNumber.y || w >= 1200 && item.elements.priceChart.y < previous.elements.priceChart.y, { beforeScoreY: previous.elements.scoreNumber.y, afterScoreY: item.elements.scoreNumber.y, beforeChartY: previous.elements.priceChart.y, afterChartY: item.elements.priceChart.y });
    }
  }
}
(async () => {
  fs.mkdirSync(out, { recursive: true });
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  for (const { width, height } of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const context = await browser.newContext({ viewport: { width, height }, acceptDownloads: true });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/#overview'); await ready(page);
    check(`${width}: snapshot rendered`, !await page.locator('#error').isVisible());
    await collectMeasurements(page, width, height);
    console.log(JSON.stringify({ phase: 'measurements', width, pages: routes.length }));
    if (!baselineMode) {
      const response = await page.request.get(base + '/api/snapshot'); assert.equal(response.status(), 200);
      const api = await response.json();
      await verifyOverview(page, width, api); console.log(JSON.stringify({ phase: 'overview', width }));
      await verifyValuation(page, width, api); console.log(JSON.stringify({ phase: 'valuation', width }));
      await verifyStyleMacroHistory(page, width, api); await verifyFunds(page, width, api);
      console.log(JSON.stringify({ phase: 'style/macro/history/funds', width }));
      for (const route of routes) {
        await go(page, route);
        check(`${width}: six-column navigation ${route}`, await page.locator(`nav a[data-view="${route}"]`).count() === 1 && (await page.locator(`nav a[data-view="${route}"]`).getAttribute('class')).includes('active'));
        check(`${width}: active navigation ${route} remains visible`, await page.locator(`nav a[data-view="${route}"]`).evaluate(e => { const r = e.getBoundingClientRect(), p = e.parentElement.getBoundingClientRect(); return r.left >= p.left - 1 && r.right <= p.right + 1; }));
        if (width < 600) check(`${width}: navigation ${route} has visible scrolling cue`, await page.locator('#nav-scroll-hint').isVisible() && /滑动|栏目/.test(await page.locator('#nav-scroll-hint').innerText()));
        check(`${width}: ${route} interaction leaves no overflow`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      }
      await go(page, 'overview');
      if (width === 1440) {
        await page.setViewportSize({ width: 720, height: 450 });
        await page.evaluate(() => window.scrollTo(0, 0));
        check('200% equivalent: overview remains within viewport width', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        check('200% equivalent: score and technical controls retained', await page.locator('#score-display').isVisible() && await page.locator('#price-instrument').isVisible());
        await page.setViewportSize({ width, height });
      }
    }
    check(`${width}: no browser script errors`, errors.length === 0, errors);
    await context.close();
  }
  const baselinePath = path.join(out, 'metrics-before.json');
  if (!baselineMode) verifyMeasuredLayout(fs.existsSync(baselinePath) ? JSON.parse(fs.readFileSync(baselinePath, 'utf8')) : null);
  const result = { mode: baselineMode ? 'baseline' : 'after', generatedAt: new Date().toISOString(), checks, metrics };
  fs.writeFileSync(baselineMode ? baselinePath : path.join(out, 'checks.json'), JSON.stringify(result, null, 2));
  if (!baselineMode) fs.writeFileSync(path.join(out, 'metrics-after.json'), JSON.stringify({ mode: 'after', generatedAt: result.generatedAt, metrics }, null, 2));
  const failures = checks.filter(c => !c.passed);
  console.log(JSON.stringify({ mode: result.mode, checks: checks.length, failed: failures.length, files: baselineMode ? [baselinePath] : [path.join(out, 'checks.json')], failures }, null, 2));
  if (failures.length) process.exitCode = 1;
})().catch(error => {
  fs.mkdirSync(out, { recursive: true });
  const failed = { mode: baselineMode ? 'baseline' : 'after', generatedAt: new Date().toISOString(), error: error.message, stack: error.stack, checks, metrics };
  fs.writeFileSync(path.join(out, baselineMode ? 'baseline-error.json' : 'checks.json'), JSON.stringify(failed, null, 2));
  console.error(error); process.exitCode = 1;
}).finally(async () => { if (browser) await browser.close(); });
