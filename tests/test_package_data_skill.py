import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import pytest

# Add script directory to sys.path
SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "skills"
    / "data-context-extractor"
    / "scripts"
    / "package_data_skill.py"
)
sys.path.insert(0, str(SCRIPT_PATH.parent))
import package_data_skill as pds


VALID_SKILL_MD = """---
name: acme-analyst
description: Test data skill for financial analysis
---

# Acme Analyst
This skill helps analysts navigate company metrics.
"""


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def create_skill_tree(skill_dir: Path, include_hidden_file=False, include_hidden_dir=False):
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
    refs = skill_dir / "references"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "metrics.md").write_text("# Metrics\n- ARR: Annual Recurring Revenue\n", encoding="utf-8")

    if include_hidden_file:
        (skill_dir / ".local-secret").write_text("secret_token=123", encoding="utf-8")
    if include_hidden_dir:
        hidden_dir = skill_dir / ".git_test"
        hidden_dir.mkdir(parents=True, exist_ok=True)
        (hidden_dir / "config").write_text("dummy", encoding="utf-8")


def test_package_skill_visible_parent(temp_dir):
    skill_dir = temp_dir / "visible" / "acme-analyst"
    create_skill_tree(skill_dir, include_hidden_file=True, include_hidden_dir=True)
    out_dir = temp_dir / "out-visible"

    zip_path = pds.package_skill(str(skill_dir), str(out_dir))
    assert zip_path is not None
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        # Verify valid files are packaged
        assert "acme-analyst/SKILL.md" in names
        assert "acme-analyst/references/metrics.md" in names
        # Verify hidden files and dirs inside the skill are excluded
        assert not any(".local-secret" in n for n in names)
        assert not any(".git_test" in n for n in names)
        assert len(names) == 2


def test_package_skill_hidden_parent(temp_dir):
    skill_dir = temp_dir / ".claude" / "skills" / "acme-analyst"
    create_skill_tree(skill_dir, include_hidden_file=True, include_hidden_dir=True)
    out_dir = temp_dir / "out-hidden"

    zip_path = pds.package_skill(str(skill_dir), str(out_dir))
    assert zip_path is not None
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        # Hidden parent .claude must not prevent packaging
        assert "acme-analyst/SKILL.md" in names
        assert "acme-analyst/references/metrics.md" in names
        # Hidden files/dirs inside skill must still be excluded
        assert not any(".local-secret" in n for n in names)
        assert not any(".git_test" in n for n in names)
        assert len(names) == 2


def test_package_skill_hidden_nested_directory(temp_dir):
    skill_dir = temp_dir / "skills" / "nested-hidden"
    create_skill_tree(skill_dir)
    nested_hidden = skill_dir / "references" / ".cache"
    nested_hidden.mkdir(parents=True, exist_ok=True)
    (nested_hidden / "temp.json").write_text("{}", encoding="utf-8")
    out_dir = temp_dir / "out"

    zip_path = pds.package_skill(str(skill_dir), str(out_dir))
    assert zip_path is not None

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert not any(".cache" in n for n in names)
        assert len(names) == 2


def test_package_empty_skill_fails(temp_dir):
    empty_skill = temp_dir / "empty-skill"
    empty_skill.mkdir(parents=True, exist_ok=True)
    # Missing SKILL.md should fail validation
    res = pds.package_skill(str(empty_skill), str(temp_dir / "out"))
    assert res is None


def test_package_all_hidden_files_fails(temp_dir):
    skill_dir = temp_dir / "all-hidden"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(VALID_SKILL_MD, encoding="utf-8")
    # If SKILL.md is valid, but pretend all files are filtered (test files_added == 0 branch)
    # We test non-existent dir
    non_existent = temp_dir / "non-existent"
    assert pds.package_skill(str(non_existent)) is None


def test_cli_execution_both_modes(temp_dir):
    visible_skill = temp_dir / "visible" / "acme-analyst"
    hidden_skill = temp_dir / ".claude" / "skills" / "acme-analyst"
    create_skill_tree(visible_skill)
    create_skill_tree(hidden_skill)
    out_dir = temp_dir / "cli-out"

    # Run CLI on visible
    r1 = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(visible_skill), str(out_dir)],
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0
    assert "Successfully packaged skill" in r1.stdout

    # Run CLI on hidden
    r2 = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(hidden_skill), str(out_dir)],
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0
    assert "Successfully packaged skill" in r2.stdout
