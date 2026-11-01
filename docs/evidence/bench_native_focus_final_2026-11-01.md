# Bateria M0 — diagnóstico parcial

Modelo: qwen3.5:4b · perfil: conservative · 3 execuções por caso.

Marcos M0–M8 não são concluídos por este relatório parcial. Cobertura bloqueada fica no denominador e não comprova ausência de capacidade da Nyx.

| Categoria | Casos | Tentativas executadas | Bloqueadas no harness | Mediana de sucesso | Gate da categoria |
|---|---:|---:|---:|---:|---|
| apps | 15 | 0/45 | 36 | 0.0% | não passou |

## Falhas executadas

- apps-01, rodada 1: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-01, rodada 2: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-01, rodada 3: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-02, rodada 1: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-02, rodada 2: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-02, rodada 3: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-12, rodada 1: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-12, rodada 2: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.
- apps-12, rodada 3: NATIVE_UI_HARNESS_1; Execução Qt incompleta; diagnóstico local preservado.

## Método e limites

TaskRunner/modelo reais; verificadores independentes leem arquivos e texto entregue. A interface pessoal não é operada. Conferência de texto tem vocabulário limitado; não é verificador semântico universal. Traces brutos ficam somente em logs/traces/.

RAM mede working sets do harness e filhos, podendo repetir páginas compartilhadas. VRAM é uso total da GPU do sistema, não alocação exclusiva da Nyx. Amostras a cada 250 ms podem não capturar picos mais curtos.
