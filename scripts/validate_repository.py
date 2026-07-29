#!/usr/bin/env python3
"""Validate the repair-skill catalog, skill structure, JSON assets and self-tests."""

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog.json"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def frontmatter_name(skill_md):
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{skill_md}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{skill_md}: unterminated YAML frontmatter")
    frontmatter = text[4:end]
    for line in frontmatter.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise ValueError(f"{skill_md}: missing frontmatter name")


def validate_json_files(skill_dir):
    for path in skill_dir.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def main():
    errors = []
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: invalid catalog: {exc}", file=sys.stderr)
        raise SystemExit(1)

    categories = catalog.get("categories", {})
    seen_names = set()
    seen_paths = set()

    for entry in catalog.get("skills", []):
        name = entry.get("name", "")
        category = entry.get("category")
        relative = entry.get("path", "")
        skill_dir = ROOT / relative

        if not NAME_PATTERN.fullmatch(name):
            errors.append(f"{name!r}: invalid skill name")
        if name in seen_names:
            errors.append(f"{name}: duplicate catalog name")
        seen_names.add(name)
        if relative in seen_paths:
            errors.append(f"{name}: duplicate catalog path {relative}")
        seen_paths.add(relative)
        if category not in categories:
            errors.append(f"{name}: unknown category {category!r}")
        if Path(relative).parts[:2] != ("skills", category):
            errors.append(f"{name}: path must be under skills/{category}/")
        if skill_dir.name != name:
            errors.append(f"{name}: directory name does not match skill name")

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"{name}: missing SKILL.md")
            continue
        try:
            if frontmatter_name(skill_md) != name:
                errors.append(f"{name}: SKILL.md frontmatter name mismatch")
            validate_json_files(skill_dir)
        except ValueError as exc:
            errors.append(str(exc))

        self_test = entry.get("self_test")
        if self_test:
            test_path = skill_dir / self_test
            if not test_path.is_file():
                errors.append(f"{name}: missing self-test {self_test}")
            else:
                result = subprocess.run(
                    [sys.executable, str(test_path)],
                    cwd=skill_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode:
                    errors.append(
                        f"{name}: self-test failed: "
                        f"{result.stdout.strip()} {result.stderr.strip()}".strip()
                    )

    actual_skills = {
        str(path.parent.relative_to(ROOT))
        for path in (ROOT / "skills").glob("*/*/SKILL.md")
    }
    unregistered = actual_skills - seen_paths
    for path in sorted(unregistered):
        errors.append(f"unregistered skill directory: {path}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"repository valid: {len(seen_names)} skill(s), {len(categories)} categories")


if __name__ == "__main__":
    main()
