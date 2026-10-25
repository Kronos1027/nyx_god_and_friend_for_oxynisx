import os
import json
import subprocess
import sys
import zipfile

import pytest

from core.project_snapshot import ProjectSnapshot, SnapshotFile
from core.skill_package import SkillPackage, SkillPackageError, parse_skill_document


def document(extra="", body="# Etapas\nConsulte references/guide.md.\n"):
    return ("---\nname: sample-skill\ndescription: Exemplo de pacote\n" + extra + "---\n" + body).encode()


def test_metadata_resources_and_tool_declaration_are_data():
    package = SkillPackage.from_snapshot(ProjectSnapshot((
        SnapshotFile("SKILL.md", document('metadata:\n  version: "1.0"\nallowed-tools: shell read_file\n')),
        SnapshotFile("references/guide.md", b"Reference content"),
        SnapshotFile("scripts/check.py", b"raise RuntimeError('must not execute')"),
    )), "sample-skill")
    assert package.metadata.metadata == (("version", "1.0"),)
    assert package.metadata.allowed_tools == "shell read_file"
    assert package.read_text("references/guide.md") == "Reference content"
    assert package.read_text("scripts/check.py").startswith("raise RuntimeError")
    assert "Consulte" in package.instructions


@pytest.mark.parametrize("content", [
    b"no frontmatter", b"---\nname: sample-skill", b"\xff", b"x" * 65537,
    document("name: duplicate\n"), document("metadata: &repeat {a: *repeat}\n"),
    document("metadata: !!python/tuple [one, two]\n"),
    document("metadata: {version: 1}\n"), document("permissions: full\n"),
    document("compatibility: ''\n"), document("metadata: {x: {nested: value}}\n"),
], ids=["missing", "unterminated", "encoding", "oversized", "duplicate", "alias", "python-tag", "typed-metadata", "unknown", "empty", "nested"])
def test_invalid_or_dangerous_frontmatter_rejected(content):
    with pytest.raises(SkillPackageError):
        parse_skill_document(content, "sample-skill")


@pytest.mark.parametrize("name", ["Different", "sample--skill", "-sample", "../sample", "sample_skill"])
def test_name_must_be_portable_and_match_folder(name):
    with pytest.raises(SkillPackageError):
        parse_skill_document(document().replace(b"sample-skill", name.encode()), name)
    with pytest.raises(SkillPackageError):
        parse_skill_document(document(), name)


def test_nested_yaml_and_large_metadata_are_bounded():
    for extra in ("metadata: " + "[" * 20 + "x" + "]" * 20 + "\n",
                  "metadata:\n" + "".join(f"  k{i}: v\n" for i in range(140)),
                  "license: " + "x" * 9000 + "\n"):
        with pytest.raises(SkillPackageError):
            parse_skill_document(document(extra), "sample-skill")


def test_bom_and_multiline_description_preserved():
    raw = b"\xef\xbb\xbf---\nname: sample-skill\ndescription: >\n  one\n  two\n---\nbody\n"
    metadata, body = parse_skill_document(raw, "sample-skill")
    assert metadata.description == "one two\n" and body == "body\n"


@pytest.mark.skipif(os.name != "nt", reason="Native Windows snapshot")
def test_capture_export_and_no_script_execution(tmp_path):
    root = tmp_path / "sample-skill"
    root.mkdir()
    (root / "SKILL.md").write_bytes(document())
    (root / "scripts").mkdir()
    sentinel = tmp_path / "never-created"
    script = f"from pathlib import Path; Path({str(sentinel)!r}).touch()".encode()
    (root / "scripts" / "init.py").write_bytes(script)
    (root / ".env").write_text("synthetic secret")
    package = SkillPackage.capture(root)
    assert package.snapshot.skipped
    assert not sentinel.exists()
    archive = tmp_path / "package.zip"
    package.export_zip(archive)
    with zipfile.ZipFile(archive) as exported:
        assert exported.read("sample-skill/SKILL.md") == document()
        assert exported.read("sample-skill/scripts/init.py") == script
        assert "sample-skill/.env" not in exported.namelist()
    assert not sentinel.exists()
    with pytest.raises(ValueError):
        package.read_text("../never-created")
    with pytest.raises(FileExistsError):
        package.export_zip(archive)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows snapshot")
def test_inspection_command_reports_validation_without_activation(tmp_path):
    root = tmp_path / "sample-skill"
    root.mkdir()
    (root / "SKILL.md").write_bytes(document().replace(b"Exemplo de pacote", "Análise 日本語".encode()))
    target = tmp_path / "export.zip"
    result = subprocess.run([sys.executable, "tools/inspect_skill_package.py", str(root), "--export", str(target)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["valid_structure"] and not report["execution_authorized"]
    assert not report["functional_tests_run"] and target.is_file()
    assert report["files"] == ["SKILL.md"] and len(report["sha256"]) == 64
    assert report["metadata"]["description"] == "Análise 日本語"


@pytest.mark.skipif(os.name != "nt", reason="Native Windows snapshot")
def test_capture_current_directory_uses_actual_folder_name(tmp_path, monkeypatch):
    root = tmp_path / "sample-skill"
    root.mkdir()
    (root / "SKILL.md").write_bytes(document())
    monkeypatch.chdir(root)
    assert SkillPackage.capture(".").metadata.name == "sample-skill"
