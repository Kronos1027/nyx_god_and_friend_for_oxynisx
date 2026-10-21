from concurrent.futures import ThreadPoolExecutor

import pytest

from core.evolution import EvolutionLab
from core.research import ResearchQueue, SOURCES, _Text, validate_url


def setup_queue(tmp_path):
    now = [1800000000.0]
    lab = EvolutionLab(tmp_path / "lab.db")
    return ResearchQueue(lab, clock=lambda: now[0]), lab, now


def test_persistent_budget_and_single_claim_across_workers(tmp_path):
    queue, lab, now = setup_queue(tmp_path)
    queue.enqueue("Python", SOURCES["Python"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: ResearchQueue(lab, clock=lambda: now[0])._claim(), range(4)))
    assert sum(job is not None for job in jobs) == 1
    assert queue.list_jobs()[0]["state"] == "running"
    now[0] += 1000
    assert ResearchQueue(lab, clock=lambda: now[0])._claim() is not None


def test_cancellation_during_read_does_not_create_knowledge(tmp_path):
    queue, lab, _ = setup_queue(tmp_path)
    identity = queue.enqueue("Python", SOURCES["Python"])

    def fetch(url):
        queue.cancel(identity)
        return url, "data from the internet"

    assert queue.run_one(fetch)["state"] == "cancelled"
    assert lab.overview()["knowledge_count"] == 0


def test_foreground_request_defers_read_without_committing(tmp_path):
    queue, lab, _ = setup_queue(tmp_path)
    queue.enqueue("Python", SOURCES["Python"])
    cancelled = [False]

    def fetch(url):
        cancelled[0] = True
        return url, "external content"

    assert queue.run_one(fetch, lambda: cancelled[0])["state"] == "deferred"
    assert queue.list_jobs()[0]["state"] == "queued"
    assert lab.overview()["knowledge_count"] == 0


def test_daily_budget_survives_restart_and_failed_reads(tmp_path):
    queue, lab, now = setup_queue(tmp_path)
    for i in range(4):
        queue.enqueue(f"Test {i}", SOURCES["Python"])
        assert queue.run_one(lambda url: (url, "trusted looking text"))["state"] == "completed"
        now[0] += 901
        queue = ResearchQueue(lab, clock=lambda: now[0])
    queue.enqueue("Fifth", SOURCES["Python"])
    assert queue.run_one(lambda url: (url, "more text")) is None
    assert lab.overview()["knowledge_count"] == 1


def test_error_is_terminal_and_no_infinite_retry(tmp_path):
    queue, lab, now = setup_queue(tmp_path)
    queue.enqueue("Python", SOURCES["Python"])

    def fail(url):
        raise TimeoutError("server did not answer")

    assert queue.run_one(fail)["state"] == "failed"
    now[0] += 1000
    assert queue.run_one(fail) is None
    assert lab.overview()["knowledge_count"] == 0


@pytest.mark.parametrize("url", ["http://docs.python.org", "https://docs.python.org.evil.test/", "https://127.0.0.1/", "file:///x", "https://u:p@docs.python.org/", "https://docs.python.org:8080/"])
def test_external_or_local_destinations_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_html_scripts_and_navigation_not_ingested():
    parser = _Text()
    parser.feed("<head><script>bad()</script></head><nav>menu</nav><main>study <b>this</b><script>ignore</script></main><footer>legal</footer>")
    assert parser.main_parts == ["study", "this"]


def test_seed_and_pending_requests_deduplicated(tmp_path):
    queue, _, _ = setup_queue(tmp_path)
    queue.seed_curiosity()
    queue.seed_curiosity()
    queue.enqueue("Repeated", SOURCES["Python"])
    assert len(queue.list_jobs()) == 3
