# Nyx — experimento KRA-13 aplicado à memória (não neural)

## Escopo exato

Esta fase incorpora **um princípio de endereçamento compartilhado leitura/escrita**
da pesquisa KRA-13, não a implementação neural original de 42 parâmetros.
Não houve transplante de pesos, treinamento PyTorch, atenção diferenciável nem
prova de vantagem sobre um dicionário Python ou banco SQLite.

O sistema atual:
- `core.kra13_hot_memory.KRA13HotMemory`: 4 slots de chaves exatas, roteamento
  determinístico BLAKE2b e sondagem linear, LRU sob colisões/lotação.
- Em caso de cache miss, `CoreMemory.get` usa o dicionário de fatos já carregados,
  cuja origem é SQLite. Nenhum fato persistente é removido por cache eviction.
- `bounded_fact_prompt`: seleciona até 15 fatos, privilegia segurança/perfil
  e recência semântica aproximada por sobreposição lexical e limita o bloco
  a 1700 caracteres. Isso protege a janela do Qwen contra prompt gigantesco.
- `AgentLoop.process` passa o pedido atual à seleção contextual.
- `SleepCycle` em SQLite revisa notas explícitas quando autorizado; checkbox
  em Aprendizado / Memória e interesses, desativado por padrão, timer 3 min.
  Pula se ocupado, foco, RAM livre < 3 GiB, fila de inferência ou CPU alta.
- Nenhuma geração adicional, download de modelo, treino automático, instalação
  de extensão ou execução arbitrária é autorizada por esses módulos.

## Evidência de pesquisa original KRA-13

Com 4 chaves explícitas, 4 slots, 42 parâmetros: média MSE ~0,0030
em tarefa sintética de sobrescrita, mas o controle determinístico atingiu
MSE=0 e K=8 ficou instável. Portanto, tratar roteamento como hipótese,
não como superioridade geral.

## Benchmark local controlado (sandbox Linux, Python 3.13)

10.002 fatos **sintéticos**, não dados privados:
- Prompt ingênuo por enumeração: 949.002 caracteres.
- Prompt selecionado: 1.322 caracteres; **99,86% menor**.
- Mediana de 5 medições com tracemalloc: ~194 ms.
- Pico de alocação tracemalloc: ~1,46 MiB para a seleção.
- Cache: 4 slots, 996 evicções após 1000 chaves distintas; a taxa de hit
  foi medida apenas sobre acessos recentes e não é avaliação de workload real.

O ganho comprovado é de **limitação do contexto**, não redução de RAM do modelo,
maior inteligência, latência menor ou retenção neural superior.

## Regressão / próximos controles

Executar: `python -m pytest -q tests/test_kra13_hot_memory.py tests/test_sleep_cycle.py tests/test_memory.py`.
O CI Linux geral precisa das dependências gráficas Qt e seus runtimes.
Somente uma execução completa no Windows real comprovará o funcionamento da
UI, captura de áudio, automação e Qwen/RTX 3060. Não publicar um novo executável
nem mesclar em `main` enquanto essas verificações estiverem pendentes.

Requisitos futuros:
- Comparar cache versus `dict`, SQLite LRU e Qwen sem cache, com latência.
- Medir recall/precisão/omissão de memórias em 100+ perguntas retidas,
  com perguntas privadas excluídas dos logs.
- Incluir adaptação de recursos, indicadores do painel e rollback.
- Para integrar o **modelo neural** KRA-13 propriamente dito:
  localizar fonte e checkpoints originais, validar PyTorch, reproduzir
  seeds e aferir generalização, K>4 e memória entre sessões.
