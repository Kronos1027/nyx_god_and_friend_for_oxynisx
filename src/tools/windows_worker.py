"""Trusted UIA worker. No Qt, model-generated code, or arbitrary commands."""
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.operation_control import OperationControl
from tools.windows_targets import UIATargets, focus, select_window, uia_context


def serve():
    control = OperationControl()
    targets = UIATargets(control)
    with uia_context():
        for line in sys.stdin:
            if len(line) > 131072:
                return 2
            request = json.loads(line)
            targets.mutation_started = False
            try:
                params = request["params"]
                if request["verb"] == "inspect":
                    data = targets.inspect(params)
                elif request["verb"] == "act":
                    data = targets.act(params["action"], params["params"])
                elif request["verb"] == "focus":
                    window = select_window(params)
                    focus(window, control)
                    data = {"hwnd": window._hWnd, "title": window.title, "verified": True}
                else:
                    raise ValueError("Operação UIA desconhecida.")
                response = {"id": request["id"], "data": data}
            except Exception as exc:
                response = {"id": request["id"], "error": str(exc)[:1000],
                            "outcome_unknown": targets.mutation_started}
            print(json.dumps(response, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
