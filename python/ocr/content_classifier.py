"""
Content Classifier
------------------
Analyzes a page image using Gemini to detect and classify different types
of content present: text, diagram, graph, numerical solution, theorem.

This enables the hybrid pipeline to apply different extraction and
evaluation strategies per content type.

Output format per page:
{
    "page_number": 1,
    "content_blocks": [
        {
            "type": "text",          # text | diagram | graph | numerical | theorem
            "description": "...",     # what was detected
            "extracted_data": "..."   # any extracted text/details from Gemini
        }
    ]
}
"""

import os
import sys
import json
import re

from .gemini_client import gemini_analyze_image, log


# --------------- Classification Prompt ---------------
CLASSIFICATION_PROMPT = """You are analyzing a page from a student's handwritten answer sheet.

Identify ALL types of content present on this page. For each distinct content block, classify it as one of:
- "text": Regular handwritten text answers
- "diagram": Any drawn diagram, figure, circuit, flowchart, or illustration
- "graph": Any plotted graph, chart, or coordinate-based drawing
- "numerical": Mathematical calculations, equations, step-by-step numerical solutions
- "theorem": Mathematical theorems, proofs, derivations, or formal statements

Return a JSON array of content blocks found on this page. Each block should have:
- "type": one of the types above
- "description": brief description of what you see (1-2 sentences)
- "extracted_data": any text, labels, values, or details you can read from that content

Return ONLY a valid JSON array, no explanations or markdown:
[
    {
        "type": "text",
        "description": "Handwritten answer about operating system scheduling",
        "extracted_data": "The text discusses round-robin scheduling..."
    }
]

If the page appears blank or unreadable, return: []
"""


# --------------- Valid Content Types ---------------
VALID_TYPES = {"text", "diagram", "graph", "numerical", "theorem"}


def classify_page_content(image_path, page_number=1):
    """
    Analyze a page image and classify the content types present.

    Args:
        image_path (str): Path to the page image.
        page_number (int): Page number for the result structure.

    Returns:
        dict: {
            "page_number": int,
            "content_blocks": [{ "type": str, "description": str, "extracted_data": str }]
        }
    """
    empty_result = {
        "page_number": page_number,
        "content_blocks": []
    }

    if not os.path.exists(image_path):
        log(f"Image not found for classification: {image_path}")
        return empty_result

    log(f"Classifying content on page {page_number}: {os.path.basename(image_path)}")

    # Send to Gemini
    response_text = gemini_analyze_image(image_path, CLASSIFICATION_PROMPT)

    if not response_text:
        log(f"Gemini returned no response for page {page_number} classification")
        return empty_result

    # Parse the response
    content_blocks = _parse_classification_response(response_text, page_number)

    return {
        "page_number": page_number,
        "content_blocks": content_blocks
    }


def _parse_classification_response(response_text, page_number):
    """
    Parse Gemini's classification response into a list of content blocks.
    """
    # Strip markdown code block wrappers
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    try:
        parsed = json.loads(cleaned)

        if not isinstance(parsed, list):
            log(f"Page {page_number}: Expected JSON array, got {type(parsed).__name__}")
            # If it's a dict with a blocks/content key, try to extract
            if isinstance(parsed, dict):
                for key in ["content_blocks", "blocks", "content"]:
                    if key in parsed and isinstance(parsed[key], list):
                        parsed = parsed[key]
                        break
                else:
                    # Wrap single dict in a list
                    parsed = [parsed]

        # Validate and clean each block
        blocks = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            content_type = str(item.get("type", "text")).lower().strip()
            # Normalize to valid types
            if content_type not in VALID_TYPES:
                content_type = _infer_type(content_type)

            blocks.append({
                "type": content_type,
                "description": str(item.get("description", "")).strip(),
                "extracted_data": str(item.get("extracted_data", "")).strip()
            })

        log(f"Page {page_number}: classified {len(blocks)} content block(s) — "
            f"{', '.join(b['type'] for b in blocks)}")

        return blocks

    except json.JSONDecodeError as e:
        log(f"Page {page_number}: Failed to parse classification JSON: {e}")
        log(f"Raw response (first 300 chars): {response_text[:300]}")

        # Fallback: treat entire page as text
        return [{
            "type": "text",
            "description": "Could not classify — treating as text",
            "extracted_data": response_text[:500]  # Include some of Gemini's analysis
        }]


def _infer_type(raw_type):
    """
    Map non-standard type labels to valid types.
    """
    raw = raw_type.lower()
    if any(kw in raw for kw in ["diagram", "figure", "circuit", "flowchart", "illustration", "drawing"]):
        return "diagram"
    if any(kw in raw for kw in ["graph", "chart", "plot", "coordinate"]):
        return "graph"
    if any(kw in raw for kw in ["numerical", "calculation", "equation", "math", "formula"]):
        return "numerical"
    if any(kw in raw for kw in ["theorem", "proof", "derivation", "lemma", "corollary"]):
        return "theorem"
    return "text"


def get_content_type_summary(content_blocks):
    """
    Produce a summary of content types found across all blocks.
    Useful for deciding evaluation strategy.

    Args:
        content_blocks (list): List of content block dicts.

    Returns:
        dict: { "has_diagrams": bool, "has_graphs": bool, "has_numericals": bool,
                "has_theorems": bool, "types_found": ["text", "diagram"] }
    """
    types_found = set()
    for block in content_blocks:
        types_found.add(block.get("type", "text"))

    return {
        "has_diagrams": "diagram" in types_found,
        "has_graphs": "graph" in types_found,
        "has_numericals": "numerical" in types_found,
        "has_theorems": "theorem" in types_found,
        "types_found": sorted(list(types_found))
    }
