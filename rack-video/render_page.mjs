/* Generic deterministic page renderer: steps window.seek(t), writes an mp4.
   node render_page.mjs <page.html> <duration_s> <fps> <out.mp4> [w] [h] */

import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const [pageFile, durArg, fpsArg, outArg, wArg, hArg] = process.argv.slice(2);
const duration = Number(durArg ?? 7);
const fps = Number(fpsArg ?? 30);
const width = Number(wArg ?? 1920);
const height = Number(hArg ?? 1080);
const out = path.resolve(outArg ?? "out/page.mp4");

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".glb": "model/gltf-binary",
  ".png": "image/png", ".webm": "video/webm", ".mp4": "video/mp4",
};
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

const rel = path.relative(ROOT, path.resolve(pageFile)).split(path.sep).join("/");
const browser = await launch({ width, height });
const page = await browser.newPage();
page.on("pageerror", (e) => console.error("[pageerror]", e.message));
await page.goto(`http://127.0.0.1:${server.address().port}/${rel}`);
await page.waitForFunction("window.rigReady === true", { timeout: 60000 });

const frames = path.join(path.dirname(out), "frames_page");
fs.rmSync(frames, { recursive: true, force: true });
fs.mkdirSync(frames, { recursive: true });
const n = Math.round(duration * fps);
for (let i = 0; i <= n; i++) {
  await page.evaluate((t) => window.seek(t), i / fps);
  await page.screenshot({ path: path.join(frames, `f${String(i).padStart(5, "0")}.png`) });
}
await browser.close(); server.close();

execFileSync("ffmpeg", [
  "-y", "-framerate", String(fps), "-i", path.join(frames, "f%05d.png"),
  "-c:v", "libx264", "-preset", "slow", "-crf", "17",
  "-pix_fmt", "yuv420p", "-movflags", "+faststart", out,
], { stdio: ["ignore", "ignore", "inherit"] });
fs.rmSync(frames, { recursive: true, force: true });
console.log(out);
