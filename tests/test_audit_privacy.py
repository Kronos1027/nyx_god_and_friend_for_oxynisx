"""Audit JSONL retains diagnostic outcomes, not private text or tool content."""
import json

from audit.logger import AuditLogger
from audit.privacy import safe_audit_payload


def test_decision_record_is_private_but_preserves_operational_outcome(tmp_path):
    logger = AuditLogger(tmp_path)
    question = "Confira meu password=VERY_PRIVATE"
    answer = '{"speech_output":"PRIVATE ANSWER","action":{"type":"write_file"}}'
    entry = logger.log_decision(
        user_input=question, response_raw=answer, parse_ok=True, parse_error=None,
        action_type="write_file", action_params={
            "path": "C:/Users/private/doc.txt", "content": "SUPERSECRET PRIVATE"
        },
        requires_confirmation=True, executed=False, result_ok=None,
        result_output="PRIVATE TOOL RESULT", mode="assistida",
    )
    raw = logger.path.read_text(encoding="utf-8")
    for sensitive in ("VERY_PRIVATE", "PRIVATE ANSWER", "SUPERSECRET",
                      "PRIVATE TOOL RESULT", "C:/Users/private"):
        assert sensitive not in raw
    saved = json.loads(raw)
    assert saved["event"] == "decision"
    assert saved["parse_ok"] is True
    assert saved["action_type"] == "write_file"
    assert saved["requires_confirmation"] is True
    assert saved["executed"] is False
    assert saved["mode"] == "assistida"
    assert saved["action_params"]["type"] == "object"
    assert entry == saved


def test_task_finish_metrics_remain_after_scrubbing_step_payload(tmp_path):
    logger = AuditLogger(tmp_path)
    logger.log_event("task_finished", task_id="t1",
                     steps=[{"tool": "write_file", "params": {"path": "/private", "content": "SECRET"},
                             "output": "api_key=VERYPRIVATE", "ok": True}],
                     model_usage={"output_count": 140}, verified_actions=1)
    raw = logger.path.read_text()
    assert "VERYPRIVATE" not in raw and '"content": "SECRET"' not in raw
    saved = logger.read_all()[0]
    assert saved["steps"] == {"type": "array", "items": 1}
    assert saved["model_usage"]["output_count"] == 140
    assert saved["verified_actions"] == 1


def test_started_tool_action_logs_no_paths_or_payload(tmp_path):
    logger = AuditLogger(tmp_path)
    logger.log_event("task_action_started", tool="write_file", task_id="t2",
                     params={"path": "/private/diary.txt",
                             "content": "MY SECRET WRITING"})
    raw = logger.path.read_text()
    assert "MY SECRET WRITING" not in raw
    assert "/private/diary.txt" not in raw
    assert logger.read_all()[0]["tool"] == "write_file"


def test_plain_text_credential_is_redacted_for_other_events():
    clean = safe_audit_payload("tool_failed", {
        "error": "password=HIDDEN token=SHOULD_HIDE",
        "ok": False,
        "attempt": 3,
    })
    assert "HIDDEN" not in str(clean)
    assert "SHOULD_HIDE" not in str(clean)
    assert clean["ok"] is False and clean["attempt"] == 3


def test_security_detail_is_always_omitted():
    item = safe_audit_payload("security", {
        "code": "permission_denied", "detail": "User path and secret",
        "allowed": False,
    })
    assert item["code"] == "permission_denied"
    assert item["allowed"] is False
    assert "User path" not in repr(item)


def test_freeform_errors_and_summaries_do_not_leak_private_paths(tmp_path):
    logger = AuditLogger(tmp_path)
    logger.log_event("task_failed",
                     error="C:/Users/Private/secret_project",
                     summary="Do not disclose internal workspace",
                     status="FAILED", verified_actions=0)
    raw = logger.path.read_text(encoding="utf-8")
    assert "secret_project" not in raw
    assert "internal workspace" not in raw
    assert logger.read_all()[0]["status"] == "FAILED"
    assert logger.read_all()[0]["verified_actions"] == 0
