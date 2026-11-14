# Programa Nyx Evolution — desenvolvimento modular verificável

**Estado:** programa técnico, não inventário de funcionalidades concluídas. O alvo
aspiracional é evoluir até 1.800 módulos de capacidade **úteis e testados**;
nenhum módulo conta apenas por ter nome, pasta ou classe vazia. O progresso real
deve ser registrado em commits e testes, nunca estimado pelo número de linhas.

## Definição mínima de um módulo concluído

Cada módulo precisa de:
1. Responsabilidade única e contrato de entradas/saídas validado.
2. Dependências explícitas e limites de CPU/RAM/VRAM/disco/conexão.
3. Permissões separadas entre leitura, escrita e ações externas.
4. Tratamento de timeout, falhas, cancelamento, efeitos desconhecidos e retorno.
5. Testes positivos, negativos, adversariais e de regressão reproduzíveis.
6. Evidência observável da pós-condição e rastreabilidade/auditoria.
7. Documentação, desativação e processo seguro de atualização/rollback.
8. Teste real do Windows quando depender de UI, GPU ou voz.

**Não iniciar 1.800 processos/modelos:** módulos devem ser preguiçosos
(on-demand), com inicialização controlada, e o modelo principal é único
por vez na máquina de 16 GiB RAM e RTX 3060 de 12 GiB VRAM.

## Áreas arquiteturais previstas (backlog, não módulos já criados)

- A. Inferência local: escolha de modelo, fila, cache KV, quantização, orçamento.
- B. Controle de recursos: admissão por RAM/VRAM, prioridades e preempção.
- C. Planejamento: decomposição, metas verificáveis e progresso.
- D. Execução: ferramentas, estado, confirmações, idempotência e rollback.
- E. Microagentes: delegação, dependências, consulta segura e comunicação.
- F. Recuperação: diagnóstico, replanejamento, retomada após interrupções.
- G. Memória episódica: fonte, relevância, atualização e esquecimento solicitado.
- H. Memória semântica: busca, compactação, verificação e origem.
- I. Sono/experimentos KRA: apenas em ociosidade e com evidência.
- J. Visão e automação: UIA, OCR quando necessário, DOM, tela, jogos.
- K. Voz e comunicação: STT, TTS, interrupções e notificações.
- L. Web e pesquisa: fontes, citações, dados mutáveis, confiabilidade.
- M. Programação: leitura, testes, diffs, aplicação revisável e isolamento.
- N. Arquivos e projetos: workspace, snapshots, versões e backups.
- O. Segurança: capacidade mínima, segredos, consentimento, auditoria.
- P. Atualizações: distribuição Windows, integridade e restauração.
- Q. Métricas: painéis, qualidade, estabilidade e consumo.
- R. Avaliação: benchmarks retidos, adversariais, regressões e testes de campo.

Um catálogo com 1.800 entradas não prova 1.800 funcionalidades. O roadmap
será granularizado progressivamente em módulos conforme problemas observados.
A arquitetura deve suportar essa escala sem pré-carregar tudo.

## Lote 01 — execução de tarefas (branch experimental)

- Microagente tem orçamento 2 por padrão e **2–6 se solicitado**;
  último turno sempre reservado à resposta, ações sempre somente leitura.
- Falhas fornecem diagnóstico breve ao planejador sem repetir automaticamente
  efeitos externos; três falhas sem verificação com a mesma ferramenta param.
- Conclusão sem evidência de execução recebe aviso. No modo GUI/autoextend,
  há no máximo **um** replanejamento sem ação externa silenciosa.
- Histórico com >12 ações é resumido em JSON: contagens antigas,
  falhas identificadas e oito observações recentes mais detalhadas.
- Avaliador \`tools/evaluate_agent_reliability.py\`: seis cenários com
  modelo roteirizado e ferramentas reais, em Linux/Windows.
- A integração com a memória e o sono permanece opt-in (lote anterior);
  proteção para 16 GiB RAM continua relevante.

## Portões de qualidade para cada lote

1. Ruff + testes focados verdes.
2. Testes de regressão gerais (Linux) e testes Windows separados.
3. Pelo menos um cenário fim a fim reprodutível do subsistema afetado.
4. Teste de pressão/falha e comportamento de cancelamento.
5. Revisão de logs (nenhum segredo/sucesso não verificado).
6. Comparativo de desempenho (baseline vs candidato) com métricas,
   hardware, semente e limitações declarados.
7. Só mesclar depois da aceitação no Windows alvo, para dependências
   de GPU, interface, automação ou áudio.

## Lacunas prioritárias (não concluídas)

- Testar dezenas de objetivos com Qwen **real** e comparar taxa de conclusão.
- Avaliar uma hora de uso interativo com interrupções e sem vazamento de RAM.
- Definir pós-condições específicas por objetivo; qualquer tool ok != meta concluída.
- Monitor de erros sem credenciais; sugestões de próximos passos verificáveis.
- Calibrar quantização/contexto/latência do modelo real na RTX 3060.
- Integrar treinamento neural KRA-13 original somente após recuperar fontes,
  checkpoints e validar generalização contra cache/dicionários.

O projeto não promete AGI, consciência, autossuficiência absoluta nem ausência
de bugs. Progresso válido = melhorias reproduzíveis sobre tarefas reais.
