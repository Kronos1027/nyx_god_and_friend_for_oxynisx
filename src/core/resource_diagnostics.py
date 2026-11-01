"""One-shot resource inspection. Process names are opt-in, never sampled in idle."""
from dataclasses import asdict
import time

from core.resource_profiles import profile_name
from core.runtime_budget import resource_snapshot, ensure_resource_headroom, InferencePressureError


def memory_consumers(limit=6, max_seconds=1.0):
    """Group working sets by executable name; shared pages may be counted twice.

    The time budget is cooperative between OS calls, not a hard syscall timeout.
    Never reads command lines, paths, windows, files or environment variables.
    """
    import psutil

    started = time.monotonic()
    groups, scanned, unavailable, truncated = {}, 0, 0, False
    for process in psutil.process_iter(['name', 'memory_info'], ad_value=None):
        if time.monotonic() - started >= max_seconds or scanned >= 4096:
            truncated = True
            break
        scanned += 1
        # psutil <=7 uses info; newer versions expose a read-only snapshot.
        info = getattr(process, 'info', None)
        if isinstance(info, dict):
            name, memory = info.get('name'), info.get('memory_info')
        else:
            snapshot = getattr(process, 'snapshot', None)
            name, memory = getattr(snapshot, 'name', None), getattr(snapshot, 'memory_info', None)
        rss = getattr(memory, 'rss', None)
        if not isinstance(name, str) or type(rss) is not int or rss <= 0:
            unavailable += 1
            continue
        name = ''.join(c for c in name if c.isprintable()).replace('\\', '/').rsplit('/', 1)[-1][:80].strip()
        if not name:
            unavailable += 1
            continue
        key = name.casefold()
        row = groups.setdefault(key, {'name': name, 'processes': 0, 'rss_bytes': 0})
        row['processes'] += 1
        row['rss_bytes'] += rss
    return {'rows': sorted(groups.values(), key=lambda row: row['rss_bytes'], reverse=True)[:max(0, min(limit, 20))],
            'scanned': scanned, 'unavailable': unavailable, 'truncated': truncated,
            'elapsed_ms': round((time.monotonic() - started) * 1000, 2), 'metric': 'RSS / working set'}


def diagnose_resources(include_processes=False):
    started = time.monotonic()
    snapshot = resource_snapshot()
    try:
        ensure_resource_headroom(snapshot)
        reason = 'Pisos críticos preservados; o modelo ainda depende do orçamento de carga e contexto.'
        critical = False
    except InferencePressureError as exc:
        reason, critical = str(exc), True
    report = {'profile': profile_name(), 'resources': asdict(snapshot),
              'critical_pressure': critical, 'reason': reason, 'processes_requested': include_processes,
              'consumers': None, 'errors': []}
    if include_processes:
        try:
            report['consumers'] = memory_consumers()
        except Exception as exc:
            report['errors'].append('Consulta de processos indisponível: ' + type(exc).__name__)
    report['elapsed_ms'] = round((time.monotonic() - started) * 1000, 2)
    return report
