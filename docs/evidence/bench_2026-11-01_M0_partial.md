# Bateria M0 — diagnóstico parcial

**Revisão posterior:** o primeiro caso de arquivos teve números corretos, mas
omitiu calculator explicitamente pedido. O PASS antigo não comprova o método.
Consulte bench_2026-11-01_M0_partial_assessment.json e bench_method_2026-11-01.md.

Modelo: qwen3.5:4b · perfil: normal · 3 execuções por caso.

Marcos M0–M8 não são concluídos por este relatório parcial. Cobertura bloqueada fica no denominador e não comprova ausência de capacidade da Nyx.

| Categoria | Casos | Tentativas executadas | Bloqueadas no harness | Mediana de sucesso | Gate da categoria |
|---|---:|---:|---:|---:|---|
| apps | 15 | 0/45 | 45 | 0.0% | não passou |
| browser | 10 | 0/30 | 30 | 0.0% | não passou |
| conversation | 2 | 6/6 | 0 | 100.0% | passou nos casos selecionados |
| desktop | 8 | 0/24 | 24 | 0.0% | não passou |
| multi_step | 5 | 3/15 | 12 | 20.0% | não passou |
| presence_memory | 6 | 0/18 | 18 | 0.0% | não passou |
| research | 4 | 0/12 | 12 | 0.0% | não passou |

## Falhas executadas

Nenhuma falha nos casos executados. Isso não avalia os casos bloqueados.

## Método e limites

TaskRunner/modelo reais; verificadores independentes leem arquivos e texto entregue. A interface pessoal não é operada. Conferência de texto tem vocabulário limitado; não é verificador semântico universal. Traces brutos ficam somente em logs/traces/.

RAM mede working sets do harness e filhos, podendo repetir páginas compartilhadas. VRAM é uso total da GPU do sistema, não alocação exclusiva da Nyx. Amostras a cada 250 ms podem não capturar picos mais curtos.

Houve retomada explícita: linhas concluídas foram preservadas; somente casos de leitura/conversa podem ser retomados automaticamente. Uma execução foi interrompida durante leitura e uma gravação encontrou WinError5 transitório; o salvamento agora é atômico, com tentativa limitada.
