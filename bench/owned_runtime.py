"""Start installed Ollama on a dedicated local endpoint; stop only owned PIDs."""
from contextlib import contextmanager
import os
import subprocess

import psutil


@contextmanager
def isolated_runtime(port=11435):
    from core import ollama_service
    host = f'http://127.0.0.1:{port}'
    previous = os.environ.get('NYX_OLLAMA_HOST')
    os.environ['NYX_OLLAMA_HOST'] = host
    process, created = None, None
    try:
        state = ollama_service.ensure_local_ollama(timeout=15)
        if not state.ready:
            raise RuntimeError(state.reason)
        if state.started_by_nyx:
            process = ollama_service._owned_process
            created = psutil.Process(process.pid).create_time()
        yield host
    finally:
        if process is not None and created is not None:
            try:
                root = psutil.Process(process.pid)
                if root.create_time()==created:
                    owned = [(item,item.create_time()) for item in root.children(recursive=True)]
                    for item,born in reversed(owned):
                        if born>=created and item.create_time()==born:
                            item.terminate()
                    root.terminate()
                    process.wait(timeout=10)
            except (psutil.Error,TimeoutError,subprocess.TimeoutExpired):
                pass
        if previous is None:
            os.environ.pop('NYX_OLLAMA_HOST',None)
        else:
            os.environ['NYX_OLLAMA_HOST'] = previous
