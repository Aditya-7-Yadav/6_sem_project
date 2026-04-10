"""
Gemini Output Cleaner
---------------------
Removes Gemini-specific artifacts and pollution from merged OCR text.

The Gemini integration adds analysis tags like [DIAGRAM]: ..., [GRAPH]: etc.
to the merged text to make content visible to segmentation. However, these
tags must be removed before the text is used for grading, as they are NOT
part of the student's actual answer and would confuse evaluators.

Functions:
- clean_gemini_artifacts(text): Remove all Gemini-added tags and artifacts.
- extract_gemini_metadata(text): Extract Gemini analysis into a separate dict.
"""

import re


def clean_gemini_artifacts(text):
    """
    Remove Gemini-specific artifacts from merged text.

    Removes:
    - [DIAGRAM]: ... blocks
    - [GRAPH]: ... blocks
    - [NUMERICAL - AI Analysis]: ... blocks
    - [THEOREM - ...]: ... blocks
    - Any markdown code blocks (```)
    - Explanatory phrases like "Here is the analysis:", "Note:"
    - Lines that start with AI analysis markers

    Args:
        text: The merged text that may contain Gemini pollution.

    Returns:
        Cleaned text with only student content (preserving genuine student-written
        diagram labels if they appear in context).
    """
    if not text:
        return ""

    cleaned = text

    # Patterns to remove entirely (including their content)
    # These are inserted by Gemini and not part of student answer
    patterns_to_remove = [
        # Tagged analysis blocks (anything like [TYPE]: ... until next blank line or tag)
        r'\n?\[DIAGRAM\]:.*?(?=\n\n|\n\[[A-Z]|$)',  # non-greedy until double newline or next tag
        r'\n?\[GRAPH\]:.*?(?=\n\n|\n\[[A-Z]|$)',
        r'\n?\[NUMERICAL.*?\]:.*?(?=\n\n|\n\[[A-Z]|$)',
        r'\n?\[THEOREM.*?\]:.*?(?=\n\n|\n\[[A-Z]|$)',
        r'\n?\[TEXT - AI Analysis\]:.*?(?=\n\n|\n\[[A-Z]|$)',
        # Markdown code blocks
        r'```[\s\S]*?```',
        # Lines that start with common AI prefixes (entire lines)
        r'(?:^|\n)\s*(?:Here is|Analysis:|Note:|AI Analysis:|Gemini says:).*?(?=\n|$)',
    ]

    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE | re.DOTALL)

    # Clean up any leftover stray tags without content (e.g., just "[DIAGRAM]")
    cleaned = re.sub(r'\[[A-Z]+\](?=\n|$)', '', cleaned)

    # Normalize multiple consecutive newlines to max 2
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    # Strip leading/trailing whitespace
    return cleaned.strip()


def extract_gemini_metadata(text):
    """
    Extract Gemini analysis metadata from the text (before cleaning).
    Useful for debugging and transparency.

    Returns a dict with keys: diagram_analysis, graph_analysis,
    numerical_analysis, theorem_analysis. Values are strings or empty.
    """
    if not text:
        return {}

    metadata = {}
    patterns = {
        "diagram_analysis": r'\[DIAGRAM\]:\s*(.*?)(?=\n\n|\n\[|$)',
        "graph_analysis": r'\[GRAPH\]:\s*(.*?)(?=\n\n|\n\[|$)',
        "numerical_analysis": r'\[NUMERICAL[^\]]*\]:\s*(.*?)(?=\n\n|\n\[|$)',
        "theorem_analysis": r'\[THEOREM[^\]]*\]:\s*(.*?)(?=\n\n|\n\[|$)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if match:
            metadata[key] = match.group(1).strip()
        else:
            metadata[key] = ""

    # Remove empty entries
    return {k: v for k, v in metadata.items() if v}
