import threading
import time

from PyQt6.QtCore import QEventLoop, QThreadPool, QTimer
from PyQt6.QtWidgets import QApplication

from ui.overlay import _ConfirmationWorker, _PromptWorker


def test_prompt_worker_runs_off_the_calling_thread():
    app = QApplication.instance() or QApplication([])  # noqa: F841
    class SlowLoop:
        worker_thread_id = None

        def process(self, prompt):
            self.worker_thread_id = threading.get_ident()
            time.sleep(0.05)
            return prompt

    loop = SlowLoop()
    pool = QThreadPool()
    worker = _PromptWorker(loop, "olá")
    pool.start(worker)

    wait = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: wait.quit() if pool.activeThreadCount() == 0 else None)
    poll.start(5)
    QTimer.singleShot(2000, wait.quit)
    wait.exec()

    assert pool.activeThreadCount() == 0
    assert loop.worker_thread_id is not None
    assert loop.worker_thread_id != threading.get_ident()


def test_approved_action_runs_off_the_calling_thread():
    app = QApplication.instance() or QApplication([])  # noqa: F841

    class SlowLoop:
        worker_thread_id = None

        def confirm_pending(self, pending_action, approved):
            self.worker_thread_id = threading.get_ident()
            time.sleep(0.05)
            return {"action": pending_action, "approved": approved}

    loop = SlowLoop()
    pool = QThreadPool()
    worker = _ConfirmationWorker(loop, {"type": "write_file"})
    pool.start(worker)

    wait = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: wait.quit() if pool.activeThreadCount() == 0 else None)
    poll.start(5)
    QTimer.singleShot(2000, wait.quit)
    wait.exec()

    assert pool.activeThreadCount() == 0
    assert loop.worker_thread_id is not None
    assert loop.worker_thread_id != threading.get_ident()
