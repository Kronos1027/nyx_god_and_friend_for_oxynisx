import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("voice_diagnostic", Path(__file__).resolve().parents[1] / "tools/verify_voice.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("text", [
    "Olá, minha amiga. Quanto é vinte mais trinta?",
    "Olá minha amiga, quanto é 20 mais 30?",
])
def test_fixture_accepts_spoken_and_numeric_numbers(text):
    assert module.matches_fixture(text)


@pytest.mark.parametrize("text", ["", "Olá, minha amiga. Quanto é 120 mais 300?", "vinte trinta", "Olá, minha amiga. Quanto é vinte mais quarenta?"])
def test_fixture_rejects_missing_words_and_partial_numbers(text):
    assert not module.matches_fixture(text)
