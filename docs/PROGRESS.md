# PROGRESS — memória externa do trabalho (atualize ao fim de cada passo relevante)

**Marco atual:** M7 HUD + M3 navegador em paralelo, por prioridade do usuário · **Branch de integração:** nyx-2
**Próximo passo exato:** integrar entregas das worktrees codex/nyx-m7-hud e codex/nyx-m3-browser. Root separa abertura/foco e inventário/reset do bench; depois Normal condicional/carga fria e classificador semântico. CI/higiene só quando necessário. Push a cada marco/~4h.
**Como retomar:** `git switch nyx-2` · ler AGENTS.md, este arquivo e docs/DECISOES.md · rodar `python -m pytest -q`
**Bloqueios:**35cenários do harness sem setup/verificador seguro, sem inferir incapacidade da Nyx. Apps não são fechados/resetados e há falhas medidas de foco/RAM. Login Spotify adiado pelo usuário. Migração privada/remoção remota fora do escopo aprovado. Requalificação de arquivos passou3/3; recusas anteriores permanecem como histórico.

## Marcos
| Marco | Status | Evidência | Gate (limiares) | Notas |
|---|---|---|---|---|
| M0 Fundação e baseline | parcial: bloqueado por ambiente | evidence/apps_expansion_2026-11-01.md | baseline ampliado/reset pendentes | Avançar por instrução do usuário |
| M1 Destravar | parcial: bloqueado por ambiente | evidence/apps_expansion_2026-11-01.md | Apps instalados ≥ 95% · foco separado | RAM/foco/reset medidos; retornar depois |
| M2 Cérebro e recursos | parcial herdado | evidence/resource_profiles_2026-10-31.md; evidence/conversation_stream_2026-10-31.md | 1º token < 1,5 s · multi-etapa ≥ 80% · VRAM ≤ 9,5 GiB | Perfis/saudações medidos; não conclui o gate |
| M3 Navegador e pesquisa | em implementação paralela | | Navegador ≥ 85% · Pesquisa ≥ 85% | codex/nyx-m3-browser |
| M4 Desktop robusto e habilidades | pendente | | Desktop ≥ 90% · 10 apps com habilidade validada | |
| M5 Confiança graduada | pendente | | tarefa de 6 passos com ≤ 1 confirmação; R3 sempre confirma | |
| M6 Presença, memória e voz | pendente | | Presença/memória ≥ 90% · voz < 2,5 s | |
| M7 Interface Nyx HUD | em implementação paralela | | QA visual + check_ui + perf | codex/nyx-m7-hud; pet congelado |
| M8 Aceitação final | pendente | | bench 3× completo · soak 2 h · falso sucesso = 0 | |

## Log (mais recente primeiro)
- 02/11/2026 — Abertura e foco separados na ferramenta/guarda final; bench
  instalado 12/15, quatro pré-existentes bloqueados por reset manual seguro.
  Ruff limpo; regressão padrão 960/61pulados/0falhas,50,083s. Nova bateria fria
  não validada. evidence/apps_policy_2026-11-02.md; M0/M1 parciais por ambiente.
  Integrados pausa de contexto sem apagar consentimento/histórico e M3 Shadow/AX
  inicial (36f1678). HUD/segundo M3 retomados nas worktrees preservadas.
- 02/11/2026 — Direção revisada pelo usuário, registrada em AGENTS/D-009.
  Dois agentes autorizados iniciaram M7/M3 em worktrees próprias, deps compartilhadas
  por junctions no volume do projeto. Sem nova cópia de venv/modelos no C.
  M0/M1 parciais por ambiente; abertura/foco passam a métricas independentes.
  Root coordena integração/docs/push e ajustes de bench/perfil/conversa.
- 01/11/2026 — Push confirmado por Git/API:35commits na branch nyx-2,58693f6,
  main/backups intactos, sem force.21blobs documentais históricos sanitizados;
  árvore final idêntica e referência original local preservada. Scanner passou.
  CI Linux real falhou em três fixtures; corrigidas sem remover asserts e com
  parser Windows separado.67testes focados verdes; próximo push/verificação CI.
