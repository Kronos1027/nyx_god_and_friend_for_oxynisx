import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.project_snapshot import ProjectSnapshot, SnapshotFile
from core.project_store import ProjectStore


def sample(value=b"first"):
    return ProjectSnapshot((SnapshotFile("main.py", value),))


def test_versions_survive_reopen_and_restore_never_overwrites(tmp_path):
    store = ProjectStore(tmp_path / "store")
    identifier = store.create("Projeto", sample())
    assert store.save(identifier, sample(b"second")) == 2
    reopened = ProjectStore(store.directory)
    assert reopened.restore(identifier, 1) == 3
    assert reopened.save(identifier, sample(b"fourth")) == 4
    assert reopened.load(identifier, 2).files[0].content == b"second"
    assert reopened.load(identifier, 3).files[0].content == b"first"
    assert [row["number"] for row in reopened.versions(identifier)] == [4, 3, 2, 1]


def test_failed_new_project_rolls_back_and_budget_does_not_prune(tmp_path):
    store = ProjectStore(tmp_path / "store")
    store.MAX_BYTES = 3
    with pytest.raises(ValueError, match="orçamento"):
        store.create("Too big", sample())
    assert store.projects() == []
    identifier = store.create("Small", sample(b"123"))
    with pytest.raises(ValueError, match="orçamento"):
        store.save(identifier, sample(b"4"))
    assert len(store.versions(identifier)) == 1
    assert store.load(identifier, 1).files[0].content == b"123"


def test_corrupted_version_cannot_be_exported(tmp_path):
    store = ProjectStore(tmp_path / "store")
    identifier = store.create("Project", sample())
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE files SET content=?", (b"changed",))
    with pytest.raises(ValueError, match="Integridade"):
        store.load(identifier, 1)


def test_concurrent_saves_allocate_distinct_versions(tmp_path):
    store = ProjectStore(tmp_path / "store")
    identifier = store.create("Project", sample())
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = list(pool.map(lambda value: store.save(identifier, sample(value)), (b"A", b"B")))
    assert sorted(versions) == [2, 3]
    assert len(store.versions(identifier)) == 3


def test_delete_only_removes_selected_catalog_project(tmp_path):
    store = ProjectStore(tmp_path / "store")
    first, second = store.create("A", sample()), store.create("B", sample())
    sentinel = tmp_path / "source.py"
    sentinel.write_text("preserve")
    store.delete(first)
    assert store.versions(first) == []
    assert store.projects()[0]["id"] == second
    assert sentinel.read_text() == "preserve"
    assert store.load(second, 1).files[0].content == b"first"


def test_existing_non_catalog_directory_is_preserved(tmp_path):
    (tmp_path / "private.txt").write_text("preserve")
    with pytest.raises(ValueError, match="não pertence"):
        ProjectStore(tmp_path)
    assert (tmp_path / "private.txt").read_text() == "preserve"
