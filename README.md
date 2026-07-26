# MoneyPrinter V2

[![Sponsor](https://readme.cash/i/d3t49gsk71.svg)](https://readme.cash/c/d3t49gsk71)


[![madewithlove](https://img.shields.io/badge/made_with-%E2%9D%A4-red?style=for-the-badge&labelColor=orange)](https://github.com/FujiwaraChoki/MoneyPrinterV2)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-brightgreen?logo=buymeacoffee)](https://www.buymeacoffee.com/fujicodes)
[![GitHub license](https://img.shields.io/github/license/FujiwaraChoki/MoneyPrinterV2?style=for-the-badge)](https://github.com/FujiwaraChoki/MoneyPrinterV2/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/FujiwaraChoki/MoneyPrinterV2?style=for-the-badge)](https://github.com/FujiwaraChoki/MoneyPrinterV2/issues)
[![GitHub stars](https://img.shields.io/github/stars/FujiwaraChoki/MoneyPrinterV2?style=for-the-badge)](https://github.com/FujiwaraChoki/MoneyPrinterV2/stargazers)
[![Discord](https://img.shields.io/discord/1134848537704804432?style=for-the-badge)](https://dsc.gg/fuji-community)

An Application that automates the process of making money online.
MPV2 (MoneyPrinter Version 2) is, as the name suggests, the second version of the MoneyPrinter project. It is a complete rewrite of the original project, with a focus on a wider range of features and a more modular architecture.

> **Note:** MPV2 needs Python 3.12 to function effectively.
> Watch the YouTube video [here](https://youtu.be/wAZ_ZSuIqfk)

## Features

- [x] Twitter Bot (with CRON Jobs => `scheduler`)
- [x] YouTube Shorts Automator (with CRON Jobs => `scheduler`)
- [x] Affiliate Marketing (Amazon + Twitter)
- [x] Find local businesses & cold outreach

## Versions

MoneyPrinter has different versions for multiple languages developed by the community for the community. Here are some known versions:

- Chinese: [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)

If you would like to submit your own version/fork of MoneyPrinter, please open an issue describing the changes you made to the fork.

## Installation

> ⚠️ If you are planning to reach out to scraped businesses per E-Mail, please first install the [Go Programming Language](https://golang.org/).

```bash
git clone https://github.com/FujiwaraChoki/MoneyPrinterV2.git

cd MoneyPrinterV2
# Copy Example Configuration and fill out values in config.json
cp config.example.json config.json

# Create a virtual environment
python -m venv venv

# Activate the virtual environment - Windows
.\venv\Scripts\activate

# Activate the virtual environment - Unix
source venv/bin/activate

# Install the requirements
pip install -r requirements.txt
```

## Usage

```bash
# Run the application
python src/main.py
```

## Documentation

All relevant documents can be found [here](docs/).

## Yoku Tea Video Factory

Yoku Tea Video Factory reads a validated product card and content template,
builds a deterministic Russian-language script, checks its claims, and creates
manual-review packages. Product cards live in `data/products/`, templates in
`data/templates/`, media manifests in `data/media/`, and isolated implementation
modules in `src/yoku/`.

The Yoku workflow does not generate images, invent packaging, call LLMs,
Ollama, external APIs or websites, send messages, or publish content. It
assembles video only from explicitly approved real Yoku Tea assets. The legacy
renderer is silent; Motion Renderer v2 may synthesize deterministic local sound
effects for social masters. Automatic publication remains disabled, and every
result requires manual review.

Run it from the repository root:

```bash
python src/yoku_main.py list-products
python src/yoku_main.py list-templates
python src/yoku_main.py generate --product taro-100g --template ozon-recipe
python src/yoku_main.py generate --product taro-200g --template ozon-recipe
python src/yoku_main.py generate --product thai-tea-200g --template ozon-objection
python src/yoku_main.py generate --product mokko-200g --template social-result
python src/yoku_main.py generate --product honey-melon-200g --template ozon-recipe
```

Available product cards are `taro-100g`, `taro-200g`, `thai-tea-200g`,
`mokko-200g`, and `honey-melon-200g`. Available content templates are
`ozon-recipe`, `ozon-objection`, and `social-result`.

The `generate` command creates a directory containing `brief.json`,
`script.txt`, `claims-report.json`, `metadata.json`, and `review.md`. Generated
packages are ignored by Git.

Run the checks with:

```bash
python -m unittest discover -s tests -v
python -m compileall src
```

Never store secrets or real API keys in Git. Keep local values in `.env`; only
the safe, empty `.env.example` template is versioned. A `PASS` from Claims Guard
does not authorize publication: the review checklist must still be completed by
a person, and `auto_publish` remains `false`.

## Approved asset, storyboard and video workflow

Approved real media stays outside Git and must be placed under:

```text
assets/yoku/products/<product_id>/
```

Each schema-version-2 manifest explicitly marks every asset with
`approved=true` and a safe `source_type`. The current approved final-slide roles
are:

```text
packshot-front.(png|jpg)
drink-hero.(png|jpg)
preparation-01.(png|jpg)
preparation-02.(png|jpg)
product-detail.(png|jpg)
cta-slide.(png|jpg)
```

The exact extension is defined in `data/media/<product_id>.json`. Final Ozon
slides are valid working assets because they were explicitly approved by the
owner; the system does not silently treat arbitrary images as approved.

Use the workflow from the repository root:

```bash
python src/yoku_main.py list-assets --assets-root /path/to/private/assets-root
python src/yoku_main.py validate-assets --product taro-100g --assets-root /path/to/private/assets-root
python src/yoku_main.py validate-assets --product taro-100g --assets-root /path/to/private/assets-root --strict
python src/yoku_main.py storyboard --product taro-100g --template social-result --assets-root /path/to/private/assets-root
python src/yoku_main.py render-video --product taro-100g --template social-result --assets-root /path/to/private/assets-root
```

Normal validation reports missing files but exits successfully. Strict
validation exits with code `1` when required files are missing. Image inspection
records dimensions and aspect ratio without uploading media or calling an
external service.

`storyboard` creates a seven-file draft package with a storyboard, shot list,
voice-over text, draft SRT subtitles, asset report, metadata, and manual review
checklist. `render-video` creates a separate local package with `video.mp4`,
`render-plan.json`, `metadata.json`, and `review.md`. It uses local FFmpeg,
creates no voice-over, uses no network services, and never publishes the result.
Use `--dry-run` to validate the complete render plan without creating MP4.

## Motion Renderer v2 for Ozon, Reels and Shorts

The v2 renderer replaces full-screen slide concatenation with one layered
HTML/GSAP motion composition. It uses separate movement for the approved drink,
packshot, powder, ice/toppings, logo, particles, and typography, then creates
10.5-second Ozon, 15-second Reels, and 18-second Shorts masters.

Install the pinned local renderer and build all three projects:

```bash
npm ci --ignore-scripts --no-fund
python src/yoku_main.py render-campaign \
  --product taro-100g \
  --platforms ozon,reels,shorts \
  --motion-assets-root assets/yoku/products/taro-100g/motion-v2
```

Every final MP4 gets an encoded-file technical report, cover, and ten-frame
contact sheet. Publication remains disabled. Setup, asset preparation, QA, and
licensing details are in
[`docs/YokuMotionRendererV2.md`](docs/YokuMotionRendererV2.md).

## Scripts

For easier usage, there are some scripts in the `scripts` directory that can be used to directly access the core functionality of MPV2 without the need for user interaction.

All scripts need to be run from the root directory of the project, e.g. `bash scripts/upload_video.sh`.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us. Check out [docs/Roadmap.md](docs/Roadmap.md) for a list of features that need to be implemented.

## Code of Conduct

Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details on our code of conduct, and the process for submitting pull requests to us.

## License

MoneyPrinterV2 is licensed under `Affero General Public License v3.0`. See [LICENSE](LICENSE) for more information.

## Acknowledgments

- [KittenTTS](https://github.com/KittenML/KittenTTS)
- [gpt4free](https://github.com/xtekky/gpt4free)

## Disclaimer

This project is for educational purposes only. The author will not be responsible for any misuse of the information provided. All the information on this website is published in good faith and for general information purposes only. The author does not make any warranties about the completeness, reliability, and accuracy of this information. Any action you take upon the information you find on this website (FujiwaraChoki/MoneyPrinterV2) is strictly at your own risk. The author will not be liable for any losses and/or damages in connection with the use of our website.