- 01/11/2026 — Usuário reiterou envio ao GitHub. Gate final970passes/27skips/
  0falhas/49,845s,997casos. Rotas nativas12; roteamento12/12para quatro apps,
  mas runner final interrompido por RAM na sétima tarefa (2passes/7execuções;
  29runtime/9harness bloqueados). Sem falso sucesso no último runner.
  Auxiliar PID real validado por parentesco/criação, árvore própria encerrada3/3;
  foco sincronizado passou12/12em fixtures, apps instalados ainda bloqueiam.
  Evidência: evidence/apps_expansion_2026-11-01.md. Não promover M0/M1.
- 01/11/2026 — Revisão de publicação:319blobs novos origin/main..HEAD analisados;
  39candidatos do scanner conferidos como fingerprints/digests/metadados do
  próprio baseline. Caminhos locais encontrados em19versões de três documentos.
  Sanitizar só esses documentos na cadeia ainda não enviada, preservar referência
  local original, manter código/árvore final idênticos, sem mudar main/backups.
- 01/11/2026 — Expansão Apps em andamento: baseline15tarefas/5apps revelou
  falso sucesso Explorer (área de trabalho), forwarder wt não reconhecido e
  escolhas browser/Bing e shell/GET_PROCESS em pedidos de abrir Edge/Terminal.
  Filtro de classe Explorer, AUMID Terminal e guarda de planejamento adicionados.
  Nova UI real Edge/Explorer/Settings/Terminal12/12, foco final confirmado.
  Gerenciador: UIA falhou; alternativa Win32 sem COM/mover mouse preserva erro
  real `(5, BringWindowToTop, Acesso negado.)`,0/3. Duas estratégias realizadas;
  não elevar ou reduzir proteção. Seguir Discord/Steam/OBS/Antigravity e gate.
  Ainda sem commit desta expansão; últimos sources commitados08f21dc.
- 01/11/2026 — Gate de regressão do incremento:949passes/27skips/0falhas,
  976casos,48,178s; Ruff limpo. Runner integrado Normal9/9executados,36bloqueados,
  saída1 correta por cobertura/sem reset. Duas novas fingerprints auditadas
  pontualmente no baseline de segredos. Próximo: ampliar apps, sem promover marco.
- 01/11/2026 — Foco nativo: superfície cloaked excluída e conferência final após
  resposta do modelo. Ensaio final9/9, integrado Normal9/9sem divergências;
  Conservador bloqueou por RAM, preservado. Janela já aberta recebe foco; fallback
  web só NOT_FOUND, informado. nativos Spotify/WhatsApp ausentes, sem login.
  Regressão975casos:948passes/27skips/0falhas,47,078s. Gate Apps20%/sem reset,
  marco não concluído. Evidência: evidence/native_focus_2026-11-01.md.
- 01/11/2026 — Defeito crítico em investigação: verificador Apps agora exige
  foreground. Baseline anterior só3/9com foco. Primeira correção6/9; superfície
  UWP da Calculadora tinha DWMWA_CLOAKED=2 embora WS_VISIBLE. Filtro DWM elevou
  para8/9, mas uma rodada confirmou foco e o perdeu antes da conclusão, um falso
  sucesso no checker final. Artefatos native_focus_ui/native_focus_dwm_ui
  preservados. Próximo: revalidar pós-condição no encerramento; gate bloqueado.
- 01/11/2026 — Higiene M0:820passes/13skips no núcleo mínimo sem Qt;
  scanner offline/hook serial/CI configurados, nove falsos positivos auditados,
  sintético bloqueado3/3. Ambiente/cache no E. Regressão completa923passes,
  27skips,6falhas de foco/70,008s; isolado12/12 posterior. Não declarar gate
  verde. Evidência: evidence/ci_hygiene_2026-11-01.md. Linux/histórico pendentes.
