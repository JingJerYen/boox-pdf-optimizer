# boox-pdf-optimizer

Optimize bloated PDFs exported from BOOX e-note devices.

## The Problem

BOOX `.note` to PDF conversion creates one PDF annotation per pen stroke. A 30-page handwritten notebook can balloon to **126 MB** because:

- **24,000+ Stamp annotations** — each stroke is a separate PDF object with its own Form XObject
- **Compression anti-pattern** — thousands of tiny streams compressed individually with FlateDecode actually *expand* the file (worse than no compression)
- **Duplicate images** — identical background images stored separately per page
- **Excessive precision** — 6 decimal places for coordinates when 2 suffice

## Installation

```bash
pip install pikepdf pymupdf Pillow
```

## Quick Start

```bash
# Just run it — default mode is optimize (near-lossless, preserves colors & vectors)
python3 pdfsimpler.py input.pdf

# Specify output path
python3 pdfsimpler.py input.pdf -o output.pdf
```

### Want it even smaller?

```bash
# Aggressive coordinate rounding (still vector, still has color)
python3 pdfsimpler.py input.pdf --precision 1

# Rasterize as images (lossy, but much smaller)
python3 pdfsimpler.py input.pdf --mode rasterize --dpi 150

# Maximum compression: grayscale rasterize (smallest possible, loses color)
python3 pdfsimpler.py input.pdf --mode rasterize --dpi 150 --grayscale
```

## Modes

### `optimize` (default)

Near-lossless. Keeps vector strokes intact, preserves colors (ink colors, highlights, etc.).

What it does:
1. **Flattens annotations** — merges all stroke annotations into page content streams, eliminating tens of thousands of redundant PDF objects
2. **Reduces coordinate precision** — rounds coordinates from 6 to 2 decimal places (configurable via `--precision`)
3. **Merges connected strokes** — consecutive line segments with the same width become a single path
4. **Deduplicates images** — shares identical background images across pages
5. **Removes redundant state** — strips duplicate color/width commands
6. **Re-compresses** — one large stream per page compresses far better than thousands of tiny ones

### `rasterize`

Lossy. Renders each page as a PNG image. Loses vector data but can compress further.

Options:
- `--dpi` — resolution (default: 200, try 150 for smaller files)
- `--grayscale` — render in grayscale instead of RGB (roughly half the size, but loses ink colors)

## Results

Tested on a 32-page differential geometry notebook exported from BOOX Note Air:

| Command | Size | Reduction | Color | Vector |
|---|---|---|---|---|
| Original (BOOX export) | 126 MB | — | Yes | Yes |
| **`python3 pdfsimpler.py input.pdf`** (default) | 29.6 MB | 4.2x | Yes | Yes |
| `--precision 1` | 20 MB | 6.3x | Yes | Yes |
| `--mode rasterize --dpi 150` | 31.4 MB | 4.0x | Yes | No |
| `--mode rasterize --dpi 150 --grayscale` | **17.7 MB** | **7.1x** | No | No |

## Options

| Option | Applies to | Description |
|---|---|---|
| `-o, --output` | both | Output PDF file path (default: `input_optimized.pdf` or `input_rasterized.pdf`) |
| `--mode` | — | `optimize` (default) = flatten annotations, keep vectors; `rasterize` = render as images |
| `--precision` | optimize only | Decimal places for coordinates (default: 2, try 1 for smaller files) |
| `--dpi` | rasterize only | Render resolution (default: 200, try 150 for smaller files) |
| `--grayscale` | rasterize only | Render in grayscale instead of RGB (half the size, loses color) |

## How It Works

BOOX stores each pen stroke as a PDF `/Stamp` annotation with an appearance stream containing individual line segments with per-segment line widths (pressure sensitivity data):

```
/GS gs
0 0 0 RG
1 j 1 J
2.34424 w 225.455 2406.47 m 225.376 2406.65 l S
2.33910 w 225.376 2406.65 m 225.274 2406.96 l S
...
```

This tool flattens all annotations into the page content stream, merges connected segments, and lets FlateDecode compress one large stream instead of thousands of tiny ones.

