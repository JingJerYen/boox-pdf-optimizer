#!/usr/bin/env python3
"""
pdfsimpler - Optimize bloated BOOX .note-converted PDFs.

BOOX e-note exports create one PDF annotation per pen stroke, resulting in
tens of thousands of tiny Form XObjects that compress poorly. This tool
fixes that with two modes:

  optimize   (default) — flatten annotations into page content, reduce
                         coordinate precision, deduplicate images.
                         Near-lossless, typically 5-15× smaller.

  rasterize  — render each page as a high-quality image.
               Lossy but maximum compression, typically 15-40× smaller.

Usage:
    python3 pdfsimpler.py input.pdf [-o output.pdf] [--mode optimize|rasterize]
                                    [--dpi 200] [--quality 85] [--precision 2]
"""

import argparse
import hashlib
import io
import re
import sys
from pathlib import Path


def round_pdf_numbers(content: bytes, precision: int = 2) -> bytes:
    """Round floating-point numbers in PDF content stream to given precision."""
    def _round_match(m: re.Match) -> bytes:
        val = float(m.group(0))
        rounded = round(val, precision)
        if rounded == int(rounded):
            return str(int(rounded)).encode()
        return f"{rounded:.{precision}f}".rstrip("0").rstrip(".").encode()

    return re.sub(rb"-?\d+\.\d{3,}", _round_match, content)


# Pattern: "W x1 y1 m x2 y2 l S"
_SEGMENT_RE = re.compile(
    rb"([\d.]+)\s+w\s+"
    rb"(-?[\d.]+)\s+(-?[\d.]+)\s+m\s+"
    rb"(-?[\d.]+)\s+(-?[\d.]+)\s+l\s+S"
)


def merge_strokes(content: bytes) -> bytes:
    """Merge consecutive line segments with same width and connected endpoints into paths.

    Turns:
        2.34 w 225.46 2406.47 m 225.38 2406.65 l S
        2.34 w 225.38 2406.65 m 225.27 2406.96 l S
    Into:
        2.34 w 225.46 2406.47 m 225.38 2406.65 l 225.27 2406.96 l S
    """
    lines = content.split(b"\n")
    output = []
    # Current path state
    cur_width = None
    cur_start = None  # (x, y) of moveto
    cur_end = None    # (x, y) of last lineto
    path_parts = []   # list of "x y l" parts after the moveto

    def flush_path():
        nonlocal cur_width, cur_start, cur_end, path_parts
        if cur_width is not None and cur_start is not None:
            line = f"{cur_width} w {cur_start[0]} {cur_start[1]} m"
            for part in path_parts:
                line += f" {part}"
            line += " S"
            output.append(line.encode())
        cur_width = None
        cur_start = None
        cur_end = None
        path_parts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = _SEGMENT_RE.fullmatch(line)
        if m:
            w = m.group(1).decode()
            x1, y1 = m.group(2).decode(), m.group(3).decode()
            x2, y2 = m.group(4).decode(), m.group(5).decode()

            # Can extend current path if same width and start == previous end
            if (cur_width == w and cur_end is not None
                    and cur_end[0] == x1 and cur_end[1] == y1):
                path_parts.append(f"{x2} {y2} l")
                cur_end = (x2, y2)
            else:
                flush_path()
                cur_width = w
                cur_start = (x1, y1)
                cur_end = (x2, y2)
                path_parts = [f"{x2} {y2} l"]
        else:
            flush_path()
            output.append(line)

    flush_path()

    # Second pass: skip redundant width and color commands
    result = []
    prev_w = None
    prev_color = None
    w_pattern = re.compile(rb"^([\d.]+) w (.+)$")
    color_pattern = re.compile(rb"^[\d.]+ [\d.]+ [\d.]+ R[Gg]$")
    for line in output:
        # Skip duplicate color commands
        cm = color_pattern.match(line)
        if cm:
            if line == prev_color:
                continue
            prev_color = line
            result.append(line)
            continue
        # Skip duplicate width commands
        m2 = w_pattern.match(line)
        if m2:
            w_val = m2.group(1)
            rest = m2.group(2)
            if w_val == prev_w:
                result.append(rest)
            else:
                result.append(line)
                prev_w = w_val
        else:
            result.append(line)

    return b"\n".join(result)