- 01/11/2026 15:26 — Higiene M0 em andamento: ambiente mínimo separado no E
  reproduziu11erros de coleção por Qt/NumPy. Imports GUI passaram a ser opcionais
  somente nos testes, com mocks unitários de APIs Windows independentes de libs
  reais. psutil7.2.2 declarado no núcleo; requisitos de teste CPU separados.
  Ambiente mínimo Windows sem Qt terminou verde; Linux/WSL não disponível, não
  declarar CI Linux executado. Logs/XML em build/diagnostic/ci-core-final.*.
- 01/11/2026 15:26 — detect-secrets1.5.0 instalado só em .local-deps/security-env,
  wheel120341bytes, ambiente4,85MB, startup0,610–0,644s, RSS~50MiB incluindo
  launcher/filhos, nenhum PID GPU observado. Scan --no-verify local encontrou9
  candidatos:4fingerprints de código,3digests Ollama confirmados,1literal de
  teste de redação e1nome de variável apiKeyEnv. Nenhuma verificação de chave
  na rede executada; baseline auditado/hook/CI e histórico ainda pendentes.
  Arquivo privado build/diagnostic/secrets-working-tree.json contém só hashes.
- 01/11/2026 14:56 — UI de produção temporária→QTest no PermissionDialog real→
  ferramenta real→Win32 independente: Calculadora/Bloco de notas/Paint3× cada,
  9/9 no ensaio integrado, uma confirmação/uma ação por tarefa, sem divergências.
  Runner Apps agora executa9/45tentativas;36bloqueadas. Gate continua falso por
  cobertura e ausência de reset. Sem fechar apps pessoais ou operar a Nyx pessoal.
  929aprovados,27pulados,0falhas,50,637s,saída0; Ruff incl.bench limpo. Evidência:
  evidence/native_app_ui_2026-11-01.md. Próximo: higiene M0 CI/segredos.
- 01/11/2026 14:27 — Runner50casos, script run_live, marcadores Windows e
  verificadores independentes iniciais implementados.150linhas finalizadas;
  141BLOCKED_HARNESS. Retomada R0 explícita e gravação atômica sobreviveram a
  interrupção/WinError5, sem repetir linhas prontas. Gate M0 continua parcial.
- 01/11/2026 14:27 — Checker inicial perdeu omissão de calculator em uma rodada:
  método2/3, embora números3/3corretos. Artifact original preservado com avaliação
  posterior. Guarda do planejador exige cálculo quando explicitamente pedido;
  nova rodada3/3, oito leituras+calculator,396,26,468/28,640/26,375s.
  Regressão final927aprovados,27pulados,0falhas,48,889s; Ruff limpo incl.bench.
  Próximo: ampliar Apps/Desktop e higiene CI/segredos; não publicar ou reiniciar Nyx pessoal.
- 01/11/2026 13:03 — Usuário aprovou suspensão pública. Guarda antes de upload,
  nuvem desabilitada na UI, preferências false em fonte/instalação; backups,
  chave e outras preferências preservados. Ensaio real3/3 bloqueados, snapshots e
  chaves intactos. Instância pessoal não reiniciada; executáveis antigos têm limite.
  Regressão:915 aprovados,27pulados,zero falhas,56,581s,saída0; Ruff limpo.
- 01/11/2026 12:58 — Win32 confirmou janela foreground visível e OpenClipboard
  acessível; nenhum conteúdo do clipboard lido. Probe interativo passou nesta sessão.
- 01/11/2026 12:59 — Pacote lido e instalado sem sobrescrever arquivos existentes;
  branch nyx-2 preserva todos os commits. Plano em PLANO_EXECUCAO.md. Repositório
  público/branch backup confirmados por metadados; proposta ainda não executada.
- 31/10/2026 — Última regressão antes do pacote: 913 aprovados,27 pulados,zero
  falhas,52,136s,saída0; Ruff limpo. Windows/browser habilitados,LPAC opt-in pulado.
- 31/10/2026 — Baseline Shadow DOM: 0/3, erros reais de localizador não aceito;
  fixture e driver ainda em preparação, nenhuma mudança de runtime aplicada.
