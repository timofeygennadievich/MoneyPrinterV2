# Third-party notices for Yoku Tea Motion Renderer v2

The direct runtime dependencies are pinned in `package.json` and fully resolved
in `package-lock.json`.

| Dependency | Version | License | Use |
| --- | ---: | --- | --- |
| HyperFrames | 0.7.72 | Apache-2.0 | Deterministic HTML/GSAP-to-video renderer |
| @sparticuz/chromium | 149.0.0 | MIT | Local headless Chromium binary distributed through npm |
| GSAP | 3.15.0 | Standard "no charge" license | Seekable motion timeline |

HyperFrames source and license:
<https://github.com/heygen-com/hyperframes>

Sparticuz Chromium source and license:
<https://github.com/Sparticuz/chromium>

GSAP uses its own Standard "no charge" license rather than Apache-2.0 or MIT.
Its use here is limited to producing Yoku Tea marketing videos. Review the
current license before repackaging the renderer as a hosted competing
animation service:
<https://gsap.com/standard-license/>

Chromium itself contains components under multiple open-source licenses. The
Chromium binary and all product/brand/font assets remain local and are not
committed to this repository.

## Security audit note

`npm audit --omit=dev` on 2026-07-26 reports inherited advisories in
`@hono/node-server`, `adm-zip`, and `sharp`/libvips for which the pinned
HyperFrames dependency graph has no compatible patched resolution. Motion
Renderer v2 is restricted to trusted local media, does not expose the Hono
server publicly, does not accept untrusted ZIP files, and is installed with
dependency lifecycle scripts disabled. See `docs/YokuMotionRendererV2.md` for
the full threat model. These advisories must be re-evaluated before operating
the renderer as a network service.
