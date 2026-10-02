"""Guard against raw internal vocabulary reaching the screen.

The interface promises plain English over implementation detail, and that
promise is easy to break by accident: a backend field that already reads
well ("Limited", "High") gets replaced with its index, or an empty value
falls through and renders as a literal token.

This is a regression guard, not a general linter. Each entry below is a
leak that actually occurred. `null` and `undefined` are deliberately absent
from the list because they are legitimate JavaScript values used all over
the component logic; only phrases that can only be display copy are listed.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_SRC = BACKEND_DIR.parent / "frontend" / "src"

# Lowercase, matched case-insensitively. Each one can only occur in a string
# a person reads, never in working JavaScript. Domain words that happen to be
# used as identifiers or in comments ("ceiling", "pillars") are deliberately
# absent: this list is for leaks that reach the screen, not for naming.
BANNED_PHRASES = (
    "evidence tier",
    "tier 0",
    "tier 1",
    "tier 2",
    " of 3 is",
)


def _components() -> list[Path]:
    if not FRONTEND_SRC.exists():
        return []
    return sorted(
        path for path in FRONTEND_SRC.rglob("*")
        if path.suffix in {".jsx", ".js"}
    )


def test_no_raw_internal_vocabulary_in_the_interface():
    offenders: dict[str, list[str]] = {}
    for path in _components():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        found = [phrase for phrase in BANNED_PHRASES if phrase in text]
        if re.search(r"\bnan\b", text):
            found.append("NaN")
        if found:
            offenders[str(path.relative_to(BACKEND_DIR.parent))] = found

    assert not offenders, f"raw vocabulary in user-facing copy: {offenders}"


def test_the_guard_actually_catches_a_planted_leak(tmp_path):
    """A guard that cannot fail is worse than no guard, so prove it fails."""
    planted = tmp_path / "Leak.jsx"
    planted.write_text(
        "export default () => <p>Evidence tier 0 of 3 is derived only from balls</p>",
        encoding="utf-8",
    )
    text = planted.read_text(encoding="utf-8").lower()
    assert any(phrase in text for phrase in BANNED_PHRASES)


def test_the_component_tree_is_actually_present():
    """Guard against the guard silently scanning nothing."""
    assert _components(), "expected to find frontend components to scan"