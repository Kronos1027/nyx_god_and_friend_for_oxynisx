"""Independent artifact postconditions; no LLM/model invocation."""
import hashlib

import pytest

from core.goal_contract import GoalContract, MAX_VERIFY_BYTES


def expected(path):
    return {"kind": "file_sha256", "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def witness(path, *, ok=True, verified=True, tool="write_file"):
    return {"tool": tool, "params": {"path": str(path)},
            "ok": ok, "verified": verified}


def test_exact_bytes_require_verified_write_within_authorized_root(tmp_path):
    path = tmp_path / "x.txt"
    path.write_bytes(b"hello\n")
    contract = GoalContract.parse(expected(path), [tmp_path])
    assert contract.evaluate([], [tmp_path]).reason == "no_verified_write"
    assert contract.evaluate([witness(path, tool="read_file")], [tmp_path]).reason == "no_verified_write"
    assert contract.evaluate([witness(path, verified=False)], [tmp_path]).reason == "no_verified_write"
    assert contract.evaluate([witness(path)] , [tmp_path]).passed is True


def test_modified_artifact_is_not_marked_complete(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("correct", encoding="utf-8")
    contract = GoalContract.parse(expected(path), [tmp_path])
    path.write_text("wrong", encoding="utf-8")
    result = contract.evaluate([witness(path)], [tmp_path])
    assert result.status == "UNVERIFIED" and result.reason == "hash_mismatch"


def test_missing_or_oversized_artifact_fails_closed(tmp_path):
    path = tmp_path / "a.dat"
    path.write_bytes(b"ok")
    contract = GoalContract.parse(expected(path), [tmp_path])
    path.unlink()
    assert contract.evaluate([witness(path)], [tmp_path]).reason == "file_missing"
    with path.open("wb") as fh:
        fh.truncate(MAX_VERIFY_BYTES + 1)
    assert contract.evaluate([witness(path)], [tmp_path]).reason == "file_too_large"


@pytest.mark.parametrize("payload", [
    None, "", {}, {"kind": "shell", "path": "/tmp/file", "sha256": "a" * 64},
    {"kind": "file_sha256", "path": "relative", "sha256": "a" * 64},
    {"kind": "file_sha256", "path": "/tmp/file", "sha256": "short"},
    {"kind": "file_sha256", "path": "/tmp/file", "sha256": "a" * 64, "action": "run"},
])
def test_unknown_or_untrusted_contract_rejected(tmp_path, payload):
    with pytest.raises(ValueError):
        GoalContract.parse(payload, [tmp_path])


def test_outside_root_and_symlink_escape_are_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    with pytest.raises(ValueError):
        GoalContract.parse(expected(outside), [root])
    link = root / "alias"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("OS denies test symlink")
    with pytest.raises(ValueError):
        GoalContract.parse({"kind": "file_sha256", "path": str(link),
                            "sha256": "a" * 64}, [root])


def test_revalidation_after_symlink_change(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    path = root / "x"
    path.write_text("x")
    contract = GoalContract.parse(expected(path), [root])
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("x")
    try:
        path.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("OS denies test symlink")
    assert contract.evaluate([witness(path)], [root]).reason == "outside_authorized_roots"


def test_empty_file_hash_is_valid_when_proven(tmp_path):
    path = tmp_path / "zero"
    path.touch()
    contract = GoalContract.parse(expected(path), [tmp_path])
    assert contract.evaluate([witness(path)], [tmp_path]).passed


def test_file_absent_requires_verified_delete_not_preexisting_absence(tmp_path):
    target = tmp_path / "obsolete.txt"
    contract = GoalContract.parse({"kind": "file_absent", "path": str(target)}, [tmp_path])
    assert contract.evaluate([], [tmp_path]).reason == "no_verified_delete"
    assert contract.evaluate([witness(target, tool="delete_file")], [tmp_path]).passed
    target.write_text("exists")
    assert contract.evaluate([witness(target, tool="delete_file")], [tmp_path]).reason == "file_still_exists"


def test_file_absent_rejects_wrong_witness_or_extra_fields(tmp_path):
    target = tmp_path / "x"
    contract = GoalContract.parse({"kind": "file_absent", "path": str(target)}, [tmp_path])
    assert contract.evaluate([witness(target)], [tmp_path]).reason == "no_verified_delete"
    with pytest.raises(ValueError):
        GoalContract.parse({"kind": "file_absent", "path": str(target), "sha256": "a" * 64}, [tmp_path])
