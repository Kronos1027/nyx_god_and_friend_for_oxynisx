---
name: nyx-windows-live-verify
description: Rodar o gate de verificação real da Nyx no Windows (bateria de aceitação, testes windows_live, evidência antes/depois) ao fechar qualquer marco ou corrigir uma capacidade.
---

# Gate de verificação real

Use ao **fechar um marco**, ao corrigir qualquer capacidade (abrir app, navegador, desktop, presença) e antes de afirmar que algo funciona.

1. Confirme que há desktop interativo (janela em primeiro plano e clipboard acessíveis). Se não houver, **não simule**: atualize `tools/run_live.ps1` e peça ao usuário para executá-lo; leia o resultado em `docs/evidence/`.
2. Rode `python -m ruff check src tests tools` e `python -m pytest -q`.
3. Rode `python tools/run_bench.py --runs 3 --categories <as que o marco toca>`. Regras da bateria e formato: `references/bench-spec.md`.
4. Grave `docs/evidence/bench_<data>_<marco>.md/json` com taxa de sucesso por categoria, tempo mediano, VRAM/RAM pico e **traces das falhas** (`logs/traces/` fica fora do git; copie só o trecho sanitizado).
5. Compare com o baseline do M0. Se qualquer categoria tocada ficou abaixo do limiar, **o marco não fecha**: diagnostique pelo trace, corrija, rode de novo.
6. Falso sucesso (a Nyx afirma feito, o verificador independente nega) = bloqueio imediato.

Nunca: afrouxar verificador, reduzir número de execuções, marcar `verified=True` sem observar a pós-condição, ou usar mock em teste de aceitação.
