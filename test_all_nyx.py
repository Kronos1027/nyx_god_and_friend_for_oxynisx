"""
Nyx - Teste REAL e COMPLETO de todas as ferramentas
"""
import sys, json, os, tempfile, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
os.environ["PYTHONUTF8"] = "1"

PASS = "OK"
FAIL = "FAIL"
WARN = "WARN"
results = {}

def section(title):
    print()
    print("=" * 65)
    print(f"  {title}")
    print("=" * 65)

def ok(name, detail=""):
    print(f"  [OK] {name}" + (f": {detail}" if detail else ""))
    results[name] = "PASS"

def fail(name, detail=""):
    print(f"  [FAIL] {name}: {detail}")
    results[name] = "FAIL"

def warn(name, detail=""):
    print(f"  [WARN] {name}: {detail}")
    results[name] = "WARN"

tmpdir = Path(tempfile.mkdtemp(prefix="nyx_test_"))

# ──────────────────────────────────────────────
section("1. SCHEMA / VALIDACAO JSON (defesa LLM)")
# ──────────────────────────────────────────────
from core.llm_client import validate_payload, parse_response, SchemaValidationError

valid_payload = {
    "reasoning": "Teste.",
    "alternative_suggestion": None,
    "emotion": "talk",
    "action": {"type": "none", "params": {}},
    "requires_confirmation": False,
    "confirmation_prompt": None,
    "speech_output": "Ola!",
}
try:
    r = validate_payload(valid_payload)
    ok("schema_valid_payload", f"emotion={r.emotion} action={r.action.type}")
except Exception as e:
    fail("schema_valid_payload", str(e))

bad = dict(valid_payload, emotion="raiva")
try:
    validate_payload(bad)
    fail("schema_rejects_bad_emotion")
except SchemaValidationError:
    ok("schema_rejects_bad_emotion")

r = parse_response("isso nao e json {{{")
if not r.parse_ok and r.action.type == "none":
    ok("schema_safe_fallback", "json invalido -> action=none")
else:
    fail("schema_safe_fallback")

# ──────────────────────────────────────────────
section("2. SHELL TOOL (allowlist + PowerShell)")
# ──────────────────────────────────────────────
from tools.shell_tool import ShellTool, ShellBlockedError

shell = ShellTool(dialect="powershell", timeout=20)

r = shell.run_template("LIST_DIR", {"path": "."})
if r.ok and r.output:
    ok("shell_list_dir", f"{len(r.output.splitlines())} linhas")
elif r.ok:
    warn("shell_list_dir", "executou mas sem output")
else:
    fail("shell_list_dir", r.error)

r = shell.run_template("DISK_FREE", {})
if r.ok:
    ok("shell_disk_free", r.output.strip().splitlines()[0] if r.output else "sem saida")
else:
    fail("shell_disk_free", r.error)

r = shell.run_template("GET_PROCESS", {})
if r.ok and r.output:
    ok("shell_get_process", f"{len(r.output.splitlines())} linhas")
else:
    fail("shell_get_process", r.error or "sem output")

r = shell.run_template("GET_FILE_INFO", {"path": "pyproject.toml"})
if r.ok and r.output:
    ok("shell_get_file_info", r.output.strip().splitlines()[0])
else:
    fail("shell_get_file_info", r.error or "sem output")

try:
    shell.run_template("LIST_DIR", {"path": "; rm -rf /"})
    fail("shell_injection_blocked")
except ShellBlockedError:
    ok("shell_injection_blocked")

try:
    shell.run_template("LIST_DIR", {"path": "../../etc"})
    fail("shell_traversal_blocked")
except ShellBlockedError:
    ok("shell_traversal_blocked")

try:
    shell.run_template("EXEC_ARBITRARY", {"cmd": "whoami"})
    fail("shell_unknown_template_blocked")
except ShellBlockedError:
    ok("shell_unknown_template_blocked")

if shell.is_destructive("KILL_PROCESS_BY_NAME"):
    ok("shell_destructive_flag")
else:
    fail("shell_destructive_flag")

# ──────────────────────────────────────────────
section("3. FILE TOOL (sandbox)")
# ──────────────────────────────────────────────
from tools.file_tool import FileTool

ft = FileTool(allowed_roots=[tmpdir])

r = ft.write_file({"path": str(tmpdir / "hello.txt"), "content": "Ola Nyx!"})
if r.ok:
    ok("file_write")
else:
    fail("file_write", r.error)

