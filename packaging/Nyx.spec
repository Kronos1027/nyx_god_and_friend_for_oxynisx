# PyInstaller spec for the Windows desktop application.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from pathlib import Path

repo = Path(SPECPATH).resolve().parent
datas = [(str(repo / "src/core/schema.gbnf"), "src/core")]
datas += [(str(repo / "assets/oxynisx/spritesheet.png"), "assets/oxynisx")]
binaries = []
hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtMultimedia",
    "PyQt6.QtNetwork",
    "PyQt6.QtSvg",
    "llama_cpp",
    "faster_whisper",
    "ctranslate2",
    "kokoro_onnx",
    "onnxruntime",
    "sounddevice",
    "soundfile",
    "pywinauto",
    "pyautogui",
    "mss",
    "PIL",
]

for package in ("llama_cpp", "faster_whisper", "ctranslate2", "kokoro_onnx", "onnxruntime"):
    binaries += collect_dynamic_libs(package)
datas += collect_data_files("faster_whisper")
datas += collect_data_files("kokoro_onnx")

a = Analysis(
    [str(repo / "src/main.py")],
    pathex=[str(repo / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff", "IPython", "jupyter", "notebook", "tkinter"],
    noarchive=False,
    optimize=1,
)
# PyInstaller may resolve Qt's ICU/system dependencies from unrelated DLL
# search paths on the build machine. Never ship the host's libheif bundle; it
# contains an incompatible ICU and Windows API shim DLLs that break Qt startup.
host_libheif = "\\libheif\\libheif\\bin\\"
host_poppler = "\\poppler\\library\\bin\\"
a.binaries = [
    entry for entry in a.binaries
    if (
        host_libheif not in Path(entry[1]).as_posix().casefold().replace("/", "\\")
        and host_poppler not in Path(entry[1]).as_posix().casefold().replace("/", "\\")
    )
]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nyx",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Nyx",
)
