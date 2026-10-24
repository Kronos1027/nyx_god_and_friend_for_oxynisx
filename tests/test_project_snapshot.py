from contextlib import contextmanager
import hashlib
import os
import zipfile

import pytest

from core.project_snapshot import ProjectSnapshot, SnapshotError, SnapshotFile, SnapshotLimits

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows snapshot filesystem backend")


def test_capture_materialize_and_export_preserve_bytes_without_execution(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "pkg").mkdir()
    (source / "pkg" / "maths.py").write_text("def add(a, b): return a+b\n")
    (source / "main.py").write_text("raise RuntimeError('must never execute during copy')\n")
    (source / "image.png").write_bytes(b"\x89PNG\r\n\x00\xff")
    snapshot = ProjectSnapshot.capture(source)
    manifest = snapshot.manifest()
    assert manifest["bytes"] == sum(len(item.content) for item in snapshot.files)
    assert all(
        item["sha256"] == hashlib.sha256((source / item["path"]).read_bytes()).hexdigest()
        for item in manifest["files"]
    )
    (source / "main.py").write_text("changed after capture")
    destination = snapshot.write_new_directory(tmp_path / "staging")
    assert "must never execute" in (destination / "main.py").read_text()
    assert ProjectSnapshot.capture(destination).manifest()["sha256"] == manifest["sha256"]
    output = tmp_path / "project.zip"
    snapshot.export_zip(output)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {item.name for item in snapshot.files}
        for item in snapshot.files:
            assert archive.read(item.name) == item.content


def test_sensitive_names_and_dependency_trees_are_reported_but_not_copied(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("private remote")
    for name in (".env", ".env.local", "credentials.json", "private.pem"):
        (tmp_path / name).write_text("synthetic secret")
    (tmp_path / "main.py").write_text("print(96)")
    snapshot = ProjectSnapshot.capture(tmp_path)
    assert [item.name for item in snapshot.files] == ["main.py"]
    assert set(snapshot.skipped) == {
        ".git",
        ".env",
        ".env.local",
        "credentials.json",
        "private.pem",
    }


@pytest.mark.parametrize(
    "limit",
    [
        SnapshotLimits(files=1),
        SnapshotLimits(bytes=3),
        SnapshotLimits(file_bytes=2),
        SnapshotLimits(entries=1),
    ],
)
def test_snapshot_budget_rejects_oversized_input(tmp_path, limit):
    (tmp_path / "a.txt").write_bytes(b"123")
    (tmp_path / "b.txt").write_bytes(b"456")
    with pytest.raises(SnapshotError):
        ProjectSnapshot.capture(tmp_path, limits=limit)


def test_cancelled_snapshot_never_opens_files(tmp_path, monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("No file may be read after cancellation")

    monkeypatch.setattr("core.project_snapshot.regular_file", unexpected)
    with pytest.raises(SnapshotError, match="cancelada"):
        ProjectSnapshot.capture(tmp_path, cancelled=lambda: True)


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "C:/outside",
        "a\\b",
        "file:stream",
        "NUL.txt",
        "a./x",
        "dir/../x",
        "x\x00y",
        "dir//x",
    ],
)
def test_unsafe_artifact_names_rejected(name):
    with pytest.raises(SnapshotError):
        SnapshotFile(name, b"content")


def test_existing_destinations_are_not_overwritten(tmp_path):
    snapshot = ProjectSnapshot((SnapshotFile("main.py", b"print(1)"),))
    archive = tmp_path / "existing.zip"
    archive.write_bytes(b"preserve")
    with pytest.raises(OSError):
        snapshot.export_zip(archive)
    assert archive.read_bytes() == b"preserve"
    folder = tmp_path / "existing"
    folder.mkdir()
    (folder / "personal.txt").write_text("preserve")
    with pytest.raises(OSError):
        snapshot.write_new_directory(folder)
    assert (folder / "personal.txt").read_text() == "preserve"


