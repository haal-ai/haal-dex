# Feature: intent, Property 11: File read/write round trip
"""Property 11: File read/write round trip

For any byte content and file path, writing the content via the file write
tool and then reading it via the file read tool should return the original
content.

**Validates: Requirements 6.1, 6.2**

Strategy:
- Generate random text content via ``st.text()`` (UTF-8 safe)
- Generate a random safe filename component
- Write to a temp directory, then read back and compare
"""

from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings, strategies as st

from app.engine.tools import read_file, write_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(tool_fn, **kwargs):
    """Call a tool function, stripping any Strands wrapper if present."""
    fn = getattr(tool_fn, "__wrapped__", tool_fn)
    return fn(**kwargs)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Text content that is valid UTF-8 (the tools use utf-8 encoding).
# Exclude bare \r because Python text-mode I/O normalises line endings
# (\r → \n on read), which is expected platform behaviour, not a bug.
_content = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # exclude surrogates
        blacklist_characters="\r",
    ),
    min_size=0,
    max_size=4096,
)

# Safe filename component (alphanumeric + underscore, non-empty).
_filename = st.from_regex(r"[a-zA-Z0-9_]{1,30}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(content=_content, filename=_filename)
@settings(max_examples=100)
def test_write_then_read_returns_original_content(content: str, filename: str):
    """Property 11: For any content and path, write then read returns
    original content.

    **Validates: Requirements 6.1, 6.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, f"{filename}.txt")

        _call(write_file, path=path, content=content)
        result = _call(read_file, path=path)

        assert result == content, (
            f"Round-trip failed: wrote {len(content)} chars, "
            f"read back {len(result)} chars"
        )
