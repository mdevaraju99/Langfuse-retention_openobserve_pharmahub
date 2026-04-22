"""
PDF text extraction with PyMuPDF for better layout and optional table blocks.
Falls back to pypdf if PyMuPDF fails.
"""
from __future__ import annotations

import io
import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from pypdf import PdfReader


def _safe_slug(name: str) -> str:
    base = Path(name or "document").stem
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return clean or "document"


def _table_markdowns_from_page(page) -> List[str]:
    out: List[str] = []
    try:
        finder = page.find_tables()
        tables = getattr(finder, "tables", finder)
        if not isinstance(tables, (list, tuple)):
            try:
                tables = list(tables)
            except Exception:
                tables = []
        for tab in tables:
            try:
                md = tab.to_markdown()
                if md and md.strip():
                    out.append(md.strip())
            except Exception:
                continue
    except Exception:
        pass
    return out


def _tables_from_page(page) -> Tuple[str, int]:
    """Best-effort table extraction (PyMuPDF 1.23+). Returns markdown-ish text + count."""
    parts: List[str] = []
    count = 0
    for md in _table_markdowns_from_page(page):
        parts.append("\n[TABLE]\n" + md + "\n[/TABLE]\n")
        count += 1
    return "".join(parts), count


def extract_pdf_text_and_tables(
    file,
    max_pages: int,
    max_chars: int,
) -> Tuple[str, int, str, Dict[str, int]]:
    """
    Returns (combined_text, page_count_used, engine_label, metadata).
    Truncates at max_chars with a notice suffix.
    """
    file.seek(0)
    raw = file.read()
    if not raw:
        return "", 0, "empty", {"table_count": 0, "image_count": 0, "formula_like_count": 0, "chart_like_count": 0}

    engine = "pypdf"
    text_parts: List[str] = []
    pages_used = 0
    table_count = 0
    image_count = 0

    try:
        import fitz

        doc = fitz.open(stream=raw, filetype="pdf")
        n = min(doc.page_count, max(1, max_pages))
        pages_used = n
        engine = "pymupdf"

        for i in range(n):
            page = doc.load_page(i)
            body = page.get_text("text") or ""
            tbl, t_count = _tables_from_page(page)
            table_count += t_count
            try:
                image_count += len(page.get_images(full=True) or [])
            except Exception:
                pass
            block = f"\n--- Page {i + 1} ---\n{body.strip()}\n{tbl}"
            text_parts.append(block)
            if sum(len(p) for p in text_parts) >= max_chars:
                break
        doc.close()
    except Exception:
        # Fallback: pypdf
        try:
            buf = io.BytesIO(raw)
            reader = PdfReader(buf)
            n = min(len(reader.pages), max(1, max_pages))
            pages_used = n
            for i in range(n):
                t = reader.pages[i].extract_text() or ""
                text_parts.append(f"\n--- Page {i + 1} ---\n{t}")
                if sum(len(p) for p in text_parts) >= max_chars:
                    break
        except Exception:
            return "", 0, "failed", {"table_count": 0, "image_count": 0, "formula_like_count": 0, "chart_like_count": 0}

    full = "".join(text_parts).strip()
    if len(full) > max_chars:
        full = full[:max_chars] + "\n\n[TRUNCATED: document exceeded configured character limit for ingestion.]"

    # Normalize whitespace for downstream chunking
    full = re.sub(r"\n{4,}", "\n\n\n", full)
    formula_like_count = len(
        re.findall(
            r"([A-Za-z]+\s*=\s*[A-Za-z0-9\+\-\*/\(\)\.]+|[A-Za-z]\([A-Za-z0-9,\s]+\)\s*=)",
            full,
        )
    )
    chart_like_count = len(
        re.findall(r"\b(chart|graph|plot|axis|histogram|scatter|bar chart|line chart|figure)\b", full, flags=re.IGNORECASE)
    )
    metadata = {
        "table_count": int(table_count),
        "image_count": int(image_count),
        "formula_like_count": int(formula_like_count),
        "chart_like_count": int(chart_like_count),
    }
    return full, pages_used, engine, metadata


