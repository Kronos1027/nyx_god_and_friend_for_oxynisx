# Bateria M0 — diagnóstico parcial

Modelo: qwen3.5:4b · perfil: conservative · 3 execuções por caso.

Marcos M0–M8 não são concluídos por este relatório parcial. Apps ausentes são excluídos por inventário independente. Casos instalados bloqueados permanecem no denominador e não comprovam ausência de capacidade da Nyx. Abrir uma janela nova e obter foco são métricas distintas.

| Categoria | Casos | Tentativas executadas | Bloqueadas no harness/ambiente | Foco confirmado/medido | Mediana de sucesso | Gate da categoria |
|---|---:|---:|---:|---:|---:|---|
| browser | 10 | 0/30 | 30/0 | 0/0 | 0.0% | não passou |

## Falhas e bloqueios

Nenhuma falha nos casos executados. Isso não avalia os casos bloqueados.

## Método e limites

TaskRunner/modelo reais; verificadores independentes leem arquivos e texto entregue. A interface pessoal não é operada. Conferência de texto tem vocabulário limitado; não é verificador semântico universal. Traces brutos ficam somente em logs/traces/.

RAM mede working sets do harness e filhos, podendo repetir páginas compartilhadas. VRAM é uso total da GPU do sistema, não alocação exclusiva da Nyx. Amostras a cada 250 ms podem não capturar picos mais curtos.
