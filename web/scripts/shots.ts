/** Screenshots every page at desktop and phone width, plus the downloaded PNG, into ./shots. Needs `npm run preview` running. */

import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, type Browser, type Page } from "@playwright/test";

const OUT = resolve(import.meta.dirname, "../shots");
const BASE = process.env.SHOT_BASE ?? "http://localhost:4173";

async function settle(page: Page, ms: number): Promise<void> {
  await page.waitForTimeout(ms);
}

async function captureField(page: Page, name: string, day: number): Promise<void> {
  await page.goto(`${BASE}/#/`);
  await settle(page, 600);
  await page.evaluate((d) => {
    const scrub = document.querySelector<HTMLInputElement>(".scrub")!;
    scrub.value = String(d);
    scrub.dispatchEvent(new Event("input", { bubbles: true }));
  }, day);
  await settle(page, 200);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

async function captureTest(page: Page, test: string, name: string, day: number): Promise<void> {
  await page.goto(`${BASE}/#/`);
  await settle(page, 600);
  await page.click(`[data-test="${test}"]`);
  await page.evaluate((d) => {
    const scrub = document.querySelector<HTMLInputElement>(".scrub")!;
    scrub.value = String(d);
    scrub.dispatchEvent(new Event("input", { bubbles: true }));
  }, day);
  await settle(page, 200);
  await page.locator(".field").screenshot({ path: `${OUT}/${name}.png` });
}

async function captureCall(page: Page): Promise<void> {
  await captureField(page, "field-end", 2999);
  await page.click('[data-view="tally"]');
  await page.locator('[data-call="0"]').click();
  await settle(page, 200);
  await page.locator(".field").screenshot({ path: `${OUT}/call-desktop.png` });
}

async function captureCard(page: Page, modelId: string, format: string, name: string): Promise<void> {
  await page.goto(`${BASE}/#/model/${modelId}`);
  await page.waitForSelector(".download");
  await settle(page, 600);
  const download = page.waitForEvent("download");
  await page.click(`.download[data-format="${format}"]`);
  await (await download).saveAs(`${OUT}/${name}.png`);
}

async function run(browser: Browser): Promise<void> {
  const desktop = await (await browser.newContext({ viewport: { width: 1360, height: 900 }, acceptDownloads: true })).newPage();
  const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  const errors: string[] = [];
  for (const page of [desktop, phone]) {
    page.on("pageerror", (error) => errors.push(error.stack ?? String(error)));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
  }
  await captureField(desktop, "field-desktop", 2600);
  await captureField(phone, "field-phone", 2600);
  await captureTest(desktop, "reversal", "reversal-desktop", 2600);
  await captureTest(desktop, "fog", "fog-desktop", 2800);
  await captureCall(desktop);
  await desktop.goto(`${BASE}/#/model/mock-counter`);
  await settle(desktop, 900);
  await desktop.screenshot({ path: `${OUT}/model-desktop.png`, fullPage: true });
  await phone.goto(`${BASE}/#/model/mock-verbalized`);
  await settle(phone, 900);
  await phone.screenshot({ path: `${OUT}/model-phone.png`, fullPage: true });
  await desktop.goto(`${BASE}/#/how`);
  await settle(desktop, 400);
  await desktop.screenshot({ path: `${OUT}/how-desktop.png`, fullPage: true });
  await captureCard(desktop, "mock-counter", "landscape", "card-x");
  await captureCard(desktop, "mock-counter", "portrait", "card-tall");
  const reduced = await (await browser.newContext({ reducedMotion: "reduce" })).newPage();
  await reduced.goto(`${BASE}/#/`);
  await settle(reduced, 500);
  console.log(`reduced motion opens at: ${await reduced.locator(".day-label").textContent()}`);
  await desktop.goto(`${BASE}/#/`);
  await settle(desktop, 1500);
  console.log(`after 1.5s of play: ${await desktop.locator(".day-label").textContent()}`);
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(`phone horizontal overflow: ${overflow}px`);
  console.log(errors.length ? `console errors:\n${errors.join("\n")}` : "no console errors");
}

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
await run(browser);
await browser.close();
