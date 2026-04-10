"""
Hybrid Extractor
----------------
Merges OCRSpace text extraction with Gemini visual analysis to produce
the best possible content extraction for each page.

Merge strategy per content type:
    | Content Type      | Primary Source | Fallback    |
    |-------------------|---------------|-------------|
    | Plain text        | OCRSpace      | Gemini      |
    | Missing/complex   | Gemini        | OCRSpace    |
    | Diagrams          | Gemini only   | —           |
    | Graphs            | Gemini only   | —           |
    | Numericals        | OCR + Gemini  | Either      |
    | Theorems          | OCR + Gemini  | Either      |
"""

import os
import sys

from .gemini_client import log
from .gemini_output_cleaner import clean_gemini_artifacts


def merge_page_results(ocr_text, classification_result, page_number=1):
    """
    Merge OCRSpace text and Gemini classification for a single page.

    Args:
        ocr_text (str): Plain text extracted by OCRSpace.
        classification_result (dict): Output from content_classifier.classify_page_content().
            Expected: { "page_number": int, "content_blocks": [...] }
        page_number (int): Page number.

    Returns:
        dict: Merged result with both raw text and enriched content blocks.
        {
            "page_number": int,
            "ocr_text": str,
            "merged_text": str,          # Best available text
            "content_blocks": [...],      # Classified and enriched blocks
            "has_visual_content": bool,   # True if diagrams/graphs detected
            "extraction_sources": [...]   # Which sources contributed
        }
    """
    content_blocks = classification_result.get("content_blocks", [])
    sources = []

    # --------------- Determine text sources ---------------
    has_ocr = bool(ocr_text and ocr_text.strip())
    has_gemini = bool(content_blocks)

    if has_ocr:
        sources.append("ocrspace")
    if has_gemini:
        sources.append("gemini")

    # --------------- Build merged text ---------------
    merged_text = _build_merged_text(ocr_text, content_blocks)
    # Clean Gemini artifacts (remove pollution tags) before further processing
    merged_text = clean_gemini_artifacts(merged_text)

    # --------------- Enrich content blocks ---------------
    enriched_blocks = _enrich_blocks(ocr_text, content_blocks)

    # --------------- Check for visual content ---------------
    visual_types = {"diagram", "graph"}
    has_visual = any(b.get("type") in visual_types for b in enriched_blocks)

    log(f"Page {page_number}: merged from {', '.join(sources)} — "
        f"{len(enriched_blocks)} blocks, visual={has_visual}")

    return {
        "page_number": page_number,
        "ocr_text": ocr_text or "",
        "merged_text": merged_text,
        "content_blocks": enriched_blocks,
        "has_visual_content": has_visual,
        "extraction_sources": sources
    }


def _build_merged_text(ocr_text, content_blocks):
    """
    Build the best possible text representation by combining OCR and Gemini.
    - For text blocks: prefer OCR (better for handwriting) unless OCR is empty
    - For visual blocks: use Gemini's extracted_data
    - For numericals/theorems: combine both sources
    """
    parts = []

    # Start with OCR text as the base (it's usually the most complete for text)
    if ocr_text and ocr_text.strip():
        parts.append(ocr_text.strip())

    # Add Gemini's extracted data for non-text content (diagrams, graphs, etc.)
    for block in content_blocks:
        block_type = block.get("type", "text")
        extracted = block.get("extracted_data", "").strip()

        if block_type in ("diagram", "graph"):
            # Visual content: only Gemini can extract this
            if extracted:
                parts.append(f"\n[{block_type.upper()}]: {block.get('description', '')}")
                parts.append(extracted)

        elif block_type in ("numerical", "theorem"):
            # For numericals/theorems: append Gemini's analysis if it adds info
            if extracted and ocr_text and extracted not in ocr_text:
                parts.append(f"\n[{block_type.upper()} - AI Analysis]: {extracted}")

    # If OCR was empty but Gemini found text, use Gemini's text
    if not ocr_text or not ocr_text.strip():
        for block in content_blocks:
            if block.get("type") == "text":
                extracted = block.get("extracted_data", "").strip()
                if extracted:
                    parts.append(extracted)

    return "\n".join(parts) if parts else ""


def _enrich_blocks(ocr_text, content_blocks):
    """
    Enrich content blocks with source information and OCR fallback data.
    """
    enriched = []

    for block in content_blocks:
        block_type = block.get("type", "text")
        enriched_block = {
            "type": block_type,
            "description": block.get("description", ""),
            "extracted_data": block.get("extracted_data", ""),
            "source": _determine_source(block_type, ocr_text)
        }

        # For text blocks, prefer OCR if available
        if block_type == "text" and ocr_text and ocr_text.strip():
            enriched_block["ocr_text"] = ocr_text
            enriched_block["source"] = "ocrspace"

        # For visual-only content, source is always Gemini
        elif block_type in ("diagram", "graph"):
            enriched_block["source"] = "gemini"

        # For numericals/theorems, mark as hybrid if both available
        elif block_type in ("numerical", "theorem") and ocr_text:
            enriched_block["ocr_text"] = ocr_text
            enriched_block["source"] = "hybrid"

        enriched.append(enriched_block)

    # If no content blocks from Gemini but OCR has text, create a text block
    if not enriched and ocr_text and ocr_text.strip():
        enriched.append({
            "type": "text",
            "description": "Text extracted by OCR (no Gemini classification available)",
            "extracted_data": ocr_text,
            "source": "ocrspace"
        })

    return enriched


def _determine_source(content_type, ocr_text):
    """Determine the primary extraction source based on content type."""
    if content_type in ("diagram", "graph"):
        return "gemini"
    elif content_type in ("numerical", "theorem"):
        return "hybrid" if ocr_text else "gemini"
    else:
        return "ocrspace" if ocr_text else "gemini"


def merge_all_pages(page_results):
    """
    Combine merged results from all pages into a single document-level result.

    Args:
        page_results (list): List of per-page merge results.

    Returns:
        dict: Document-level merged content.
    """
    all_text_parts = []
    all_content_blocks = []
    all_sources = set()
    has_any_visual = False

    for page in page_results:
        if page.get("merged_text"):
            all_text_parts.append(page["merged_text"])
        all_content_blocks.extend(page.get("content_blocks", []))
        all_sources.update(page.get("extraction_sources", []))
        if page.get("has_visual_content"):
            has_any_visual = True

    return {
        "full_text": "\n\n".join(all_text_parts),
        "content_blocks": all_content_blocks,
        "extraction_sources": sorted(list(all_sources)),
        "has_visual_content": has_any_visual,
        "total_pages_processed": len(page_results)
    }
