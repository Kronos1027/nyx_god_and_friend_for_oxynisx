import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from bench.native_windows import APPS, matches  # noqa: E402


def test_uia_or_title_success_does_not_replace_independent_process_identity():
    assert matches({'process':'CalculatorApp.exe','title':'test'},APPS['calculator'])
    assert matches({'process':'ApplicationFrameHost.exe','title':'Calculadora'},APPS['calculator'])
    assert not matches({'process':'ApplicationFrameHost.exe','title':'Outro aplicativo'},APPS['calculator'])
    assert not matches({'process':'Editor.exe','title':'Calculadora'},APPS['calculator'])
    assert not matches({'process':'ApplicationFrameHost.exe','title':'Calculadora.png - Fotos'},APPS['calculator'])