def extract_pdf_media_assets(
    file,
    filename: str,
    max_pages: int,
    output_dir: str,
    max_images: int = 24,
    max_tables: int = 12,
    max_snippets: int = 12,
) -> Dict:
    """
    Extract and persist rich-media artifacts (tables, images, formula/chart snippets) for UI previews.
    Returns a manifest dict. If extraction fails, returns an empty manifest.
    """
    manifest = {
        "filename": filename,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pages_used": 0,
        "tables": [],
        "images": [],
        "formula_snippets": [],
        "chart_snippets": [],
    }
    file.seek(0)
    raw = file.read()
    if not raw:
        return manifest

    doc_hash = hashlib.md5((filename + str(len(raw))).encode("utf-8")).hexdigest()[:10]
    doc_slug = f"{_safe_slug(filename)}_{doc_hash}"
    base_dir = Path(output_dir) / doc_slug
    image_dir = base_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    try:
        import fitz
    except Exception:
        return manifest

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
        n = min(doc.page_count, max(1, max_pages))
        manifest["pages_used"] = int(n)

        table_total = 0
        image_total = 0
        formula_total = 0
        chart_total = 0

        formula_pattern = re.compile(
            r"([A-Za-z]+\s*=\s*[A-Za-z0-9\+\-\*/\(\)\.]+|[A-Za-z]\([A-Za-z0-9,\s]+\)\s*=)"
        )
        chart_pattern = re.compile(
            r"\b(chart|graph|plot|axis|histogram|scatter|bar chart|line chart|figure)\b",
            flags=re.IGNORECASE,
        )

        for i in range(n):
            page = doc.load_page(i)
            page_no = i + 1
            page_text = page.get_text("text") or ""

            for md in _table_markdowns_from_page(page):
                table_total += 1
                if len(manifest["tables"]) < max_tables:
                    manifest["tables"].append({"page": page_no, "markdown": md})

            try:
                for img in page.get_images(full=True) or []:
                    xref = img[0]
                    image_total += 1
                    if len(manifest["images"]) >= max_images:
                        continue
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n > 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        img_name = f"p{page_no}_img{len(manifest['images']) + 1}.png"
                        img_path = image_dir / img_name
                        pix.save(str(img_path))
                        manifest["images"].append(
                            {
                                "page": page_no,
                                "path": str(img_path),
                                "width": int(pix.width),
                                "height": int(pix.height),
                            }
                        )
                    except Exception:
                        continue
            except Exception:
                pass

            for m in formula_pattern.findall(page_text):
                formula_total += 1
                if len(manifest["formula_snippets"]) < max_snippets:
                    manifest["formula_snippets"].append({"page": page_no, "text": m.strip()[:200]})

            if chart_pattern.search(page_text):
                chart_total += 1
                if len(manifest["chart_snippets"]) < max_snippets:
                    lines = [ln.strip() for ln in page_text.splitlines() if chart_pattern.search(ln)]
                    snippet = " | ".join(lines[:2])[:260] if lines else "Chart/graph reference detected."
                    manifest["chart_snippets"].append({"page": page_no, "text": snippet})

        doc.close()
        manifest["table_count"] = int(table_total)
        manifest["image_count"] = int(image_total)
        manifest["formula_like_count"] = int(formula_total)
        manifest["chart_like_count"] = int(chart_total)

        manifest_path = base_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    except Exception:
        return manifest


def load_media_manifest(filename: str, output_dir: str) -> Dict:
    """
    Load the latest media manifest for a filename from media assets dir.
    """
    slug = _safe_slug(filename)
    root = Path(output_dir)
    if not root.exists():
        return {}
    candidates = sorted(root.glob(f"{slug}_*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return {}
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception:
        return {}


def delete_media_assets(filename: str, output_dir: str) -> None:
    slug = _safe_slug(filename)
    root = Path(output_dir)
    if not root.exists():
        return
    for folder in root.glob(f"{slug}_*"):
        if not folder.is_dir():
            continue
        for p in sorted(folder.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                continue


def clear_media_assets(output_dir: str) -> None:
    root = Path(output_dir)
    if not root.exists():
        return
    for p in sorted(root.rglob("*"), reverse=True):
        try:
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                p.rmdir()
        except Exception:
            continue
