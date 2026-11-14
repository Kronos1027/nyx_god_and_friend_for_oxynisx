"""Static code preflight: no project code is ever run during inspection."""
import json
from types import SimpleNamespace

import pytest

from tools.code_patch_preflight import (
    MAX_SOURCE_BYTES, PatchPreflightError, check_edit_batch,
    check_source, inspect_existing_files,
)
from tools.code_task_tool import CodeTaskRunner


def plan(edits):
    return json.dumps({"reasoning": "", "summary": "repair", "edits": edits})


class FakeModel:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return self.output


def test_python_ast_never_executes_source(tmp_path):
    marker = tmp_path / "should_not_exist.txt"
    content = f"from pathlib import Path\nPath({str(marker)!r}).write_text('UNSAFE')\n"
    result = check_source("code.py", content)
    assert result["status"] == "PARSED"
    assert result["format"] == "python"
    assert not marker.exists()


@pytest.mark.parametrize(("relative", "content", "code"), [
    ("syntax.py", "def invalid(:\n pass\n", "PYTHON_SYNTAX"),
    ("bad.json", '{"name": ', "JSON_SYNTAX"),
    ("duplicates.json", '{"name": 1, "name": 2}', "JSON_DUPLICATE_KEY"),
    ("bad.toml", "key = [1, \n", "TOML_SYNTAX"),
])
def test_bad_sources_fail_with_bounded_error_without_original_text(relative, content, code):
    with pytest.raises(PatchPreflightError) as found:
        check_source(relative, content)
    assert found.value.code == code
    assert content not in str(found.value)


def test_unsupported_format_is_not_credited_as_valid():
    for path in ("note.md", "config.yaml", "config.yml", "config.cfg", "a.txt"):
        result = check_source(path, "might be invalid arbitrary content")
        assert result["status"] == "UNSCANNED"


def test_max_source_bytes_enforced():
    with pytest.raises(PatchPreflightError, match="SOURCE_TOO_LARGE"):
        check_source("a.py", "x" * (MAX_SOURCE_BYTES + 1))


def test_edits_batch_rejects_case_insensitive_duplicates():
    edits = [
        SimpleNamespace(relative="src/Main.py", content="x = 1\n"),
        SimpleNamespace(relative="src/main.PY", content="y = 2\n"),
    ]
    with pytest.raises(PatchPreflightError, match="DUPLICATE_TARGET"):
        check_edit_batch(edits)


def test_edit_batch_reports_all_formats_without_claiming_unscanned_validity():
    edits = [
        SimpleNamespace(relative="a.py", content="x = 1\n"),
        SimpleNamespace(relative="config.json", content='{"ok":true}'),
        SimpleNamespace(relative="readme.md", content="Free text"),
    ]
    results = check_edit_batch(edits)
    assert [r["status"] for r in results] == ["PARSED", "PARSED", "UNSCANNED"]


def test_readonly_preflight_does_not_call_model_or_executor(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "cfg.toml").write_text("ok = true\n", encoding="utf-8")
    model = FakeModel("should not be called")
    calls = []
    runner = CodeTaskRunner(model, [repo], runner=lambda *args: calls.append(True))
    output = runner.run({"path": str(repo), "operation": "preflight",
                         "files": ["app.py", "cfg.toml"]})
    assert output.ok
    assert model.calls == 0 and not calls
    assert output.meta["tests_executed"] is False
    assert all(x["status"] == "PARSED" for x in output.meta["checks"])