def optimize(input_path: str, output_path: str, precision: int = 2) -> None:
    """Flatten annotations and optimize vector content."""
    import pikepdf

    print(f"Opening {input_path} ...")
    pdf = pikepdf.open(input_path)
    total_pages = len(pdf.pages)

    for pg_idx in range(total_pages):
        page = pdf.pages[pg_idx]
        annots = page.get("/Annots")
        if not annots:
            print(f"  Page {pg_idx + 1}/{total_pages}: no annotations, skipping")
            continue

        num_annots = len(annots)
        print(f"  Page {pg_idx + 1}/{total_pages}: flattening {num_annots} annotations ...")

        # Collect all annotation appearance stream content
        stroke_lines = bytearray()

        # Gather resources we need to carry over (ExtGState, etc.)
        page_res = page.get("/Resources", pikepdf.Dictionary())
        if "/ExtGState" not in page_res:
            page_res["/ExtGState"] = pikepdf.Dictionary()

        # Strip only the gs and join/cap header (shared across all annotations),
        # but KEEP the color (RG/rg) since it varies per annotation.
        gs_header_pattern = re.compile(
            rb"^/(\w+)\s+gs\s*\n"         # graphics state — capture name
        )
        joincap_pattern = re.compile(
            rb"^\d+\s+j\s+\d+\s+J\s*\n",  # line join/cap
            re.MULTILINE,
        )
        gs_names_needed = set()

        for annot_ref in annots:
            try:
                annot = annot_ref
                if not isinstance(annot, pikepdf.Dictionary):
                    annot = pdf.get_object(annot_ref.objgen)

                ap = annot.get("/AP")
                if not ap:
                    continue
                normal = ap.get("/N")
                if not normal or not isinstance(normal, pikepdf.Stream):
                    continue

                stream_data = normal.read_bytes()
                if not stream_data:
                    continue

                # Copy over any ExtGState resources from the form
                form_res = normal.get("/Resources", pikepdf.Dictionary())
                form_gs = form_res.get("/ExtGState", pikepdf.Dictionary())
                for gs_name, gs_ref in form_gs.items():
                    page_res["/ExtGState"][gs_name] = gs_ref
                    gs_names_needed.add(str(gs_name).lstrip("/"))

                # Strip only gs and join/cap, keep color commands
                stripped = gs_header_pattern.sub(b"", stream_data)
                stripped = joincap_pattern.sub(b"", stripped).strip()
                if stripped:
                    stroke_lines += stripped
                    stroke_lines += b"\n"

            except Exception as e:
                print(f"    Warning: skipped annotation: {e}")
                continue

        # Build merged content with shared header (gs + join/cap only)
        merged_content = bytearray()
        merged_content += b"q\n"
        if gs_names_needed:
            gs_name = next(iter(gs_names_needed))
            merged_content += f"/{gs_name} gs\n".encode()
        merged_content += b"1 j 1 J\n"
        merged_content += stroke_lines
        merged_content += b"Q\n"

        # Round coordinates for precision reduction
        if precision < 6:
            merged_content = round_pdf_numbers(bytes(merged_content), precision)
        else:
            merged_content = bytes(merged_content)

        # Merge consecutive connected line segments into paths
        merged_content = merge_strokes(merged_content)

        # Get existing page content
        existing_content = b""
        if "/Contents" in page:
            contents = page["/Contents"]
            if isinstance(contents, pikepdf.Stream):
                existing_content = contents.read_bytes()
            elif isinstance(contents, pikepdf.Array):
                parts = []
                for c in contents:
                    if isinstance(c, pikepdf.Stream):
                        parts.append(c.read_bytes())
                    else:
                        obj = pdf.get_object(c.objgen)
                        parts.append(obj.read_bytes())
                existing_content = b"\n".join(parts)

        # Combine: existing content (background image) + annotation strokes
        final_content = existing_content + b"\n" + merged_content

        # Replace page content with single merged stream
        page["/Contents"] = pdf.make_stream(final_content)
        page["/Resources"] = page_res

        # Remove annotations
        del page["/Annots"]

    # Deduplicate images
    print("  Deduplicating images ...")
    image_map = {}  # hash -> first object
    dedup_count = 0
    for pg_idx in range(total_pages):
        page = pdf.pages[pg_idx]
        xobjs = page.get("/Resources", {}).get("/XObject", {})
        for name in list(xobjs.keys()):
            obj = xobjs[name]
            if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name("/Image"):
                raw = obj.read_raw_bytes()
                h = hashlib.md5(raw).hexdigest()
                if h in image_map:
                    xobjs[name] = image_map[h]
                    dedup_count += 1
                else:
                    image_map[h] = obj

    if dedup_count:
        print(f"    Deduplicated {dedup_count} images ({len(image_map)} unique)")

    # Clean up orphaned objects and save
    print(f"  Saving to {output_path} ...")
    pdf.remove_unreferenced_resources()
    pdf.save(output_path, linearize=True, compress_streams=True,
             stream_decode_level=pikepdf.StreamDecodeLevel.all)
    pdf.close()

    in_size = Path(input_path).stat().st_size
    out_size = Path(output_path).stat().st_size
    ratio = in_size / out_size if out_size else 0
    print(f"\n  Done!  {in_size / 1024 / 1024:.1f} MB → {out_size / 1024 / 1024:.1f} MB  ({ratio:.1f}× smaller)")


