# Bateria M0 — diagnóstico parcial

Modelo: qwen3.5:4b · perfil: normal · 3 execuções por caso.

Marcos M0–M8 não são concluídos por este relatório parcial. Apps ausentes são excluídos por inventário independente. Casos instalados bloqueados permanecem no denominador e não comprovam ausência de capacidade da Nyx. Abrir uma janela nova e obter foco são métricas distintas.

| Categoria | Casos | Tentativas executadas | Bloqueadas no harness/ambiente | Foco confirmado/medido | Mediana de sucesso | Gate da categoria |
|---|---:|---:|---:|---:|---:|---|
| browser | 10 | 30/30 | 0/0 | 0/0 | 20.0% | não passou |

## Falhas e bloqueios

- browser-02, rodada 1: UNVERIFIED; 
- browser-02, rodada 2: UNVERIFIED; 
- browser-02, rodada 3: UNVERIFIED; 
- browser-03, rodada 1: UNVERIFIED; 
- browser-03, rodada 2: UNVERIFIED; 
- browser-03, rodada 3: UNVERIFIED; 
- browser-04, rodada 1: UNVERIFIED; 
- browser-04, rodada 2: UNVERIFIED; 
- browser-04, rodada 3: UNVERIFIED; 
- browser-05, rodada 1: UNVERIFIED; 
- browser-05, rodada 2: UNVERIFIED; 
- browser-05, rodada 3: RESOURCE_PRESSURE; 
- browser-06, rodada 1: UNVERIFIED; 
- browser-06, rodada 2: UNVERIFIED; 
- browser-06, rodada 3: RESOURCE_PRESSURE; 
- browser-07, rodada 1: UNVERIFIED; 
- browser-07, rodada 2: UNVERIFIED; 
- browser-07, rodada 3: RESOURCE_PRESSURE; 
- browser-08, rodada 1: UNVERIFIED; 
- browser-08, rodada 2: UNVERIFIED; 
- browser-08, rodada 3: RESOURCE_PRESSURE; 
- browser-09, rodada 1: UNVERIFIED; 
- browser-09, rodada 2: UNVERIFIED; 
- browser-09, rodada 3: RESOURCE_PRESSURE; 
- browser-10, rodada 3: RESOURCE_PRESSURE; 

## Método e limites

TaskRunner/modelo reais; verificadores independentes leem arquivos e texto entregue. A interface pessoal não é operada. Conferência de texto tem vocabulário limitado; não é verificador semântico universal. Traces brutos ficam somente em logs/traces/.

RAM mede working sets do harness e filhos, podendo repetir páginas compartilhadas. VRAM é uso total da GPU do sistema, não alocação exclusiva da Nyx. Amostras a cada 250 ms podem não capturar picos mais curtos.
