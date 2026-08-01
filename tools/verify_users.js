// Headless check that every participant in the manifest loads and draws.
// Usage: NODE_PATH=/home/ubuntu/b/node_modules node tools/verify_users.js [outdir]
const { chromium } = require('playwright-core');
const EXE = process.env.HOME + '/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell';
const BASE = process.env.NSE_URL || 'http://127.0.0.1:8099';
const OUT = process.argv[2] || '/tmp/nse_users';
const fs = require('fs');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const mf = await (await fetch(BASE + '/data/manifest.json')).json();
  const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
  let bad = 0;

  for (const u of mf.users) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errs = [];
    page.on('pageerror', e => errs.push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    page.on('requestfailed', r => errs.push('reqfail: ' + r.url()));

    await page.goto(BASE + '/index.html', { waitUntil: 'load', timeout: 60000 });
    await page.waitForTimeout(6000);            // React CDN boot + default cube + first draw
    // The switcher is a React dropdown: it needs real events, not element.click().
    let clicked = 'ok';
    try {
      await page.click('button[title="Choose participant"]', { timeout: 10000 });
      await page.waitForTimeout(500);
      await page.getByText(u.label, { exact: true }).first().click({ timeout: 10000 });
    } catch (e) { clicked = 'click-failed'; }
    await page.waitForTimeout(6000);             // cube fetch + redraw

    const probe = await page.evaluate(() => {
      const cells = [...document.querySelectorAll('[data-ch]')];
      const colored = cells.filter(c => {
        const b = getComputedStyle(c).backgroundColor;
        return b && b !== 'rgba(0, 0, 0, 0)' && !/238, 240, 243|236, 238, 241/.test(b);
      });
      const cv = [...document.querySelectorAll('canvas')].filter(c => c.width > 0 && c.height > 0);
      return { cells: cells.length, colored: colored.length, canvases: cv.length, text: document.body.innerText.slice(0, 200) };
    });

    const expectCells = u.geo.length;
    const ok = probe.cells === expectCells && probe.colored > 0 && probe.canvases > 0 && errs.length === 0;
    if (!ok) bad++;
    console.log(`${ok ? 'PASS' : 'FAIL'} ${u.id.padEnd(4)} switch=${clicked} cells=${probe.cells}/${expectCells} colored=${probe.colored} canvas=${probe.canvases} arrays=${u.arrays.length} err=${errs.length}`);
    if (errs.length) errs.slice(0, 3).forEach(e => console.log('        ' + e.slice(0, 160)));
    await page.screenshot({ path: `${OUT}/${u.id}.png` });
    await page.close();
  }
  await browser.close();
  console.log(bad ? `\n${bad} participant(s) failed` : '\nall participants OK');
  process.exit(bad ? 1 : 0);
})();
