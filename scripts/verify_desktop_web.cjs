'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
let playwright;
if (process.env.NASDAQ_PLAYWRIGHT) playwright=require(process.env.NASDAQ_PLAYWRIGHT);
else { try { playwright=require('playwright'); } catch { playwright=require(path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); } }
const {chromium}=playwright;
const base = process.argv[2], output = process.argv[3], checks=[];
let browser;
function check(name, passed) { checks.push({name,passed:Boolean(passed)});assert.ok(passed,name); }
(async()=>{
  browser = await chromium.launch({channel:'msedge',headless:true});
  for(const width of [1440,390]) {
    const page = await browser.newPage({viewport:{width,height:844}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/#overview');
    await page.waitForFunction(()=>typeof data!=='undefined' && data);
    for(const route of ['overview','valuation','style','macro','funds','history']) {
      await page.locator(`nav a[data-view="${route}"]`).click();
      await page.waitForFunction(r=>!document.getElementById(r).hidden,route);
      if(route==='valuation')await page.waitForFunction(()=>typeof valuationView!=='undefined' && valuationView && document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
      check(`${width}: ${route} renders without horizontal overflow`,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    }
    await page.locator('nav a[data-view="valuation"]').click();
    await page.locator('[data-metric="forward"]').click();
    await page.waitForFunction(()=>valuationView?.metric==='forward' && document.getElementById('valuation-body').getAttribute('aria-busy')==='false');
    // Verify API-backed valuation and percentile charts share real dates.
    check(`${width}: Forward PE charts synchronize`,await page.evaluate(()=>{
      const level=Chart.getChart('valuation-level-chart'),percent=Chart.getChart('valuation-percentile-chart');
      return level.data.labels.length>0 && JSON.stringify(level.data.labels)===JSON.stringify(percent.data.labels);
    }));
    check(`${width}: no JavaScript errors`,errors.length===0);
    await page.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;checks.push({name:error.message,passed:false});}).finally(async()=>{
  if(browser)await browser.close();
  fs.writeFileSync(output,JSON.stringify({checks,passed:checks.filter(x=>x.passed).length,failed:checks.filter(x=>!x.passed).length},null,2));
  console.log(JSON.stringify({checks:checks.length,failed:checks.filter(x=>!x.passed).length}));
});
