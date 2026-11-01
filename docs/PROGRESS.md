# PROGRESS — memória externa do trabalho (atualize ao fim de cada passo relevante)

**Marco atual:** M0 (integração e baseline ampliado) · **Branch:** nyx-2 · **Base preservada:** 5fc8ee5
**Próximo passo exato:** ampliar o runner M0 com fixture Qt de produção para aprovação R1 e verificador Win32 independente de abertura de apps; ler a skill desktop e app-launch-ladder antes de editar. Não reexecutar o relatório legado como se o método estivesse aprovado.
**Como retomar:** `git switch nyx-2` · ler AGENTS.md, este arquivo e docs/DECISOES.md · rodar `python -m pytest -q`
**Bloqueios:**47setups/verificadores do harness pendentes, sem inferir incapacidade da Nyx. Login Spotify adiado pelo usuário. Migração privada/remoção remota fora do escopo aprovado. Requalificação atual de arquivos passou3/3; antigas recusas de RAM permanecem como histórico.

## Marcos
| Marco | Status | Evidência | Gate (limiares) | Notas |
|---|---|---|---|---|
| M0 Fundação e baseline | em andamento | evidence/diagnosis_phase0.md | baseline ampliado/independente pendente | P1–P12 já avaliados; higiene parcial |
| M1 Destravar | parcial herdado | evidence/diagnosis_phase0.md | Apps ≥ 95% · Desktop ≥ 90% | 13/15 nomes, dois web; falta bateria independente completa |
| M2 Cérebro e recursos | parcial herdado | evidence/resource_profiles_2026-10-31.md; evidence/conversation_stream_2026-10-31.md | 1º token < 1,5 s · multi-etapa ≥ 80% · VRAM ≤ 9,5 GiB | Perfis/saudações medidos; não conclui o gate |
| M3 Navegador e pesquisa | pendente | | Navegador ≥ 85% · Pesquisa ≥ 85% | |
| M4 Desktop robusto e habilidades | pendente | | Desktop ≥ 90% · 10 apps com habilidade validada | |
| M5 Confiança graduada | pendente | | tarefa de 6 passos com ≤ 1 confirmação; R3 sempre confirma | |
| M6 Presença, memória e voz | pendente | | Presença/memória ≥ 90% · voz < 2,5 s | |
| M7 Interface Nyx HUD | pendente | | QA visual + check_ui + perf | |
| M8 Aceitação final | pendente | | bench 3× completo · soak 2 h · falso sucesso = 0 | |

## Log (mais recente primeiro)
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
