#!/usr/bin/env node

import { chmodSync, mkdirSync, renameSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";

const targetDir = resolve(process.argv[2] || "output/.chromium-runtime");
mkdirSync(targetDir, { recursive: true });
process.env.TMPDIR = targetDir;
process.env.XDG_CACHE_HOME = join(targetDir, "xdg-cache");
mkdirSync(process.env.XDG_CACHE_HOME, { recursive: true });

const executable = join(targetDir, "chromium");
const minimumExecutableSize = 180 * 1024 * 1024;
const isUsable = () => {
  try {
    return statSync(executable).size >= minimumExecutableSize;
  } catch {
    return false;
  }
};

const waitForStableExecutable = async () => {
  let previousSize = -1;
  let stableSamples = 0;
  for (let sample = 0; sample < 240; sample += 1) {
    let size = -1;
    try {
      size = statSync(executable).size;
    } catch {
      size = -1;
    }
    if (size === previousSize && size >= minimumExecutableSize) {
      stableSamples += 1;
    } else {
      stableSamples = 0;
    }
    previousSize = size;
    if (stableSamples >= 8) {
      chmodSync(executable, 0o700);
      const probe = spawnSync(executable, ["--version"], {
        encoding: "utf8",
        timeout: 10_000,
      });
      if (probe.status === 0 && /^Chromium\s+\d+/.test(probe.stdout.trim())) {
        return true;
      }
      return false;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
  return false;
};

let browserReady = isUsable() && await waitForStableExecutable();
for (let attempt = 1; attempt <= 3 && !browserReady; attempt += 1) {
  try {
    renameSync(executable, `${executable}.invalid-${Date.now()}-${attempt}`);
  } catch {
    // No existing invalid file to quarantine.
  }
  const require = createRequire(import.meta.url);
  const modulePath = require.resolve("@sparticuz/chromium");
  const packageRoot = dirname(dirname(modulePath));
  const { inflate } = await import("@sparticuz/chromium");
  await inflate(join(packageRoot, "bin", "chromium.br"));
  browserReady = await waitForStableExecutable();
}

if (!browserReady) {
  throw new Error("Chromium extraction produced an incomplete executable.");
}
chmodSync(executable, 0o700);
process.stdout.write(`${executable}\n`);