def rasterize(input_path: str, output_path: str, dpi: int = 200, quality: int = 85) -> None:
    """Render each page as an image and build a new PDF."""
    import fitz  # PyMuPDF
    from PIL import Image

    print(f"Opening {input_path} ...")
    doc = fitz.open(input_path)
    total_pages = len(doc)

    # Create output PDF
    out_doc = fitz.open()

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for pg_idx in range(total_pages):
        print(f"  Page {pg_idx + 1}/{total_pages}: rendering at {dpi} DPI ...")
        page = doc[pg_idx]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)

        # Convert to PIL for better compression control
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)

        # For mostly-white pages with dark strokes, PNG compresses better than JPEG
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        img_data = buf.getvalue()

        # Create new page with same dimensions
        rect = page.rect
        new_page = out_doc.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=img_data)

    print(f"  Saving to {output_path} ...")
    out_doc.save(output_path, deflate=True, garbage=4)
    out_doc.close()
    doc.close()

    in_size = Path(input_path).stat().st_size
    out_size = Path(output_path).stat().st_size
    ratio = in_size / out_size if out_size else 0
    print(f"\n  Done!  {in_size / 1024 / 1024:.1f} MB → {out_size / 1024 / 1024:.1f} MB  ({ratio:.1f}× smaller)")


def main():
    parser = argparse.ArgumentParser(
        description="Optimize bloated BOOX-exported PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("-o", "--output", help="Output PDF file (default: input_optimized.pdf)")
    parser.add_argument(
        "--mode", choices=["optimize", "rasterize"], default="optimize",
        help="optimize = flatten annotations (near-lossless); rasterize = render as images (lossy)"
    )
    parser.add_argument("--dpi", type=int, default=200, help="DPI for rasterize mode (default: 200)")
    parser.add_argument("--quality", type=int, default=85, help="JPEG quality for rasterize mode (default: 85)")
    parser.add_argument("--precision", type=int, default=2, help="Decimal precision for coordinates in optimize mode (default: 2)")

    args = parser.parse_args()

    input_path = args.input
    if not Path(input_path).exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        p = Path(input_path)
        suffix = "optimized" if args.mode == "optimize" else "rasterized"
        output_path = str(p.with_stem(f"{p.stem}_{suffix}"))

    if args.mode == "optimize":
        optimize(input_path, output_path, precision=args.precision)
    else:
        rasterize(input_path, output_path, dpi=args.dpi, quality=args.quality)


if __name__ == "__main__":
    main()
