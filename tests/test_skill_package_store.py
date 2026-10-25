from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import json
import subprocess
import sys
import zipfile

import pytest

from core.project_snapshot import ProjectSnapshot, SnapshotFile
from core.skill_package import SkillPackage
from core.skill_package_store import SkillPackageStore


def package(body="first"):
    return SkillPackage.from_snapshot(ProjectSnapshot((SnapshotFile(
        "SKILL.md", ("---\nname: example\ndescription: Example package\n---\n" + body).encode()),
        SnapshotFile("scripts/check.py", b"raise RuntimeError('never execute')"),
    )), "example")


def test_persist_reopen_versions_provenance_and_inactive_status(tmp_path):
    store = SkillPackageStore(tmp_path / "catalog")
    first = store.import_snapshot(package(), origin="local fixture one")
    second = store.import_snapshot(package("second"), origin="local fixture two")
    reopened = SkillPackageStore(tmp_path / "catalog")
    assert (first["version"], second["version"]) == (1, 2)
    rows = reopened.list_packages()
    assert len(rows) == 1 and rows[0]["version"] == 2
    assert rows[0]["state"] == "inactive" and rows[0]["validation"] == "structural_only"
    assert reopened.load("example", 1).instructions == "first"
    assert reopened.load("example").instructions == "second"
    assert [row["origin"] for row in reopened.versions("example")] == ["local fixture two", "local fixture one"]


def test_import_revalidates_forged_metadata_and_rolls_back_quota_failure(tmp_path, monkeypatch):
    store = SkillPackageStore(tmp_path / "catalog")
    original = package()
    with pytest.raises(ValueError, match="divergem"):
        store.import_snapshot(replace(original, instructions="forged"), origin="fixture")
    monkeypatch.setattr(store.artifacts, "MAX_BYTES", 1)
    with pytest.raises(ValueError):
        store.import_snapshot(original, origin="fixture")
    assert store.list_packages() == [] and store.artifacts.projects() == []


def test_concurrent_imports_get_distinct_numbers(tmp_path):
    first = SkillPackageStore(tmp_path / "catalog")
    second = SkillPackageStore(tmp_path / "catalog")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store.import_snapshot, package(text), origin="fixture")
                   for store, text in ((first, "one"), (second, "two"))]
        assert sorted(future.result()["version"] for future in futures) == [1, 2]
    assert len(first.list_packages()) == 1


def test_persisted_byte_corruption_blocks_loading(tmp_path):
    store = SkillPackageStore(tmp_path / "catalog")
    store.import_snapshot(package(), origin="fixture")
    with store.artifacts._db() as db:
        db.execute("UPDATE files SET content=? WHERE name='scripts/check.py'", (b"changed",))
    with pytest.raises(ValueError, match="Integridade"):
        store.load("example")


@pytest.mark.skipif(os.name != "nt", reason="Windows snapshots and ZIP")
def test_folder_import_and_version_export_keep_source_unchanged(tmp_path):
    folder = tmp_path / "example"
    package().snapshot.write_new_directory(folder)
    original = (folder / "SKILL.md").read_bytes()
    store = SkillPackageStore(tmp_path / "catalog")
    result = store.import_directory(folder)
    assert result["state"] == "inactive"
    assert (folder / "SKILL.md").read_bytes() == original
    destination = tmp_path / "export.zip"
    store.export("example", 1, destination)
    with zipfile.ZipFile(destination) as archive:
        assert archive.read("example/SKILL.md") == original
    with pytest.raises(ValueError, match="cancelada"):
        store.import_directory(folder, cancelled=lambda: True)
    assert len(store.versions("example")) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows package import")
def test_package_commands_import_list_inspect_export_across_processes(tmp_path):
    folder = tmp_path / "example"
    package().snapshot.write_new_directory(folder)
    command = [sys.executable, "tools/manage_skill_packages.py", "--store", str(tmp_path / "catalog")]

    def run(*args):
        result = subprocess.run([*command, *map(str, args)], capture_output=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
        data = json.loads(result.stdout)
        assert data["ok"] and not data["execution_authorized"]
        return data["result"]

    assert run("import", folder)["version"] == 1
    assert run("list")[0]["state"] == "inactive"
    assert run("inspect", "example")["instructions"] == "first"
    assert run("versions", "example")[0]["version"] == 1
    destination = tmp_path / "export.zip"
    assert run("export", "example", 1, destination)["exported"] == str(destination)
    assert destination.is_file()