## Google Drive Automation (Optional)

Automatically optimize BOOX PDFs when they sync to Google Drive — no manual steps after setup.

**How it works:** A Google Apps Script runs on a timer and watches your Drive folder. When it finds a new PDF, it sends it to a Google Cloud Function that downloads, optimizes, and uploads the result back as `filename_optimized.pdf`.

**Cost:** Free. Apps Script and Cloud Functions both have free tiers that this workload stays well within. A Google Cloud account with billing enabled is required (credit card needed to activate, but you won't be charged within free limits).

### Prerequisites

- A [Google Cloud](https://cloud.google.com/free) account with billing enabled
- `gcloud` CLI — install from [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install), then run `gcloud auth login`

> **No local setup needed.** Google Cloud Shell is a free browser-based Linux terminal with `gcloud` and `git` pre-installed.

### Step 1 — Deploy the Cloud Function

Open [Google Cloud Shell](https://shell.cloud.google.com), then run:

```bash
git clone https://github.com/JingJerYen/boox-pdf-optimizer.git
cd boox-pdf-optimizer
./deploy.sh YOUR_GCP_PROJECT_ID
```

The script prints a **Cloud Function URL**, an **Auth Token**, and a **Service Account email** — save all three for the next steps.

### Step 2 — Share your Drive folder with the service account

In Google Drive, right-click your BOOX sync folder → Share → add the Service Account email from Step 1 with **Editor** access.

### Step 3 — Set up Apps Script

1. Go to [script.google.com](https://script.google.com) and create a new project
2. Paste the contents of `apps_script/Code.gs` and save
3. Go to **Project Settings → Script Properties** and add:

| Property | Value |
|---|---|
| `FOLDER_ID` | The ID at the end of your Drive folder URL — the part after `/folders/` and before any `?` |
| `CLOUD_FUNCTION_URL` | The URL from Step 1 |
| `AUTH_TOKEN` | The token from Step 1 |

4. Add a trigger: **Triggers → Add trigger → `watchFolder` → Time-driven → Every 10 minutes**

### Step 4 — Test

Run `watchFolder` manually from the Apps Script editor. The execution log should show:

```
Optimizing: my-notes.pdf
Done: my-notes.pdf → 29.6 MB (4.2x smaller)
```

Then check your Drive folder for `my-notes_optimized.pdf`.

For a detailed explanation of the architecture, permissions model, and troubleshooting, see [CLOUD_SETUP.md](CLOUD_SETUP.md).

## Claude Code Skills (AI-powered OCR)

This repo ships two [Claude Code](https://claude.ai/code) slash commands that turn BOOX notes into LaTeX documents using Claude's vision.

### Prerequisites

1. Install [Claude Code](https://claude.ai/code) (requires a Claude Pro or API subscription):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
2. Log in:
   ```bash
   claude login
   ```
3. Open a terminal **inside this repo directory** — the skills are project-scoped and only activate here.

Python dependencies (`pikepdf`, `pymupdf`, `gdown`) are auto-installed by the skills on first run.

### `/boox-prep` — Prepare a PDF

Downloads from Google Drive (if needed), detects BOOX notes by annotation count, and rasterizes with `pdfsimpler.py`.

```
/boox-prep notes.pdf
/boox-prep https://drive.google.com/file/d/FILE_ID/view
/boox-prep FILE_ID
```

Outputs `notes_prepped.pdf` and tells you to run `/pdf2latex` next.

### `/pdf2latex` — OCR to LaTeX

Takes a clean local PDF, renders each page as an image, uses Claude vision to transcribe all math and text to LaTeX, then compiles to PDF with `pdflatex`.

```
/pdf2latex notes_prepped.pdf
```

Outputs `notes_prepped_latex.tex` and `notes_prepped_latex.pdf`.

### Full pipeline example

```
/boox-prep https://drive.google.com/file/d/FILE_ID/view
/pdf2latex notes_prepped.pdf
```

> **Note:** `/pdf2latex` uses Claude's vision inside your chat session — no extra API cost beyond your subscription. Processing time scales with page count (roughly 10–20 seconds per page).

## License

MIT
