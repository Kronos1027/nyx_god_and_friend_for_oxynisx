"""Code loop: proposals, safe paths, backups and rollback."""

import json


from tools.code_task_tool import CodeTaskRunner


def plan(edits, summary="ok"):
    return json.dumps({"reasoning": "", "edits": edits, "summary": summary})


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, user_input, history=None):
        self.calls += 1
        if not self.replies:
            return plan([])
        return self.replies.pop(0)


def build(tmp_path, results, replies):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    llm = FakeLLM(replies)
    calls = {"count": 0}

    def runner(_repo, _python):
        calls["count"] += 1
        index = min(calls["count"] - 1, len(results) - 1)
        return results[index]

    return CodeTaskRunner(llm, [repo], runner=runner), repo, llm, calls


def test_passing_tests_do_not_call_the_model(tmp_path):
    runner, repo, llm, _ = build(tmp_path, [(0, "3 passed")], [])

    result = runner.run({"path": str(repo), "task": "corrija"})

    assert result.ok is True
    assert "passaram" in result.output
    assert llm.calls == 0


def test_failing_tests_return_a_proposal_without_writing(tmp_path):
    runner, repo, llm, _ = build(
        tmp_path, [(1, "AssertionError: expected 4")], [plan([{"path": "sum.py", "content": "def add(a, b):\n    return a + b\n"}])],
    )

    result = runner.run({"path": str(repo), "task": "conserte add"})

    assert result.ok is True
    assert result.meta["applied"] is False
    assert result.meta["proposed"][0]["path"] == "sum.py"
    assert not (repo / "sum.py").exists()
    assert llm.calls == 1


def test_apply_writes_and_retries_until_green(tmp_path):
    runner, repo, llm, calls = build(
        tmp_path,
        [(1, "AssertionError: expected 4"), (0, "1 passed")],
        [plan([{"path": "sum.py", "content": "def add(a, b):\n    return a + b\n"}])],
    )

    result = runner.run({"path": str(repo), "task": "conserte add", "apply": True})

    assert result.ok is True
    assert result.meta["passed"] is True
    assert calls["count"] == 2
    assert (repo / "sum.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


def test_paths_outside_the_repository_are_rejected(tmp_path):
    runner, repo, _, _ = build(
        tmp_path, [(1, "fail")], [plan([{"path": "../escape.py", "content": "x = 1\n"}])],
    )

    result = runner.run({"path": str(repo), "task": "corrija", "apply": True})

    assert result.ok is False
    assert "fora do repositório" in result.error
    assert not (tmp_path / "escape.py").exists()


def test_disallowed_file_types_are_rejected(tmp_path):
    runner, repo, _, _ = build(
        tmp_path, [(1, "fail")], [plan([{"path": "payload.exe", "content": "MZ"}])],
    )

    result = runner.run({"path": str(repo), "task": "corrija"})

    assert result.ok is False
    assert "não permitido" in result.error


def test_empty_plan_is_an_error(tmp_path):
    runner, repo, _, _ = build(tmp_path, [(1, "fail")], [plan([])])

    result = runner.run({"path": str(repo), "task": "corrija"})

    assert result.ok is False
    assert "nenhuma edição" in result.error


def test_failed_rounds_restore_the_original_files(tmp_path):
    runner, repo, _, _ = build(
        tmp_path,
        [(1, "fail 1"), (1, "fail 2")],
        [
            plan([{"path": "sum.py", "content": "def add(a, b):\n    return a - b\n"}]),
            plan([{"path": "sum.py", "content": "def add(a, b):\n    return 0\n"}]),
        ],
    )
    original = "def add(a, b):\n    return 0\n"
    (repo / "sum.py").write_text(original, encoding="utf-8")

    result = runner.run({"path": str(repo), "task": "conserte", "apply": True, "max_rounds": 2})

    assert result.ok is False
    assert result.meta["reverted"] is True
    assert (repo / "sum.py").read_text(encoding="utf-8") == original


def test_repository_outside_allowed_roots_is_refused(tmp_path):
    inside = tmp_path / "inside"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    runner = CodeTaskRunner(FakeLLM([]), [inside])

    result = runner.run({"path": str(outside), "task": "corrija"})

    assert result.ok is False
    assert "raízes permitidas" in result.error


def test_frozen_app_runs_tests_with_an_external_python(monkeypatch):
    from tools import code_task_tool

    monkeypatch.setattr(code_task_tool.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        code_task_tool.shutil, "which",
        lambda name: r"C:\Python311\python.exe" if name == "python" else None,
    )
    assert code_task_tool.CodeTaskRunner.python_executable() == r"C:\Python311\python.exe"


def test_source_run_uses_the_current_interpreter(monkeypatch):
    from tools import code_task_tool

    monkeypatch.setattr(code_task_tool.sys, "frozen", False, raising=False)
    assert code_task_tool.CodeTaskRunner.python_executable() == code_task_tool.sys.executable


def test_project_virtualenv_is_preferred_over_path(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".venv" / "Scripts").mkdir(parents=True)
    interpreter = repo / ".venv" / "Scripts" / "python.exe"
    interpreter.write_text("", encoding="utf-8")

    runner = CodeTaskRunner(FakeLLM([]), [repo])

    assert runner._resolve_python(repo) == str(interpreter)


def test_explicit_interpreter_must_exist(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CodeTaskRunner(FakeLLM([]), [repo], runner=lambda _repo, _python: (0, ""))

    result = runner.run({"path": str(repo), "task": "x", "python": str(tmp_path / "missing-python.exe")})

    assert result.ok is False
    assert "interpretador" in result.error.lower()
