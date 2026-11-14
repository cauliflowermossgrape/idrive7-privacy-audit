// Print the report HTML to an A4 PDF with headless Chromium.
// usage: node tools/pdf.cjs IN.html OUT.pdf
// Needs `npm i playwright` (or playwright-core with a Chromium install).
// PLAYWRIGHT_PATH can point at another playwright-core folder.
const path = require('path');

function load() {
  for (const name of [process.env.PLAYWRIGHT_PATH, 'playwright', 'playwright-core'].filter(Boolean)) {
    try { return require(name); } catch (e) { /* try the next one */ }
  }
  console.error('Playwright not found: run `npm i playwright` or set PLAYWRIGHT_PATH');
  process.exit(1);
}

(async () => {
  const { chromium } = load();
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(process.argv[2]));
  await page.pdf({
    path: process.argv[3], format: 'A4', printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:7pt;color:#777;width:100%;text-align:center">BMW MGU privacy audit · <span class="pageNumber"></span>/<span class="totalPages"></span></div>',
  });
  await browser.close();
})();
