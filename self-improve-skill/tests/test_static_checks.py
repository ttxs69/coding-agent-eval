"""Static checks for the self-improve skill.

Validate that SKILL.md is well-formed and triggerable. Run via:
    uv run pytest self-improve-skill/tests/test_static_checks.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse flat YAML frontmatter (between --- markers) as a dict.

    Handles only `key: value` lines; ignores list/multiline values.
    Sufficient for skill frontmatter, which is flat.
    """
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def test_skill_md_exists():
    assert SKILL_MD.is_file(), f"Missing: {SKILL_MD}"


def test_frontmatter_has_required_fields():
    fm = parse_frontmatter(SKILL_MD.read_text())
    assert "name" in fm, "frontmatter missing 'name'"
    assert "description" in fm, "frontmatter missing 'description'"


def test_name_is_self_improve():
    fm = parse_frontmatter(SKILL_MD.read_text())
    assert fm.get("name") == "self-improve", (
        f"name should be 'self-improve', got {fm.get('name')!r}"
    )


def test_description_contains_trigger_words():
    fm = parse_frontmatter(SKILL_MD.read_text())
    desc = fm.get("description", "").lower()
    for trigger in ("self-improve", "improve", "evolve"):
        assert trigger in desc, (
            f"description missing trigger word {trigger!r}: {desc!r}"
        )


def test_description_mentions_categories():
    fm = parse_frontmatter(SKILL_MD.read_text())
    desc = fm.get("description", "").lower()
    for category in ("feature", "next", "forward"):
        assert category in desc, (
            f"description missing category {category!r}: {desc!r}"
        )


def test_references_exist():
    """All references/*.md paths mentioned in SKILL.md exist."""
    if not SKILL_MD.exists():
        return
    text = SKILL_MD.read_text()
    refs = re.findall(r"references/([a-z0-9_-]+\.md)", text)
    for ref in refs:
        ref_path = SKILL_DIR / "references" / ref
        assert ref_path.is_file(), f"Referenced file missing: {ref_path}"
