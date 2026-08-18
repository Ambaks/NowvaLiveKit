/* Captures the display UI during the condensed replay into out/setup_cap.webm.
   Spawns the python replay (which owns the display server), attaches a
   headless 16:10 page, and screen-records it until the replay finishes. */

import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const OUT = path.join(HERE, "out");
fs.mkdirSync(OUT, { recursive: true });

const py = spawn(path.join(ROOT, "venv", "bin", "python"),
  [path.join(HERE, "replay_setup.py")], { cwd: ROOT });
py.stderr.on("data", (d) => process.stderr.write(d));

const lines = [];
const waitLine = (want) => new Promise((resolve, reject) => {
  const check = () => lines.some((l) => l.includes(want)) && resolve();
  check();
  py.stdout.on("data", (d) => {
    for (const l of d.toString().split("\n")) if (l.trim()) lines.push(l.trim());
    check();
  });
  py.on("exit", (code) => reject(new Error(`replay exited early (${code})`)));
});

await waitLine("READY");
const browser = await launch({ width: 1920, height: 1200 });
const page = await browser.newPage();
await page.goto("http://localhost:8768", { waitUntil: "networkidle2" })
  .catch(async () => {
    /* port unknown? read it from the server module default */
    throw new Error("could not open display page on :8768 — check DISPLAY_PORT");
  });
const recorder = await page.screencast({ path: path.join(OUT, "setup_cap.webm") });
await waitLine("DONE");
await recorder.stop();
await browser.close();
py.kill("SIGINT");
console.log(path.join(OUT, "setup_cap.webm"));