r = ft.read_file({"path": str(tmpdir / "hello.txt")})
if r.ok and "Ola Nyx" in r.output:
    ok("file_read", r.output.strip())
else:
    fail("file_read", r.error or r.output)

r = ft.find_files({"root": str(tmpdir), "pattern": "*.txt"})
if r.ok and "hello.txt" in r.output:
    ok("file_find", r.output.strip())
else:
    fail("file_find", r.error or r.output)

try:
    r = ft.read_file({"path": "C:/Windows/System32/drivers/etc/hosts"})
    if not r.ok:
        ok("file_sandbox_escape_blocked")
    else:
        fail("file_sandbox_escape_blocked", "DEU ACESSO INDEVIDO!")
except Exception:
    ok("file_sandbox_escape_blocked")

# ──────────────────────────────────────────────
section("4. CLIPBOARD TOOL")
# ──────────────────────────────────────────────
from tools.clipboard_tool import ClipboardTool

clip = ClipboardTool()
r = clip.run({"action": "write", "text": "Nyx test clipboard 12345"})
if r.ok:
    ok("clipboard_write")
else:
    warn("clipboard_write", r.error)

r = clip.run({"action": "read"})
if r.ok and "Nyx" in r.output:
    ok("clipboard_read", r.output.strip()[:40])
else:
    warn("clipboard_read", r.error or r.output)

r = clip.run({"action": "clear"})
if r.ok:
    ok("clipboard_clear")
else:
    warn("clipboard_clear", r.error)

# ──────────────────────────────────────────────
section("5. PROJECT WATCH TOOL (hardware)")
# ──────────────────────────────────────────────
from tools.project_watch_tool import ProjectWatchTool

pw = ProjectWatchTool()
r = pw.run({})
if r.ok and "CPU" in r.output:
    for line in r.output.strip().splitlines()[:4]:
        print(f"    {line}")
    ok("project_watch_hw")
elif r.ok:
    warn("project_watch_hw", r.output[:80])
else:
    fail("project_watch_hw", r.error)

# ──────────────────────────────────────────────
section("6. UI TOOL (automacao desktop)")
# ──────────────────────────────────────────────
from tools.ui_tool import UITool

ui = UITool(screenshots_dir=tmpdir / "screenshots")

r = ui.list_windows({})
if r.ok:
    ok("ui_list_windows", f"{r.meta.get('count', 0)} janelas")
else:
    fail("ui_list_windows", r.error)

r = ui.take_screenshot({"filename": "nyx_test_shot"})
if r.ok:
    ok("ui_screenshot", r.output[:80])
else:
    warn("ui_screenshot", r.error)

if ui.is_destructive("close_window", {}):
    ok("ui_destructive_flag")
else:
    fail("ui_destructive_flag")

# ──────────────────────────────────────────────
section("7. SPRITE RENDERER (pixel art)")
# ──────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    from ui.sprite_renderer import SpriteRenderer

    sr = SpriteRenderer(scale=2)
    all_ok = True
    for emotion in ["idle", "talk", "think", "surprised", "listening", "error", "sleep"]:
        for mode in ["assistida", "autonoma"]:
            px = sr.render(emotion, mode)
            if px.isNull() or px.width() == 0:
                fail(f"sprite_{emotion}_{mode}")
                all_ok = False
    if all_ok:
        ok("sprite_renderer_14_sprites", "7 emocoes x 2 modos = 14 sprites")
except Exception as e:
    fail("sprite_renderer", str(e))

# ──────────────────────────────────────────────
section("8. AGENT LOOP (ciclo decisao completo)")
# ──────────────────────────────────────────────
from core.llm_client import OfflineLLM
from core.agent_loop import AgentLoop, SecurityError
from tools.registry import ToolRegistry, ToolSpec, ToolResult
from audit.logger import AuditLogger
from config import NyxConfig, PermissionMode

cfg = NyxConfig()
cfg.log_dir = tmpdir / "logs"
cfg.log_dir.mkdir(parents=True, exist_ok=True)

audit = AuditLogger(cfg.log_dir, session_id="full_test")
registry = ToolRegistry()
registry.register(
    ToolSpec(name="shell", description="shell", destructive=False, sensitive=True),
    lambda p: ToolResult(ok=True, output="shell-simulado"),
)
llm = OfflineLLM()
loop = AgentLoop(llm, registry, audit, mode=PermissionMode.ASSISTIDA)

