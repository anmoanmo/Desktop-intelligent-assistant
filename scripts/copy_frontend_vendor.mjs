import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const vendorDir = join(root, "src", "desktop_assistant", "ui", "vendor");
mkdirSync(vendorDir, { recursive: true });

const candidates = [
  ["node_modules/pixi.js-legacy/dist/browser/pixi-legacy.min.js", "pixi.min.js"],
  ["node_modules/pixi-live2d-display/dist/cubism4.min.js", "pixi-live2d-display.min.js"],
  ["node_modules/@pixi-spine/all-3.8/dist/pixi-spine-3.8.umd.js", "pixi-spine.umd.js"],
];

for (const [source, target] of candidates) {
  const sourcePath = join(root, source);
  if (existsSync(sourcePath)) {
    copyFileSync(sourcePath, join(vendorDir, target));
    console.log(`copied ${target}`);
  } else {
    console.warn(`missing ${source}`);
  }
}

console.warn("live2dcubismcore.min.js must be obtained from the official Live2D Cubism SDK and copied manually.");
