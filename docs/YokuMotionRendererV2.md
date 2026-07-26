# Yoku Tea Motion Renderer v2

Motion Renderer v2 is the local, deterministic production path for Yoku Tea
product videos. It builds platform-specific motion compositions from a trusted
product card and an approved layered asset pack, renders them through
HyperFrames/GSAP/Chromium, normalizes the masters with FFmpeg, and creates QA
proofs. It never publishes or uploads a video.

## Output profiles

| Profile | Duration | Video | Audio | Purpose |
| --- | ---: | --- | --- | --- |
| `ozon` | 10.5 s | 1080×1920, 30 fps, H.264 | none | Silent marketplace product card |
| `reels` | 15.0 s | 1080×1920, 30 fps, H.264 | original local SFX | Instagram Reels master |
| `shorts` | 18.0 s | 1080×1920, 30 fps, H.264 | original local SFX | YouTube Shorts master |

The three profiles use separate scene timing and safe zones from
`data/motion/platforms.json`. They share the same five-beat story:

1. appetizing drink hook;
2. exact product packshot;
3. powder → drink → ice and topping transformation;
4. catalog-backed facts;
5. product, drink, and positioning end card.

## Safety contract

- Product facts come from `data/products/<product_id>.json`.
- Claims Guard runs before any project or MP4 is created.
- Every image role must be `approved=true`, product-scoped, and SHA-256
  verified in a local motion manifest.
- The HTML composition has no remote media, CDN, model, or API dependency.
- The pack label and logo are approved pixels; they are never regenerated.
- Ozon has no direct purchase imperative and no audio.
- `auto_publish` and `external_uploads` remain `false`.
- Technical QA does not replace the final visual inspection.

Private images, brand fonts, extracted Chromium, renders, and audio stay in
ignored local directories. Only manifests, crop recipes, templates, code, and
tests are versioned.

## Install

Python 3.12, Node.js 22 or newer, FFmpeg, and FFprobe are required.

Install the exact JavaScript dependency graph:

```bash
npm ci --ignore-scripts --no-fund
```

`--ignore-scripts` intentionally prevents the optional HyperFrames
`onnxruntime-node` lifecycle download. Motion Renderer v2 does not use that
optional runtime. HyperFrames, GSAP, and Chromium versions are pinned in
`package.json` and `package-lock.json`; licenses are recorded in
`THIRD_PARTY_NOTICES.md`.

### Transitive dependency audit

As of 2026-07-26, `npm audit --omit=dev` reports one moderate and four high
advisories inherited from HyperFrames (`@hono/node-server`, `adm-zip`, and
`sharp`/libvips). The pinned HyperFrames release has no compatible patched
dependency graph available through `npm audit fix`.

The renderer therefore applies a deliberately narrow threat model:

- run only on Linux as a local CLI;
- bind no public server;
- keep telemetry and network media disabled;
- accept only owner-approved, hash-verified local images and MP4 files;
- never process an untrusted ZIP;
- install with `--ignore-scripts`, so the unused `onnxruntime-node` lifecycle
  download does not execute.

Do not expose this renderer as a hosted service or feed it untrusted media until
the upstream advisories have patched releases. Re-run `npm audit --omit=dev`
when upgrading HyperFrames.

If the supplied brandbook contains embedded NT Somic subsets, restore their
browser-readable Unicode maps locally:

```bash
python scripts/extract_yoku_brand_fonts.py \
  /path/to/YokuTea_Brand-Guideline.pdf \
  --output-dir assets/yoku/brand
```

The extracted fonts are not committed.

## Prepare the approved Taro 100 g layers

The checked-in recipe identifies exact crops in the approved pilot and does not
use a generative image service:

```bash
python src/yoku_main.py render-campaign \
  --product taro-100g \
  --platforms ozon,reels,shorts \
  --reference-video /path/to/approved-taro-100g-pilot.mp4 \
  --prepare-from-reference \
  --overwrite-motion-assets \
  --dry-run
```

The local asset pack is written to
`assets/yoku/products/taro-100g/motion-v2/` and includes `logo`, `drink`,
`packshot`, `powder`, and `toppings` plus a hash manifest.

## Render all masters

After reviewing the dry-run projects:

```bash
python src/yoku_main.py render-campaign \
  --product taro-100g \
  --platforms ozon,reels,shorts \
  --motion-assets-root assets/yoku/products/taro-100g/motion-v2
```

The campaign directory contains:

```text
taro-100g-ozon.mp4
taro-100g-instagram-reels.mp4
taro-100g-youtube-shorts.mp4
campaign-report.json
campaign-report.md
claims-report.json
run-metadata.json
qa/<platform>/*-cover.png
qa/<platform>/*-contact-sheet.jpg
qa/<platform>/*-qa.json
qa/<platform>/*-qa.md
projects/<platform>/...
logs/<platform>/...
```

Each encoded master is checked for dimensions, duration, frame rate, frame
count, H.264, `yuv420p`, expected audio presence, decode errors, and black
frames. Covers and ten-frame contact sheets are generated from the normalized
MP4 rather than from the HTML preview.

## Tests

```bash
python -m compileall src
python -m unittest -v tests.test_motion_renderer_v2
python -m unittest discover -s tests -v
```

HyperFrames performs browser/runtime/layout/motion/contrast verification before
each high-quality render. Its full diagnostics are preserved under `logs/`.

## Adding another SKU

Do not reuse Taro pixels for another product. Add:

1. a validated product card;
2. an approved motion asset pack or an explicit extraction recipe;
3. a matching hash manifest;
4. visual QA notes for packaging, drink, masks, text, and safe zones.

The reusable renderer and platform profiles need no code change when those
inputs follow the same contract.
