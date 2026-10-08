"""Extracts a project/business identifier from a filename or folder path,
e.g. "AB31" from "AB31_compliance_report.pdf" or from "Projects/AB31/..." —
the architecture doc's example of a code users search by (search_files_tool
matches on this too).

This is a placeholder heuristic, not a real answer. DKK's actual project
numbering convention is unknown until Phase 0 discovery happens — revisit
this regex once that's known instead of assuming this guess is correct.
"""

import re

# 2-3 letters followed by 1-4 digits, e.g. AB31, PRJ104 — a common shape for
# project codes, but genuinely just a guess pending real DKK conventions.
# Uses explicit lookaround instead of \b: \b treats underscore as a word
# character, so it fails to find "AB31" in "AB31_test_memo" — exactly the
# most common real filename shape. This version doesn't have that bug.
PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z]{2,3}\d{1,4})(?![A-Z0-9])")


def extract_business_identifier(filename: str, folder_path: str | None = None) -> str | None:
    """Filename takes priority (it's the more deliberate signal); falls back
    to the folder path so a client that organizes by project-coded folders
    (e.g. "Projects/AB31/drainage_report.txt") rather than project-coded
    filenames still gets indexed under the right code. Caught by testing: a
    real batch upload organized by folder was invisible to "what documents
    do we have for project AB31" until this fallback was added — the file
    names alone (drainage_report.txt) never contained the code."""
    match = PATTERN.search(filename.upper())
    if match:
        return match.group(1)
    if folder_path:
        match = PATTERN.search(folder_path.upper())
        if match:
            return match.group(1)
    return None