def test_readonly_preflight_rejects_apply(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    model = FakeModel("")
    runner = CodeTaskRunner(model, [repo])
    result = runner.run({"path": str(repo), "operation": "preflight",
                         "files": ["a.py"], "apply": True})
    assert not result.ok
    assert model.calls == 0


def test_readonly_preflight_rejects_symlink_escape_and_traversal(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text("password='dontread'")
    for path in ("../secret.py", "/tmp/secret.py", "C:/secret.py"):
        with pytest.raises(PatchPreflightError):
            inspect_existing_files(repo, [path])
    alias = repo / "alias.py"
    try:
        alias.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Filesystem does not permit symlinks")
    with pytest.raises(PatchPreflightError, match="SYMLINK_DISALLOWED"):
        inspect_existing_files(repo, ["alias.py"])


def test_inspection_refuses_large_and_invalid_encoding(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "big.py").write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    (repo / "invalid.py").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PatchPreflightError, match="FILE_NOT_SMALL_REGULAR_FILE"):
        inspect_existing_files(repo, ["big.py"])
    with pytest.raises(PatchPreflightError, match="FILE_NOT_READABLE"):
        inspect_existing_files(repo, ["invalid.py"])


def test_invalid_model_patch_never_changes_real_project_even_with_injected_runner(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    original = repo / "app.py"
    original.write_text("x = 1\n", encoding="utf-8")
    llm = FakeModel(plan([{"path": "app.py", "content": "def broken(:\n pass\n"}]))
    calls = []
    def test_runner(*args):
        calls.append(True)
        return (1, "one existing test failed")
    runner = CodeTaskRunner(llm, [repo], runner=test_runner)
    response = runner.run({"path": str(repo), "task": "correct syntax", "apply": True})
    assert not response.ok
    assert original.read_text() == "x = 1\n"
    assert len(calls) == 1


def test_proposed_patch_is_preflighted_without_executing_tests(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    llm = FakeModel(plan([{"path": "app.py", "content": "x = 1\n"}]))
    runner = CodeTaskRunner(llm, [repo])
    response = runner.run({
        "path": str(repo), "task": "fix", "operation": "propose",
        "test_output": "AssertionError from user-provided report",
    })
    assert response.ok
    assert response.meta["tests_executed"] is False
    assert response.meta["preflight_checks"][0]["status"] == "PARSED"
    assert not (repo / "app.py").exists()


def test_compatibility_existing_injected_test_runner_still_returns_provenance(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    runner = CodeTaskRunner(FakeModel("never called"), [repo],
                            runner=lambda _repo, _python: (0, "tests: 1 passed"))
    response = runner.run({"path": str(repo), "task": "check"})
    assert response.ok
    assert response.meta["test_execution_source"] == "injected_executor"
    assert response.meta["test_exit_code"] == 0
    assert response.meta["tests_executed"] is True


def test_no_isolation_backend_still_refuses_arbitrary_project_test_execution(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    marker = tmp_path / "unsafe_effect.txt"
    (repo / "conftest.py").write_text(
        f"open({str(marker)!r}, 'w').write('untrusted')", encoding="utf-8",
    )
    runner = CodeTaskRunner(FakeModel(""), [repo])
    result = runner.run({"path": str(repo), "task": "run tests"})
    assert not result.ok
    assert "isolamento real" in result.error
    assert not marker.exists()



def test_cli_provides_offline_python_check_without_running_project(tmp_path, capsys):
    import importlib.util
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    cli_path = __import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "nyx_code_preflight.py"
    spec = importlib.util.spec_from_file_location("nyx_preflight_cli", cli_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--repo", str(root), "app.py"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tests_executed"] is False
    assert report["ok"] is True
    assert report["checked"] == 1


def test_cli_returns_nonzero_for_unsupported_or_invalid_source(tmp_path, capsys):
    import importlib.util
    root = tmp_path / "project"
    root.mkdir()
    (root / "unsupported.yaml").write_text("a: v", encoding="utf-8")
    (root / "broken.py").write_text("def broken(:", encoding="utf-8")
    cli_path = __import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "nyx_code_preflight.py"
    spec = importlib.util.spec_from_file_location("nyx_preflight_cli2", cli_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--repo", str(root), "unsupported.yaml"]) == 1
    assert json.loads(capsys.readouterr().out)["unscanned"] == 1
    assert module.main(["--repo", str(root), "broken.py"]) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "PYTHON_SYNTAX"
