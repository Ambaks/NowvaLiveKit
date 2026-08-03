/* Debug stills: fixed azimuths with doors open, to locate the true front. */

import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "rack-video", "out");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".glb": "model/gltf-binary" };

const server = await new Promise((resolve) => {
  const s = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(req.url.split("?")[0]));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end(); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  s.listen(0, () => resolve(s));
});

const browser = await launch({ width: 960, height: 540 });
const page = await browser.newPage();
page.on("pageerror", (e) => console.error("[pageerror]", e.message));
await page.goto(`http://127.0.0.1:${server.address().port}/rack-video/film.html`);
await page.waitForFunction("window.rigReady === true", { timeout: 60000 });

const t = Number(process.argv[2] ?? 13);
for (const az of [0, 90, 180, 270]) {
  const info = await page.evaluate(
    ({ az, t }) => window.debugOrbit(az, t), { az, t });
  await page.screenshot({ path: path.join(OUT, `az${az}_t${t}.png`) });
  if (az === 0) console.log("screen normal:", info.screenNormal, "frontAz:", info.frontAz);
}
console.log("done");
await browser.close(); server.close();
