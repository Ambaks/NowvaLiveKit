/* WebGL smoke test: verify headless Chromium gives us a GPU context. */

import { launch } from "./browser.mjs";

const browser = await launch({ width: 640, height: 400 });
const page = await browser.newPage();
const info = await page.evaluate(() => {
  const canvas = document.createElement("canvas");
  const gl = canvas.getContext("webgl2");
  if (!gl) return { ok: false };
  const dbg = gl.getExtension("WEBGL_debug_renderer_info");
  return {
    ok: true,
    renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "masked",
    maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
  };
});
console.log(JSON.stringify(info));
await browser.close();
