/* Shared headless-Chromium launcher for the rack video pipeline. */

import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer-core";

const CHROME = path.join(
  os.homedir(),
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64",
  "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);

export async function launch({ width, height, deviceScaleFactor = 1 }) {
  return puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: [
      `--window-size=${width},${height}`,
      "--hide-scrollbars",
      "--force-color-profile=srgb",
      "--disable-lcd-text",
    ],
    defaultViewport: { width, height, deviceScaleFactor },
  });
}
