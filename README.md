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

```
positional arguments:
  input                 Input PDF file

options:
  -o, --output OUTPUT   Output PDF file (default: input_optimized.pdf)
  --mode {optimize,rasterize}
                        optimize = flatten annotations (near-lossless)
                        rasterize = render as images (lossy)
  --dpi DPI             DPI for rasterize mode (default: 200)
  --quality QUALITY     JPEG quality for rasterize mode (default: 85)
  --precision PRECISION Decimal precision for coordinates in optimize mode (default: 2)
  --grayscale           Rasterize in grayscale instead of RGB (smaller file, loses color)
```

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

## License

MIT