# Chat basico (action=none)
r = loop.process("ola")
if not r.executed and r.response.parse_ok:
    ok("loop_chat_none", f"emotion={r.response.emotion}")
else:
    fail("loop_chat_none")

# Bloqueio de autonomo por texto
try:
    loop.activate_autonomous(source="texto_do_usuario")
    fail("loop_security_autonomous")
except SecurityError:
    ok("loop_security_autonomous", "SecurityError levantado")

# Autonomo legítimo via UI
loop.activate_autonomous(source="ui_toggle")
if loop.mode is PermissionMode.AUTONOMA:
    ok("loop_autonomous_ok")
else:
    fail("loop_autonomous_ok")

# Timeout forçado
from unittest.mock import MagicMock
fake_clock = MagicMock()
fake_clock.now.return_value = 9_999_999.0
loop.clock = fake_clock
loop._enforce_autonomy_timeout()
if loop.mode is PermissionMode.ASSISTIDA:
    ok("loop_timeout_revert")
else:
    fail("loop_timeout_revert")

# Confirmacao pendente em modo assistida
shell_json = json.dumps({
    "reasoning": "listar diretorio",
    "alternative_suggestion": None,
    "emotion": "talk",
    "action": {"type": "shell", "params": {"template": "LIST_DIR", "path": "."}},
    "requires_confirmation": False,
    "confirmation_prompt": None,
    "speech_output": "Listando...",
})
llm.queue(shell_json)
loop.mode = PermissionMode.ASSISTIDA
from core.agent_loop import MonotonicClock
loop.clock = MonotonicClock()
r = loop.process("lista o diretorio")
if r.needs_confirmation and not r.executed:
    ok("loop_confirmation_required")
else:
    fail("loop_confirmation_required", f"needs={r.needs_confirmation} exec={r.executed}")

# Confirmar -> executa
r2 = loop.confirm_pending({"type": "shell", "params": {"template": "LIST_DIR", "path": "."}}, approved=True)
if r2.executed:
    ok("loop_confirm_approved")
else:
    fail("loop_confirm_approved")

# Negar -> nao executa
r3 = loop.confirm_pending({"type": "shell", "params": {}}, approved=False)
if not r3.executed:
    ok("loop_confirm_denied")
else:
    fail("loop_confirm_denied")

# ──────────────────────────────────────────────
section("9. AUDIT LOGGER")
# ──────────────────────────────────────────────
audit_file = cfg.log_dir / "nyx_audit_full_test.jsonl"
if audit_file.exists():
    lines = [json.loads(l) for l in audit_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    events = [l["event"] for l in lines]
    ok("audit_log", f"{len(events)} eventos gravados: {events[:5]}")
else:
    fail("audit_log", "arquivo nao encontrado")

# ──────────────────────────────────────────────
section("10. MACRO TOOL")
# ──────────────────────────────────────────────
from tools.macro_tool import MacroStore, make_macro_tool_func

store = MacroStore(tmpdir / "macros")
macro_fn = make_macro_tool_func(store, registry)

r = macro_fn({"action": "save", "name": "macro_teste", "steps": [
    {"type": "shell", "params": {"template": "LIST_DIR", "path": "."}}
]})
if r.ok:
    ok("macro_save")
else:
    fail("macro_save", r.error)

r = macro_fn({"action": "list"})
if r.ok and "macro_teste" in r.output:
    ok("macro_list", r.output.strip())
else:
    fail("macro_list", r.error or r.output)

r = macro_fn({"action": "delete", "name": "macro_teste"})
if r.ok:
    ok("macro_delete")
else:
    fail("macro_delete", r.error)

# ──────────────────────────────────────────────
section("RESUMO FINAL")
# ──────────────────────────────────────────────
passed = sum(1 for v in results.values() if v == "PASS")
warned  = sum(1 for v in results.values() if v == "WARN")
failed  = sum(1 for v in results.values() if v == "FAIL")
total   = len(results)

print()
print(f"  Total : {total}")
print(f"  PASS  : {passed}")
print(f"  WARN  : {warned}  (funciona com ressalva)")
print(f"  FAIL  : {failed}")

if failed == 0:
    print("\n  [APROVADO] TODOS OS MODULOS FUNCIONAIS!")
else:
    fails = [k for k, v in results.items() if v == "FAIL"]
    print(f"\n  [REPROVADO] Falhas: {fails}")

shutil.rmtree(tmpdir, ignore_errors=True)
