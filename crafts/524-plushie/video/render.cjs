// 使い方: NODE_PATH=$(npm root -g) node render.cjs <出力フォルダ> [fps] [時刻,時刻,...]
const { chromium } = require('playwright');
const { mkdirSync } = require('fs');
const path = require('path');

(async () => {
const [out, fpsArg = '30', timesArg] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const here = __dirname;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium' });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto('file://' + path.join(here, 'scenes.html'));
await page.evaluate(() => document.fonts.ready);
const total = await page.evaluate(() => window.TOTAL);
const fps = Number(fpsArg);
const times = timesArg ? timesArg.split(',').map(Number) : Array.from({ length: Math.round(total * fps) }, (_, i) => i / fps);
for (let i = 0; i < times.length; i++) {
  await page.evaluate(t => render(t), times[i]);
  await page.screenshot({ path: path.join(out, `${String(i).padStart(5, '0')}.png`) });
}
await browser.close();
console.log(`${times.length} frames, ${total}s`);
})();
