"""Testes para o subsistema de Text-To-Speech (TTS) da Nyx"""

from audio.tts import TextToSpeech, _clean_text_for_speech


def test_tts_clean_text():
    """A função de limpeza de texto é agora uma função de módulo (não método da classe)."""
    raw = "Olá! [Ação realizada com sucesso](file:///test.txt) **Importante:** teste `código` aqui. 🚀👍"
    cleaned = _clean_text_for_speech(raw)
    assert "file:///" not in cleaned
    assert "código" not in cleaned
    assert "Importante:" in cleaned
    assert "teste aqui." in cleaned


def test_tts_speak_disabled():
    tts = TextToSpeech(enabled=False)
    # Não deve gerar exceção mesmo quando desabilitado
    tts.speak("Teste de fala desabilitada.")
    assert tts.enabled is False


def test_tts_init():
    tts = TextToSpeech()
    # Nova API: sem atributo 'rate' — Kokoro controla velocidade internamente (speed=1.1)
    assert tts.enabled is True
    # Worker thread deve estar ativo
    assert tts._worker_thread.is_alive()


def test_tts_stop_current():
    """stop_current() não deve lançar exceção mesmo sem fala em andamento."""
    tts = TextToSpeech(enabled=False)
    tts.stop_current()  # não deve explodir


def test_tts_shutdown():
    """shutdown() deve encerrar o worker de forma limpa."""
    tts = TextToSpeech(enabled=True)
    tts.shutdown()
    # Após shutdown, o worker deve ter encerrado
    tts._worker_thread.join(timeout=2.0)
    assert not tts._worker_thread.is_alive()
