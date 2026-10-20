"""Testes da Fase 0.6: ContextManager e ModelBroker de VRAM (core/context.py e core/broker.py)"""


from core.context import ContextManager
from core.broker import ModelBroker, ModelRole


def test_context_manager_observation_masking():
    ctx = ContextManager(max_context_tokens=8192, mask_threshold_chars=200)

    # 1. Observação curta (não é mascarada)
    short_obs = "Resultado: 42"
    res1 = ctx.store_observation("calc", short_obs)
    assert res1 == short_obs

    # 2. Observação longa (deve ser mascarada)
    long_obs = "A" * 1500
    res2 = ctx.store_observation("web_search", long_obs)
    assert "[obs #2 — web_search" in res2
    assert "recuperável via ctx.get(2)" in res2
    assert len(res2) < 200

    # 3. Recuperação sob demanda
    recovered = ctx.get_raw_observation(2)
    assert recovered == long_obs


def test_context_manager_todo_recitation():
    ctx = ContextManager()
    ctx.update_todo([
        {"id": "step_1", "desc": "Abrir aplicativo", "status": "done"},
        {"id": "step_2", "desc": "Processar dados", "status": "running"},
        {"id": "step_3", "desc": "Salvar arquivo", "status": "pending"},
    ])

    recitation = ctx.format_todo_recitation()
    assert "[x] step_1: Abrir aplicativo" in recitation
    assert "[~] step_2: Processar dados" in recitation
    assert "[ ] step_3: Salvar arquivo" in recitation

    msgs = ctx.assemble_prompt("Você é a Nyx.", [], "Próximo passo?")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "[PLANO ATIVO — RECITADO]" in msgs[1]["content"]


def test_model_broker_lifecycle():
    broker = ModelBroker(budget_mb=11000)

    # 1. Aloca planner
    h1 = broker.acquire(ModelRole.PLANNER, "qwen2.5:3b-instruct", estimated_mb=3500)
    assert h1.role == ModelRole.PLANNER
    assert ModelRole.PLANNER in broker.active_models

    # 2. Telemetria
    tele = broker.get_telemetry()
    assert "vram_budget_mb" in tele
    assert tele["vram_budget_mb"] == 11000
    assert "planner" in tele["active_roles"]

    # 3. Libera modelo
    broker.release(ModelRole.PLANNER)
    assert ModelRole.PLANNER not in broker.active_models
    assert broker.swap_count >= 1
