"""Model usage metrics: fixed storage, no raw prompts, durable restart."""
import json

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OllamaClient
from core.task_journal import TaskJournal
from core.task_runner import TaskRunner
from core.task_usage import accumulate_usage, clean_usage, empty_usage, usage_summary
from tools.registry import ToolRegistry


def answer():
    return json.dumps({"emotion": "idle", "speech_output": "SQLite é um banco local",
                       "action": {"type": "none", "params": {}},
                       "requires_confirmation": False})


def report():
    return [{"valid_json": True, "prompt_eval_count": 120,
             "prompt_eval_cached_count": 80, "eval_count": 40,
             "total_duration_ns": 1_000_000_000,
             "load_duration_ns": 100_000_000,
             "eval_duration_ns": 800_000_000}]


def test_usage_aggregates_and_excludes_secrets():
    totals = accumulate_usage(empty_usage(), report() + [{"valid_json": False,
         "prompt_eval_count": True, "eval_count": -5, "secret": "HIDDEN"}])
    assert totals["generation_attempts"] == 2
    assert totals["valid_json"] == 1
    assert totals["invalid_json"] == 1
    assert totals["output_tokens"] == 40
    assert totals["prompt_tokens"] == 120
    assert totals["cached_prompt_tokens"] == 80
    assert usage_summary(totals)["generation_tokens_per_second"] == 50
    assert "HIDDEN" not in json.dumps(totals)
    assert clean_usage({"output_tokens": "fake", "secret": "leak"}) == empty_usage()


def test_runner_records_usage_without_storing_the_answer(tmp_path):
    class FakeLLM:
        @property
        def generation_report(self):
            return report()
        def generate(self, prompt, **kwargs):
            return answer()

    audit = AuditLogger(tmp_path / "audit")
    loop = AgentLoop(FakeLLM(), ToolRegistry(), audit)
    runner = TaskRunner(loop)
    result = runner.start("Explique SQLite")
    assert result.response.speech_output.startswith("SQLite")
    assert runner.model_usage["generation_attempts"] == 1
    assert runner.model_usage["output_tokens"] == 40
    ended = [item for item in audit.read_all() if item.get("event") == "task_finished"]
    assert ended and ended[-1]["model_usage"]["prompt_tokens"] == 120
    assert "SQLite é um banco" not in json.dumps(ended[-1]["model_usage"])


def test_task_usage_survives_pause_and_restart(tmp_path):
    db_path = tmp_path / "journal.db"
    journal = TaskJournal(db_path)
    audit = AuditLogger(tmp_path / "audit")
    class Pausing:
        @property
        def generation_report(self):
            return report()
        def generate(self, prompt, **kwargs):
            runner.pause()
            return answer()
    loop = AgentLoop(Pausing(), ToolRegistry(), audit)
    runner = TaskRunner(loop, journal=journal)
    runner.start("Explique SQLite")
    task_id = runner.task_id
    assert journal.get(task_id)["state"] == "PAUSED"
    assert journal.get(task_id)["model_usage"]["output_tokens"] == 40
    journal.close()

    class Finish:
        @property
        def generation_report(self):
            return report()
        def generate(self, prompt, **kwargs):
            return answer()
    other = TaskJournal(db_path)
    resumed = TaskRunner(AgentLoop(Finish(), ToolRegistry(), AuditLogger(tmp_path / "second")),
                         journal=other)
    resumed.continue_task(task_id)
    assert resumed.model_usage["output_tokens"] == 80
    assert other.get(task_id)["model_usage"]["generation_attempts"] == 2
    other.close()


def test_ollama_usage_and_seed_are_extracted_without_network(monkeypatch):
    received = []
    def fake_request(url, payload, timeout):
        received.append(payload)
        return {"done": True, "done_reason": "stop",
                "message": {"content": answer()},
                "eval_count": 40, "prompt_eval_count": 120,
                "prompt_eval_cached_count": 80,
                "eval_duration": 800_000_000,
                "total_duration": 1_000_000_000,
                "load_duration": 100_000_000}
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", fake_request)
    client = OllamaClient(model="test-model", seed=42)
    result = client.generate("Explique SQLite")
    assert result == answer()
    assert received[0]["options"]["seed"] == 42
    metrics = client.generation_report[0]
    assert metrics["output_tokens_per_second"] == 50
    assert metrics["total_duration_ns"] == 1_000_000_000
    assert metrics["prompt_eval_cached_count"] == 80
