/* browsertest.js — assert the built atlas actually works in a browser.
 *
 *   node engine/browsertest.js [path-to-html]
 *
 * Needs playwright-core and the preinstalled Chromium:
 *   npm i playwright-core
 *   PW_CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome node engine/browsertest.js
 *
 * Why this file exists in the repo rather than a scratch directory
 * ---------------------------------------------------------------
 * Through Phase 3 this test lived in a temp dir, passed on every run, and missed
 * three real defects at once: out/atlas_v5.html had no doctype, no <meta charset>
 * and no <meta viewport>. The page mojibaked its 417 non-ASCII characters, rendered
 * in quirks mode, and on a phone laid out at ~980px with every responsive rule
 * inert.
 *
 * The test missed them because of HOW it tested. Passing `viewport: {width:390}`
 * to Playwright sets the layout viewport directly — which is precisely the thing a
 * missing viewport meta stops a real phone from doing. It was asserting against a
 * state the bug made unreachable, and reporting "no horizontal scroll at 390px"
 * about a page that a phone would never lay out that way.
 *
 * So the mobile case now uses isMobile + deviceScaleFactor, which makes Chromium
 * honour (or miss) the viewport meta the way a device does, and SCAFFOLD below
 * asserts the document structure directly rather than inferring it from symptoms.
 * The general rule, which this project keeps relearning: test the mechanism, not
 * only the outcome, or a bug can hold the outcome and the test steady together.
 */

const { chromium } = require('playwright-core');
const path = require('path');

const FILE = process.argv[2] ||
  path.join(__dirname, '..', 'out', 'atlas_v5.html');
const CHROME = process.env.PW_CHROME ||
  '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const VIEWS = ['P', 'C', 'M', 'D', 'S'];

const fails = [];
function check(ok, label, detail) {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? '  ' + detail : ''}`);
  if (!ok) fails.push(label + (detail ? ' — ' + detail : ''));
}

/* Document scaffolding. Every one of these was false before this fix. */
async function scaffold(pg, label) {
  const d = await pg.evaluate(() => ({
    doctype: document.doctype ? document.doctype.name : null,
    compat: document.compatMode,
    charset: document.characterSet,
    viewport: !!document.querySelector('meta[name="viewport"]'),
    lang: document.documentElement.lang,
    // A round-trip check on real content, not just the declaration: if the
    // charset is wrong these arrive as mojibake instead of the real glyphs.
    // textContent, NOT innerText -- innerText returns only what is currently
    // VISIBLE, and on first paint most of this page's em dashes sit inside the
    // lab panes, which are display:none until opened. Whether bytes decoded
    // correctly has nothing to do with whether they are on screen, so asking
    // innerText made a correct page report a charset failure.
    emdash: document.body.textContent.includes('—'),
    arrow: document.body.textContent.includes('→'),
    mojibake: /â€|Ã¢|Ã©|â†/.test(document.body.textContent),
  }));
  check(d.doctype === 'html', `[${label}] doctype`, `got ${d.doctype}`);
  check(d.compat === 'CSS1Compat', `[${label}] standards mode`, `compatMode=${d.compat}`);
  check(d.charset === 'UTF-8', `[${label}] charset`, `got ${d.charset}`);
  check(d.viewport, `[${label}] viewport meta present`);
  check(!!d.lang, `[${label}] html lang`, `got "${d.lang}"`);
  check(d.emdash && d.arrow, `[${label}] non-ASCII survives round-trip`,
        `em dash=${d.emdash} arrow=${d.arrow}`);
  check(!d.mojibake, `[${label}] no mojibake in document text`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const errs = [];

  const cases = [
    { label: 'desktop', ctx: { viewport: { width: 1440, height: 900 } } },
    // isMobile + deviceScaleFactor makes Chromium apply the visual-viewport
    // behaviour a phone has, so a missing viewport meta actually shows up here
    // instead of being papered over by the forced layout width.
    { label: 'phone', ctx: { viewport: { width: 390, height: 844 },
                             deviceScaleFactor: 3, isMobile: true, hasTouch: true } },
  ];

  for (const { label, ctx } of cases) {
    console.log(`\n${label}`);
    const page = await browser.newPage(ctx);
    page.on('console', m => { if (m.type() === 'error') errs.push(`[${label}] ${m.text()}`); });
    page.on('pageerror', e => errs.push(`[${label}] PAGEERROR ${e.message}`));
    await page.goto('file://' + path.resolve(FILE));
    await page.waitForTimeout(1200);

    await scaffold(page, label);

    // The page must never scroll sideways, and on a phone the layout viewport
    // must actually match the device rather than the ~980px fallback.
    const lay = await page.evaluate(() => ({
      inner: window.innerWidth,
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }));
    check(lay.scrollW <= lay.clientW + 1, `[${label}] no horizontal scroll`,
          `scrollW=${lay.scrollW} clientW=${lay.clientW}`);
    if (label === 'phone') {
      check(lay.inner < 500, '[phone] layout viewport is device-width',
            `innerWidth=${lay.inner} (980ish means the viewport meta is missing)`);
      const railHidden = await page.evaluate(() =>
        getComputedStyle(document.getElementById('rail')).display === 'none');
      check(railHidden, '[phone] side rail hidden below 1100px (by design)');
    }

    // All five lab views must render.
    await page.click('#labbtn');
    await page.waitForTimeout(400);
    for (const v of VIEWS) {
      await page.click(`.labtabs button[data-v="${v}"]`);
      await page.waitForTimeout(300);
      const info = await page.evaluate(vv => {
        const el = document.getElementById('lv' + vv);
        return { on: el.classList.contains('on'), len: el.innerHTML.length,
                 rows: el.querySelectorAll('tr').length };
      }, v);
      check(info.on && info.len > 400, `[${label}] lab view ${v}`,
            `${info.len}b ${info.rows} rows`);
    }
    const labScroll = await page.evaluate(() => {
      const l = document.getElementById('lab');
      return l.scrollWidth > l.clientWidth + 1;
    });
    check(!labScroll, `[${label}] lab does not scroll sideways`);
    await page.click('#labx');
    await page.waitForTimeout(250);

    // The systems panel is the one whose fields Phase 3 rewrote, so it is the
    // most likely place for a stale field to surface as "undefined".
    if (label === 'desktop') {
      await page.click('#tS');
      await page.waitForTimeout(250);
      await page.click('.srow[data-s="0"]');
      await page.waitForTimeout(400);
      const sys = await page.evaluate(() => {
        const d = document.getElementById('detail');
        return { open: d.classList.contains('open'),
                 bad: (d.innerText.match(/undefined|NaN|\[object/g) || []).length,
                 rob: d.innerText.includes('ROBUSTNESS'),
                 trig: d.innerText.toLowerCase().includes('verdict') };
      });
      check(sys.open, '[desktop] system panel opens');
      check(sys.bad === 0, '[desktop] no undefined/NaN in system panel', `${sys.bad} found`);
      check(sys.rob, '[desktop] ROBUSTNESS shown (payback lens is gone)');
      check(sys.trig, '[desktop] trigger verdict shown');
    }
    await page.close();
  }

  await browser.close();
  console.log('');
  if (errs.length) {
    console.log('console/page errors:');
    errs.forEach(e => console.log('  ' + e));
  } else {
    console.log('0 console errors, 0 page errors');
  }
  if (fails.length) {
    console.log(`\n${fails.length} FAILED:`);
    fails.forEach(f => console.log('  ' + f));
    process.exit(1);
  }
  console.log('all assertions passed');
})();
