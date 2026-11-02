# Bateria M0 — diagnóstico parcial

Modelo: qwen3.5:4b · perfil: normal · 3 execuções por caso.

Marcos M0–M8 não são concluídos por este relatório parcial. Cobertura bloqueada fica no denominador e não comprova ausência de capacidade da Nyx.

| Categoria | Casos | Tentativas executadas | Bloqueadas no harness | Mediana de sucesso | Gate da categoria |
|---|---:|---:|---:|---:|---|
| apps | 15 | 7/45 | 9 | 0.0% | não passou |

## Falhas executadas

- apps-01, rodada 1: UNVERIFIED; Verificação independente ou fluxo da UI não concluiu; confira o trace local.
- apps-01, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-01, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-02, rodada 1: UNVERIFIED; Verificação independente ou fluxo da UI não concluiu; confira o trace local.
- apps-02, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-02, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-04, rodada 1: UNVERIFIED; Verificação independente ou fluxo da UI não concluiu; confira o trace local.
- apps-04, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-04, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-05, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-05, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-06, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-06, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-07, rodada 1: UNVERIFIED; Verificação independente ou fluxo da UI não concluiu; confira o trace local.
- apps-07, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-07, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-09, rodada 1: RESOURCE_PRESSURE; Verificação independente ou fluxo da UI não concluiu; confira o trace local.
- apps-09, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-09, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-10, rodada 1: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-10, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-10, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-11, rodada 1: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-11, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-11, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-12, rodada 1: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-12, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-12, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-13, rodada 1: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-13, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-13, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-14, rodada 1: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-14, rodada 2: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.
- apps-14, rodada 3: RESOURCE_PRESSURE; A tarefa foi suspensa por pressão de memória; nenhuma nova inferência será tentada.

## Método e limites

TaskRunner/modelo reais; verificadores independentes leem arquivos e texto entregue. A interface pessoal não é operada. Conferência de texto tem vocabulário limitado; não é verificador semântico universal. Traces brutos ficam somente em logs/traces/.

RAM mede working sets do harness e filhos, podendo repetir páginas compartilhadas. VRAM é uso total da GPU do sistema, não alocação exclusiva da Nyx. Amostras a cada 250 ms podem não capturar picos mais curtos.
