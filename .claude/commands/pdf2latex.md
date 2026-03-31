Convert a local PDF of math/science notes to a LaTeX document using Claude vision OCR.

Input (`$ARGUMENTS`): a local PDF path. For BOOX notes or Drive files, run `/boox-prep` first.

---

## Step 0 — Check and install dependencies

```bash
pip_install() { pip install "$1" -q 2>/dev/null || pip install "$1" -q --break-system-packages 2>/dev/null || pip3 install "$1" -q; }
python3 -c "import fitz" 2>/dev/null || pip_install pymupdf
which pdflatex >/dev/null 2>&1 || echo "WARNING: pdflatex not found — install texlive to compile output"
echo "Dependencies OK"
```

---

## Step 1 — Render pages to images

```python
import fitz, pathlib
out = pathlib.Path('/tmp/pdf2latex_pages')
out.mkdir(parents=True, exist_ok=True)
for f in out.glob('*.png'): f.unlink()
doc = fitz.open('$ARGUMENTS')
print(f'Total pages: {len(doc)}')
for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), colorspace=fitz.csRGB)
    pix.save(str(out / f'page_{i+1:03d}.png'))
    print(f'  Rendered page {i+1}/{len(doc)}')
doc.close()
```

---

## Step 2 — Read every page image

Use the Read tool on `/tmp/pdf2latex_pages/page_001.png`, `page_002.png`, ... up to the last page. Read in batches of 4 in parallel.

---

## Step 3 — Transcribe to LaTeX

For each page, transcribe ALL content:

- **Math**: inline `$...$`, display `\[...\]`, multi-line `align`, `cases`, `gather`, etc.
- **Structure**: `\section`, `\subsection`, `\begin{definition}`, `\begin{theorem}`, `\begin{proof}`, `itemize`, `enumerate`.
- **Diagrams with clear geometry**: TikZ inside `\begin{center}\begin{tikzpicture}...\end{tikzpicture}\end{center}`. Pre-compute trig values — never use `cos(\a)` directly in coordinates.
- **Complex/decorative diagrams**: leave `% [diagram: brief description]`.
- **Non-English annotations**: translate in square brackets.
- Infer `\section` structure from content if headings aren't explicit.

---

## Step 4 — Write the .tex file

Output path: same directory and stem as `$ARGUMENTS` with `_latex.tex` suffix
(e.g. `notes.pdf` → `notes_latex.tex`).

Preamble:

```latex
\documentclass[12pt,a4paper]{article}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{mathtools}
\usepackage{tikz}
\usetikzlibrary{arrows.meta, calc, decorations.markings}
\geometry{margin=2.5cm}
\newtheorem{theorem}{Theorem}[section]
\newtheorem{definition}[theorem]{Definition}
\newtheorem{example}[theorem]{Example}
\newcommand{\R}{\mathbb{R}}
\title{Transcribed Notes}
\date{}
\begin{document}
\maketitle
\tableofcontents
\newpage
```

End with `\end{document}`.

---

## Step 5 — Compile and verify

Only run this step if `pdflatex` is available (check from Step 0).

```bash
pdflatex -interaction=nonstopmode output.tex
pdflatex -interaction=nonstopmode output.tex   # second pass for ToC
grep "^!" output.log || echo "No LaTeX errors"
```

Fix any errors and recompile. Common fixes:
- Unescaped `%`, `&`, `_` outside math → escape them
- TikZ arithmetic in coordinates → pre-compute the numbers
- Unicode characters → replace with LaTeX equivalents

---

## Step 6 — Report

Input PDF, pages processed, output `.tex` path, output `.pdf` path (if compiled), any errors.