def test_hardlinked_file_is_not_read(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("outside synthetic value")
    os.link(outside, source / "linked.txt")
    with pytest.raises(SnapshotError, match="hardlinks"):
        ProjectSnapshot.capture(source)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction/handle semantics")
def test_junctions_are_rejected_for_source_and_output(tmp_path):
    import _winapi

    source, outside = tmp_path / "source", tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    sentinel = outside / "private.txt"
    sentinel.write_text("preserve")
    _winapi.CreateJunction(str(outside), str(source / "redirect"))
    with pytest.raises(SnapshotError):
        ProjectSnapshot.capture(source)
    snapshot = ProjectSnapshot((SnapshotFile("main.py", b"print(1)"),))
    with pytest.raises(SnapshotError):
        snapshot.write_new_directory(source / "redirect" / "output")
    assert not (outside / "output").exists()
    assert sentinel.read_text() == "preserve"


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_open_source_handle_prevents_file_and_ancestor_replacement(tmp_path, monkeypatch):
    import core.project_snapshot as module

    source = tmp_path / "source"
    source.mkdir()
    original = source / "main.py"
    original.write_bytes(b"original")
    other = tmp_path / "other.py"
    other.write_bytes(b"replacement")
    real_open = module.regular_file
    attempts = []

    @contextmanager
    def guarded(path, **kwargs):
        with real_open(path, **kwargs) as stream:
            with pytest.raises(OSError):
                os.replace(other, original)
            with pytest.raises(OSError):
                source.rename(tmp_path / "moved")
            attempts.append(True)
            yield stream

    monkeypatch.setattr(module, "regular_file", guarded)
    snapshot = ProjectSnapshot.capture(source)
    assert attempts == [True]
    assert snapshot.files[0].content == b"original"
    assert other.read_bytes() == b"replacement"


def test_pinned_directory_rejects_data_write_handle(tmp_path):
    import _winapi
    import pywintypes
    import win32file
    from core.project_snapshot import pinned_directory

    outside, pinned = tmp_path / "outside", tmp_path / "pinned"
    outside.mkdir()
    pinned.mkdir()
    (outside / "sentinel").write_text("preserve")
    reference = tmp_path / "reference"
    _winapi.CreateJunction(str(outside), str(reference))
    handle = win32file.CreateFile(str(reference), 0x80000000, 7, None, 3, 0x02200000, None)
    try:
        reparse_data = win32file.DeviceIoControl(handle, 0x000900A8, None, 16384)
    finally:
        handle.Close()
    with pinned_directory(pinned):
        try:
            writer = win32file.CreateFile(str(pinned), 0x40000000, 7, None, 3, 0x02200000, None)
        except pywintypes.error as error:
            assert error.winerror == 32  # sharing violation, no write-capable handle
        else:
            try:
                with pytest.raises(pywintypes.error):
                    win32file.DeviceIoControl(writer, 0x000900A4, reparse_data, None)
            finally:
                writer.Close()
    assert not (pinned.lstat().st_file_attributes & 0x400)
    assert (outside / "sentinel").read_text() == "preserve"


def test_attribute_only_junction_attack_cannot_redirect_native_io(tmp_path):
    import _winapi
    import win32file
    from core.project_snapshot import pinned_directory, regular_file, _directory_handle
    from core.windows_files import windows_files

    outside, pinned = tmp_path / "outside", tmp_path / "pinned"
    outside.mkdir()
    pinned.mkdir()
    (outside / "sentinel").write_text("preserve")
    reference = tmp_path / "reference"
    _winapi.CreateJunction(str(outside), str(reference))
    handle = win32file.CreateFile(str(reference), 0x80000000, 7, None, 3, 0x02200000, None)
    try:
        payload = win32file.DeviceIoControl(handle, 0x000900A8, None, 16384)
    finally:
        handle.Close()
    with pinned_directory(pinned) as original:
        # Attribute-only access is not controlled by file sharing flags.
        attacker = win32file.CreateFile(str(pinned), 0x100, 7, None, 3, 0x02200000, None)
        try:
            win32file.DeviceIoControl(attacker, 0x000900A4, payload, None)
        finally:
            attacker.Close()
        assert pinned.lstat().st_file_attributes & 0x400
        assert list(windows_files().entries(original.handle)) == []
        with pytest.raises(SnapshotError):
            with regular_file(pinned / "sentinel"):
                pytest.fail("Must not open redirected input")
        with pytest.raises(SnapshotError):
            with regular_file(pinned / "injected.txt", create=True):
                pytest.fail("Must not create redirected output")
        with pytest.raises(SnapshotError):
            with _directory_handle(pinned / "injected-dir", create=True):
                pytest.fail("Must not create a redirected directory")
    assert not (outside / "injected.txt").exists()
    assert not (outside / "injected-dir").exists()
    assert (outside / "sentinel").read_text() == "preserve"


@pytest.mark.parametrize("names", [("A.txt", "a.txt"), ("pkg/a.py", "PKG/b.py"), ("a", "a/b")])
def test_conflicting_artifact_paths_rejected(names):
    with pytest.raises(SnapshotError):
        ProjectSnapshot(tuple(SnapshotFile(name, b"value") for name in names))


def test_native_directory_enumeration_spans_multiple_buffers(tmp_path):
    expected = []
    for index in range(300):
        name = f"item-{index:03d}-" + "x" * 90 + ".txt"
        (tmp_path / name).write_bytes(b"x")
        expected.append(name)
    snapshot = ProjectSnapshot.capture(tmp_path)
    assert [item.name for item in snapshot.files] == sorted(expected)
    assert snapshot.manifest()["bytes"] == 300


def test_mapped_remote_drive_is_refused_before_open(tmp_path, monkeypatch):
    import win32file

    monkeypatch.setattr(win32file, "GetDriveType", lambda _: 4)
    with pytest.raises(OSError, match="Remote"):
        ProjectSnapshot.capture(tmp_path)


def test_native_handle_is_closed_when_descriptor_conversion_fails(tmp_path, monkeypatch):
    import msvcrt
    import psutil

    (tmp_path / "input.txt").write_bytes(b"fixture")
    ProjectSnapshot.capture(tmp_path)  # load lazy native helpers before measurement
    process = psutil.Process()
    before = process.num_handles()

    def fail_conversion(*_):
        raise OSError("descriptor allocation failed")

    monkeypatch.setattr(msvcrt, "open_osfhandle", fail_conversion)
    for _ in range(20):
        with pytest.raises(OSError, match="descriptor allocation"):
            ProjectSnapshot.capture(tmp_path)
    assert process.num_handles() <= before + 2
