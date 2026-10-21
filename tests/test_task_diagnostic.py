from pathlib import Path
import runpy


evaluate = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/verify_task_runner.py"))["evaluate_result"]


def test_diagnostic_requires_verified_reads_and_full_numbers(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    steps = [{"tool": "read_file", "params": {"path": str(path)}, "ok": True, "verified": True}
             for path in (a, b)]
    assert evaluate(steps, "12 + 7 = 19", a, b, (12, 7)) == {
        "both_files_read": True, "expected_numbers_present": True}
    assert not evaluate(steps, "12 + 7 = 119", a, b, (12, 7))["expected_numbers_present"]
    assert evaluate(steps, "A: 12. B: 7. Soma: 19.", a, b, (12, 7))["expected_numbers_present"]
    assert not evaluate(steps, "12.5 + 7 = 19.5", a, b, (12, 7))["expected_numbers_present"]
    assert not evaluate([], "12 + 7 = 19", a, b, (12, 7))["both_files_read"]
    steps[0]["verified"] = False
    assert not evaluate(steps, "12 + 7 = 19", a, b, (12, 7))["both_files_read"]


def test_diagnostic_does_not_count_wrong_tool(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    steps = [{"tool": "write_file", "params": {"path": str(path)}, "ok": True, "verified": True}
             for path in (a, b)]
    assert not evaluate(steps, "12 7 19", a, b, (12, 7))["both_files_read"]
