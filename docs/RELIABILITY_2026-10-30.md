# Correções guiadas pelos registros de uso — 30/10/2026

## Falhas observadas e mudanças

**Contexto esgotado.** Nos pedidos reais da Steam de 29/10, o Ollama registrou
`n_ctx_slot=2048`, entrada de 1979 tokens e término após 69 tokens gerados.
A recuperação acrescentava instruções, chegando a 2018 + 30. Aumentar somente
o teto de saída de 512 para 1024 não resolvia a falta de espaço.

`prompt_budget` agora recebe o contexto efetivamente admitido pelo runtime,
reserva a saída e uma margem e compacta o catálogo, a memória opcional e as
observações. Pedido atual, restrições anteriores do usuário e todos os estados
das etapas são preservados; JSON não é cortado no meio. Trechos de saída são
marcados como incompletos. Procedimentos consultados permanecem inteiros.
Se o conteúdo indispensável não cabe, a tarefa pausa por capacidade em vez de
mandar uma entrada sabidamente excessiva. O contador é uma estimativa por bytes,
não o tokenizer exato do modelo. A auditoria inclui estimativa, contexto real,
contagem de entrada observada, reserva de saída e nível de compactação.

Quando há evidência de contexto esgotado, a única regeneração permitida compacta
a entrada sem aumentar o teto de saída nem acrescentar mais instruções.
Reservas de memória, confirmações, prazo e cancelamento continuam ativos.
Referência de comportamento do servidor:
[montagem e truncamento do prompt no Ollama](https://github.com/ollama/ollama/blob/main/server/prompt.go).

**Aritmética incorreta mesmo com leituras corretas.** O primeiro ensaio com o
contexto corrigido leu oito arquivos e respondeu soma 398 em vez de 396.
A ferramenta `calculator` agora oferece operações decimais limitadas, sem
`eval`, scripts, rede ou acesso ao sistema. Informa arredondamento, recusa
valores não finitos, divisão por zero e entradas excessivas. O planejador recebe
instrução para calcular valores observados com essa ferramenta.

**Steam.** A descoberta considera também o registro da instalação por máquina.
A janela do renderer só é aceita quando o executável pertence à instalação
Steam e existe um ancestral `steam.exe` observado; títulos isolados não bastam.
`list_installed_apps` aceita os aliases usados pelo modelo e devolve resumo
compacto. `list_steam_games` lê manifests locais, com limites, filtros e
paginação; não instala, compra, inicia jogos ou faz login. Manifests podem
incluir utilitários e não provam licença nem capacidade de executar um jogo.

**Aprendizado e delegação.** O planejador recebe o contrato de `evolution`;
`{query: ...}` consulta notas em vez de cair silenciosamente em status.
Simulação considera permissões dinâmicas e ferramentas desativadas.
Microagentes recebem somente seu catálogo autorizado e reservam o último turno
ao relatório. Promessas explícitas sem entrega, repetição e fim sem conclusão
retornam trabalho incompleto; não liberam dependências como sucesso.
Análises sem consulta são identificadas como `analysis_only`. Isso não prova
a verdade semântica de todo relatório nem amplia permissões dos microagentes.

**Retomada no chat correto.** Novos checkpoints guardam a conversa de origem.
A interface volta a ela antes de retomar, e o executor rejeita contexto de outra
conversa. Registros antigos sem vínculo ou de conversa excluída exigem revisão
e novo pedido; não são associados silenciosamente ao chat aberto.

## Evidência e limites

- Regressão: **807 aprovados, 50 pulados, 1 aviso, 36,01 s, saída 0**.
  `build/sandbox-probes/planner-reliability-regression.log/.xml`. Ruff aprovado.
  Testes opt-in de navegador, desktop físico e LPAC ficaram desativados nesta
  rodada. Ensaios Qt usam dados temporários e janelas de fixture.
- Ensaio real Qwen3.5:4b: **9 ações, 8 leituras verificadas, soma 396, 32,61 s**.
  Dez gerações, todas com JSON válido na primeira tentativa, contexto 2048.
  Ampliação após a sexta ação registrada. `tools/verify_context_workflow.py`
  usa componentes de produção e bloqueia efeitos fora de leituras preparadas
  e cálculo. **Não é operação da interface nem validação irrestrita do agente.**
  Relatório: `build/sandbox-probes/context-workflow-real.json`; tentativa que
  errou a soma preservada em `context-workflow-before-calculator.json`.
- Leitura real de bibliotecas Steam encontrou 19 itens instalados em quatro
  bibliotecas. `build/sandbox-probes/steam-catalog-readonly.json`.
  O ensaio de escolha pelo modelo foi **bloqueado por RAM livre abaixo de 1 GiB**,
  registrado em `steam-planning-real.json`. Não foi reduzida a reserva de memória.
- O usuário passou a conduzir os testes na interface. Não houve controle da
  Nyx nem reinício de sua interface nesta etapa. As alterações carregam na
  próxima abertura a partir do código deste projeto.
- Pet preservado: AST de `CompanionStage` idêntica ao commit anterior; nenhum
  diff em overlay, renderer ou sprites.

Permanecem pendentes: validação da escolha real de jogo na interface, recursos
MCP/CodeAct ainda descritos em `LIMITACOES.md`, e avaliação de competência em
tarefas variadas. Estes resultados não significam AGI, conhecimento completo,
observação contínua do computador ou autoaperfeiçoamento irrestrito.
