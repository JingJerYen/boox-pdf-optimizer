Prepare a BOOX note PDF for further use. Input (`$ARGUMENTS`) can be:
- A local PDF path: `notes.pdf` or `/path/to/notes.pdf`
- A Google Drive file ID or share URL: `https://drive.google.com/file/d/FILE_ID/view` or just `FILE_ID`

---

## Step 0 — Check and install dependencies

Run this once to ensure all required packages are available:

```bash
pip_install() { pip install "$1" -q 2>/dev/null || pip install "$1" -q --break-system-packages 2>/dev/null || pip3 install "$1" -q; }
python3 -c "import pikepdf" 2>/dev/null || pip_install pikepdf
python3 -c "import fitz"    2>/dev/null || pip_install pymupdf
python3 -c "import gdown"   2>/dev/null || pip_install gdown
echo "Dependencies OK"
```

Also locate `pdfsimpler.py`. Check in order:
1. Same directory as this repo: look for `pdfsimpler.py` via `git rev-parse --show-toplevel`
2. Current working directory
3. Any parent directory up to `/`

```bash
python3 -c "
import subprocess, pathlib, sys

# Try git root first
try:
    root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
                                    stderr=subprocess.DEVNULL).decode().strip()
    candidate = pathlib.Path(root) / 'pdfsimpler.py'
    if candidate.exists():
        print(candidate); sys.exit(0)
except Exception:
    pass

# Walk up from cwd
p = pathlib.Path.cwd()
for _ in range(6):
    c = p / 'pdfsimpler.py'
    if c.exists():
        print(c); sys.exit(0)
    p = p.parent

print('NOT_FOUND')
"
```

If the result is `NOT_FOUND`, tell the user:
> `pdfsimpler.py` was not found. Please run this skill from inside the pdfsimpler repo, or pass the full path manually.
Then stop.

Set `PDFSIMPLER_PATH` to the found path.

---

## Step 1 — Resolve input to a local PDF

**If input contains `drive.google.com` or looks like a Drive file ID** (25–44 alphanumeric chars, no path separators):

Extract the file ID (segment between `/d/` and `/view` or `/edit` in a URL; or the bare argument), then download:

```python
import gdown
file_id = 'FILE_ID_HERE'
out = '/tmp/boox_prep_download.pdf'
gdown.download(id=file_id, output=out, quiet=False)
print('Downloaded to:', out)
```

If `gdown` fails, tell the user the file may be private and stop — do not attempt curl.

Set working path = `/tmp/boox_prep_download.pdf`.

**If input is a local path**, set working path = `$ARGUMENTS`.

---

## Step 2 — Detect if this is a BOOX note

```python
import pikepdf
pdf = pikepdf.open('WORKING_PATH')
total_annots = sum(len(page.get('/Annots', [])) for page in pdf.pages)
pages = len(pdf.pages)
pdf.close()
print(f'Pages: {pages}, Total annotations: {total_annots}')
```

- **`total_annots > 500`**: BOOX note confirmed → continue to Step 3.
- **`total_annots <= 500`**: Not a BOOX note. Tell the user and ask if they still want to rasterize. If yes, continue. If no, stop and report the working path as-is.

---

## Step 3 — Choose processing mode and run pdfsimpler

- **High annotation count, small file per page** → `--mode optimize` (near-lossless, fast)
- **Mixed/image content, or output will be used for OCR** → `--mode rasterize` (default)

```bash
python3 PDFSIMPLER_PATH WORKING_PATH \
    -o OUTPUT_PATH \
    --mode rasterize \
    --dpi 200
```

`OUTPUT_PATH`:
- Local input `foo.pdf` → `foo_prepped.pdf` in the same directory
- Drive input → `/tmp/boox_prep_output.pdf`

---

## Step 4 — Report

- Source (Drive ID or local path)
- Input size
- Output path and size
- Compression ratio
- Mode used
- Next step suggestion: `Run /pdf2latex OUTPUT_PATH to convert to LaTeX.`
