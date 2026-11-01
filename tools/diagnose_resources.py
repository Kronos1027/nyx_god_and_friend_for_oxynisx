"""Consulta única de recursos reais; --processes inclui nomes e working sets."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from core.resource_diagnostics import diagnose_resources  # noqa: E402


def collect_in_ui(include_processes):
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, Qt
    from PyQt6.QtWidgets import QApplication
    from ui.resource_diagnostics import ResourceDiagnosticsDialog

    app = QApplication([])
    dialog = ResourceDiagnosticsDialog()
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    dialog.show()
    app.processEvents()
    results = []
    started = time.monotonic()
    dialog.refresh(include_processes)
    dialog.worker.signals.finished.connect(results.append)
    deadline = started + 15
    while dialog.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    try:
        if not results:
            raise RuntimeError('O diagnóstico Qt não terminou no prazo do ensaio.')
        report = results[0]
        consumers = report.get('consumers') or {'rows': []}
        report['ui'] = {'isolated_window': True, 'elapsed_ms': round((time.monotonic()-started)*1000, 2),
                        'rows': dialog.table.rowCount(), 'passed': dialog.table.rowCount() == len(consumers['rows'])
                        and 'RAM livre:' in dialog.summary.text() and dialog.refresh_button.isEnabled()}
        preview = ROOT / 'build/previews/resource-diagnostics.png'
        preview.parent.mkdir(parents=True, exist_ok=True)
        dialog.grab().save(str(preview))
        return report
    finally:
        dialog.close()
        if not dialog.pool.waitForDone(10000):
            raise RuntimeError('Worker Qt não encerrou após o diagnóstico.')
        dialog.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        sip.delete(app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--processes', action='store_true', help='Consultar nomes e consumo de RAM dos processos, sem caminhos ou comandos.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ui', action='store_true', help='Usar diálogo Qt de produção em janela isolada fora da tela.')
    args = parser.parse_args()
    report = collect_in_ui(args.processes) if args.ui else diagnose_resources(args.processes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    # Critical pressure is an observed state; failed measurement is a driver error.
    return 1 if report['errors'] or not report.get('ui', {}).get('passed', True) else 0


if __name__ == '__main__':
    raise SystemExit(main())
