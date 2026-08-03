/* Renders film.html deterministically: steps time, screenshots frames,
   assembles an mp4 with ffmpeg. Also a stills mode for framing checks.

   node render.mjs stills 0,4,8,10.5,13,16,18.5   -> out/still_<t>.png
   node render.mjs draft                          -> out/draft.mp4 (720p/30)
   node render.mjs final                          -> out/final.mp4 (1080p/60)
*/

import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "rack-video", "out");
const T_TOTAL = 13.0;

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
  ".glb": "model/gltf-binary", ".png": "image/png", ".mp4": "video/mp4",
  ".json": "application/json", ".webm": "video/webm", ".mov": "video/quicktime",
};

function startServer() {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent(req.url.split("?")[0]);
    const file = path.join(ROOT, url === "/" ? "rack-video/film.html" : url);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end("not found"); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, () => resolve(server)));
}

async function openRig(width, height) {
  const server = await startServer();
  const port = server.address().port;
  const browser = await launch({ width, height });
  const page = await browser.newPage();
  page.on("console", (m) => { if (m.type() === "error") console.error("[page]", m.text()); });
  page.on("pageerror", (e) => console.error("[pageerror]", e.message));
  await page.goto(`http://127.0.0.1:${port}/rack-video/film.html`);
  await page.waitForFunction("window.rigReady === true", { timeout: 60000 });
  const uiVideo = process.env.UI_VIDEO;
  if (uiVideo) await page.evaluate((u) => window.setUiVideo(u), uiVideo);
  return { server, browser, page };
}

const mode = process.argv[2] ?? "stills";
fs.mkdirSync(OUT, { recursive: true });

if (mode === "stills") {
  const times = (process.argv[3] ?? "0,4,8,10.5,13,16,18.5").split(",").map(Number);
  const { server, browser, page } = await openRig(1280, 720);
  for (const t of times) {
    await page.evaluate((tt) => window.seek(tt), t);
    const file = path.join(OUT, `still_${t.toFixed(1)}.png`);
    await page.screenshot({ path: file });
    console.log(file);
  }
  await browser.close(); server.close();
} else {
  const [width, height, fps] = mode === "final" ? [1920, 1080, 60] : [1920, 1080, 30];
  const frames = path.join(OUT, "frames");
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });
  const { server, browser, page } = await openRig(width, height);
  const n = Math.round(T_TOTAL * fps);
  const t0 = Date.now();
  for (let i = 0; i <= n; i++) {
    await page.evaluate((tt) => window.seek(tt), i / fps);
    await page.screenshot({ path: path.join(frames, `f${String(i).padStart(5, "0")}.png`) });
    if (i % (fps * 2) === 0)
      console.log(`frame ${i}/${n} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  await browser.close(); server.close();
  const out = path.join(OUT, `${mode}.mp4`);
  execFileSync("ffmpeg", [
    "-y", "-framerate", String(fps), "-i", path.join(frames, "f%05d.png"),
    "-c:v", "libx264", "-preset", "slow", "-crf", "17",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out,
  ], { stdio: "inherit" });
  console.log(out);
}
