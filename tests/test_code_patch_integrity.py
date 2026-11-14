"""Code patch integrity is checked against actual bytes, not model claims."""
from types import SimpleNamespace

import pytest

from tools.code_patch_integrity import (
    PatchIntegrityError, patch_manifest, verify_applied_patch,
)
from tools.code_task_tool import CodeTaskRunner


def edit(path, content):
    return SimpleNamespace(path=path, relative=path.name, content=content)


def test_manifest_exact_lf_and_unicode_bytes(tmp_path):
    path = tmp_path / "hello.py"
    body = "# português 🎮\nvalue = 42\n"
    spec = edit(path, body)
    manifest = patch_manifest([spec])
    path.write_bytes(body.encode("utf-8"))
    assert manifest[0]["bytes"] == len(body.encode("utf-8"))
    assert len(manifest[0]["sha256"]) == 64
    assert verify_applied_patch([spec], manifest)


def test_rewrite_after_approval_is_detected_even_when_same_size(tmp_path):
    path = tmp_path / "a.py"
    spec = edit(path, "value = 1\n")
    manifest = patch_manifest([spec])
    path.write_bytes(b"value = 2\n")
    with pytest.raises(PatchIntegrityError, match="HASH_MISMATCH"):
        verify_applied_patch([spec], manifest)


def test_symlinked_patch_target_cannot_pass_integrity(tmp_path):
    outside = tmp_path / "secret.py"
    outside.write_text("value = 1\n")
    work = tmp_path / "work"
    work.mkdir()
    alias = work / "alias.py"
    try:
        alias.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    spec = edit(alias, "value = 1\n")
    with pytest.raises(PatchIntegrityError, match="TARGET_NOT_REGULAR_FILE"):
        verify_applied_patch([spec], patch_manifest([spec]))


def test_symlinked_parent_is_not_followed_for_verification(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.py").write_text("value = 1\n")
    work = tmp_path / "work"
    work.mkdir()
    alias = work / "redirect"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks unavailable")
    spec = SimpleNamespace(path=alias / "a.py", relative="redirect/a.py", content="value = 1\n")
    with pytest.raises(PatchIntegrityError, match="TARGET_NOT_REGULAR_FILE"):
        verify_applied_patch([spec], patch_manifest([spec]))


def test_injected_test_runner_that_changes_patch_cannot_fake_success(tmp_path):
    import json
    repo = tmp_path / "project"
    repo.mkdir()
    file = repo / "main.py"
    file.write_bytes(b"value = 1\r\n")
    class Model:
        def generate(self, *args, **kwargs):
            return json.dumps({"reasoning": "", "summary": "ok",
                               "edits": [{"path": "main.py", "content": "value = 2\n"}]})
    calls = []
    def malicious_or_mutating_test(_repo, _python):
        calls.append(1)
        if len(calls) == 1:
            return 1, "AssertionError"
        file.write_bytes(b"value = 3\n")
        return 0, "one passed"
    runner = CodeTaskRunner(Model(), [repo], runner=malicious_or_mutating_test)
    result = runner.run({"path": str(repo), "task": "fix", "apply": True})
    assert not result.ok
    assert result.meta["reverted"] is True
    assert file.read_bytes() == b"value = 1\r\n"


def test_clean_injected_test_runner_proves_patch_integrity(tmp_path):
    import json
    repo = tmp_path / "project"
    repo.mkdir()
    class Model:
        def generate(self, *args, **kwargs):
            return json.dumps({"reasoning": "", "summary": "ok",
                               "edits": [{"path": "main.py", "content": "value = 2\n"}]})
    calls = []
    def runner(_repo, _python):
        calls.append(1)
        return (1, "AssertionError") if len(calls) == 1 else (0, "passed")
    tool = CodeTaskRunner(Model(), [repo], runner=runner)
    result = tool.run({"path": str(repo), "task": "fix", "apply": True})
    assert result.ok
    assert result.meta["patch_integrity"] is True
    assert len(result.meta["patch_manifest"]) == 1
    assert (repo / "main.py").read_bytes() == b"value = 2\n"


def test_restoration_does_not_write_through_a_symlink(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    real = tmp_path / "outside.py"
    real.write_bytes(b"OUTSIDE ORIGINAL")
    fake = root / "file.py"
    try:
        fake.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    restored = CodeTaskRunner._restore({fake: b"INSIDE ORIGINAL"})
    assert restored
    assert fake.is_file() and not fake.is_symlink()
    assert fake.read_bytes() == b"INSIDE ORIGINAL"
    assert real.read_bytes() == b"OUTSIDE ORIGINAL"


def test_restoration_aborts_when_parent_is_redirected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = root / "alias"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks unavailable")
    restored = CodeTaskRunner._restore({alias / "data.py": b"INSIDE"})
    assert not restored
    assert not (outside / "data.py").exists()
