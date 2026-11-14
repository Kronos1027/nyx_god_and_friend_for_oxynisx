# Nyx — arquitetura de autonomia local com 16 GB RAM / 12 GB VRAM

Proposta incremental, não promessa de AGI. Prioridades: responder ao usuário,
manter tarefas recuperáveis, validar resultados, preservar dados, não monopolizar o PC.

## 1. Componentes existentes reutilizáveis

- core.runtime_budget: leitura RAM/VRAM, admissão de modelo e fila limitada.
- core.resource_governor: prioridades e bloqueio de operações de fundo.
- core.memory: notas/episódios SQLite. Não misturar fatos verificados com hipóteses.
- core.task_runner / core.task_journal: retomada e execução verificável.
- core.evolution, core.research, core.initiative: pesquisa e iniciativa limitadas.
- tools.registry e política de confirmação: única entrada para ações reais.

## 2. Contrato de recursos

- Manter **um único modelo de linguagem residente por vez**.
- Carregar STT/TTS e visão sob demanda; descarregar componentes opcionais sob pressão.
- Contexto máximo variável pela telemetria já existente: 1024–4096 tokens.
- Trabalho de fundo sempre preemptível. Não iniciar se há interação, voz ativa,
  jogo, baixa RAM, pressão de VRAM ou telemetria desconhecida.
- Consolidação SQLite sem modelo: <=24 notas por ciclo, <=256 cartões,
  sem vetor denso nem cache em RAM permanente, mínimo de 3 GiB livres.
- Nunca executar treino LoRA junto a jogos/automação em tempo real. Avaliar
  separadamente orçamento de VRAM, conjunto de treino, validação e rollback.

## 3. Estados do agente

Conversando > executando tarefa autorizada > ocioso > revisando memoria.
Interação do usuário interrompe trabalhos opcionais; ações externas pendentes
não são repetidas cegamente após timeout. Um agente autônomo não pode conceder
suas próprias permissões, alterar política de segurança nem remover o kill-switch.

## 4. Aprendizado mensurável

1. **Fase 1 concluída em protótipo:** revisão local de notas explícitas (SleepCycle).
   Não produz novas crenças nem novos pesos.
2. **Fase 2:** medição de recuperação sobre 100+ fatos com fonte, comparação antes/
   depois, métricas por origem e testes de esquecimento; painel para revisar/apagar.
3. **Fase 3:** gerar desafios *sintéticos* usando modelo já residente somente
   quando ocioso, marcando cada hipótese como **não verificada**. Não confundir
   resposta gerada com verdade; somente promover mediante testes independentes.
4. **Fase 4:** habilidades declarativas versionadas, simulação e testes em ambiente
   isolado; ativação com confirmação humana e rollback verificável.
5. **Fase 5:** avaliar LoRA em modelo pequeno contra benchmark fixo e retido.
   Só adotar quando melhorar resultados e não regredir tarefas antigas.

## 5. Capacidade funcional sem autonomia irrestrita

- Comunicação: GUI, voz e notificações já existentes; sugestões pertinentes
  com limites de frequência e respeito ao modo foco.
- Planejamento: tarefas persistentes com condições de conclusão observáveis.
- Execução: arquivos, navegador, automação do Windows sob política única.
- Segurança: aprovar pagamentos, exclusões, publicação, envio externo e acesso
  sensível; credenciais nunca entram em sonhos, prompts ou backups públicos.
- Evolução: criar propostas de skills, testar de forma isolada e apresentar
  relatório reproduzível. Nunca promover código gerado só porque compilou.

## 6. Critérios para considerar a versão estável

- Suíte completa em Windows e Linux com ambientes reproduzíveis, sem dependências
  ausentes; teste de 6h de estabilidade sem crescimento contínuo de RAM.
- Cancelamento de tarefas/sonos durante inferência, rollback e retomada após queda.
- Medição real de pico de RAM/VRAM, latência, taxa de sucesso e regressões.
- Auditoria e consentimento para cada classe de ação externa.
- Evidência de que alterar, esquecer ou negar uma memória não a reinsere depois.

SleepCycle v1 é um módulo em branch experimental, não integrado à UI nem à
instalação Windows. A pesquisa do Google sobre sono artificial **não** demonstra
por si só autoconsciência, autoaperfeiçoamento irrestrito ou aprendizado sem falhas.
