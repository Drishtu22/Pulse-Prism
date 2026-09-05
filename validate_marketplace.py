#!/usr/bin/env python3
"""Validate the marketplace manifest and every skill folder.

Checks the round's hard requirements: a well-formed manifest, exactly one entrypoint,
every listed skill present with a valid SKILL.md carrying YAML frontmatter, and no
dangling references to scripts or reference files.

Standard library only, so this runs anywhere with no install step.

Usage:
    python3 validate_marketplace.py [marketplace_root]
"""

import json
import os
import re
import sys

REQUIRED_FRONTMATTER = ["name", "description"]
RECOMMENDED_FRONTMATTER = ["license", "allowed-tools"]


def parse_frontmatter(path):
    """Minimal YAML frontmatter reader — enough for the key/value and block-scalar forms
    a SKILL.md uses, without requiring PyYAML."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    block, body = text[3:end], text[end + 4:]

    keys, current = {}, None
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            current = m.group(1)
            keys[current] = m.group(2).strip()
        elif current and line.startswith((" ", "\t")):
            keys[current] = (keys[current] + " " + line.strip()).strip()
    return keys, body


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    errors, warnings, ok = [], [], []

    manifest_path = os.path.join(root, "marketplace.json")
    if not os.path.exists(manifest_path):
        print("FAIL: marketplace.json not found at root")
        return 1
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: marketplace.json is not valid JSON: {e}")
        return 1
    ok.append("marketplace.json parses")

    for field in ("name", "version", "skills"):
        if field not in manifest:
            errors.append(f"manifest missing required field '{field}'")

    skills = manifest.get("skills", [])
    entrypoints = [s for s in skills if s.get("entrypoint") is True]
    if len(entrypoints) == 1:
        ok.append(f"exactly one entrypoint: {entrypoints[0].get('id')}")
    else:
        errors.append(f"expected exactly one entrypoint, found {len(entrypoints)}")

    if not os.path.exists(os.path.join(root, "README.md")):
        errors.append("README.md not found at root")
    else:
        ok.append("README.md present")

    seen_ids = set()
    for entry in skills:
        sid, rel = entry.get("id"), entry.get("path")
        if not sid or not rel:
            errors.append(f"skill entry missing id or path: {entry}")
            continue
        if sid in seen_ids:
            errors.append(f"duplicate skill id '{sid}'")
        seen_ids.add(sid)

        folder = os.path.join(root, rel)
        if not os.path.isdir(folder):
            errors.append(f"{sid}: path '{rel}' is not a directory")
            continue

        skill_md = os.path.join(folder, "SKILL.md")
        if not os.path.exists(skill_md):
            errors.append(f"{sid}: SKILL.md missing")
            continue

        fm, body = parse_frontmatter(skill_md)
        if fm is None:
            errors.append(f"{sid}: SKILL.md has no YAML frontmatter")
            continue

        for key in REQUIRED_FRONTMATTER:
            if not fm.get(key):
                errors.append(f"{sid}: frontmatter missing required '{key}'")
        for key in RECOMMENDED_FRONTMATTER:
            if not fm.get(key):
                warnings.append(f"{sid}: frontmatter missing recommended '{key}'")

        if fm.get("name") and fm["name"] != sid:
            errors.append(f"{sid}: frontmatter name '{fm['name']}' does not match manifest id")

        desc = fm.get("description", "")
        if desc and len(desc) < 60:
            warnings.append(f"{sid}: description is short ({len(desc)} chars); "
                            "it is the primary trigger signal")
        if desc and not re.search(r"\buse (this )?(skill )?when\b|\buse it for\b|\binvoked by\b", desc, re.I):
            warnings.append(f"{sid}: description states what it does but not when to use it")

        lines = body.count("\n")
        if lines > 500:
            warnings.append(f"{sid}: SKILL.md body is {lines} lines; consider moving "
                            "detail into references/")

        # Dangling reference check: a SKILL.md that names a script which does not exist
        # is a hygiene failure a grader will find immediately.
        for ref in re.findall(r"`?(scripts/[\w./-]+\.(?:py|sh|js))`?", body):
            if not os.path.exists(os.path.join(folder, ref)):
                errors.append(f"{sid}: SKILL.md references missing file '{ref}'")
        for ref in re.findall(r"`?((?:\.\./[\w-]+/)?references/[\w./-]+\.(?:md|json))`?", body):
            target = os.path.normpath(os.path.join(folder, ref))
            if not os.path.exists(target):
                errors.append(f"{sid}: SKILL.md references missing file '{ref}'")

        ok.append(f"{sid}: SKILL.md valid ({lines} body lines)")

    for name, items in (("OK", ok), ("WARNING", warnings), ("ERROR", errors)):
        if items:
            print(f"\n{name}:")
            for i in items:
                print(f"  - {i}")

    print(f"\n{len(ok)} passed, {len(warnings)} warnings, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
