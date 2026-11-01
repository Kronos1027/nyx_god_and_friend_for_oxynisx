# PROGRESS — memória externa do trabalho (atualize ao fim de cada passo relevante)

**Marco atual:** M0 (integração e baseline ampliado) · **Branch:** nyx-2 · **Base preservada:** 5fc8ee5
**Próximo passo exato:** verificar acesso real a foreground/clipboard sem ler conteúdo; implementar manifesto50/runner independente e tools/run_live.ps1 antes de fechar M0.
**Como retomar:** `git switch nyx-2` · ler AGENTS.md, este arquivo e docs/DECISOES.md · rodar `python -m pytest -q`
**Bloqueios:** decisão sobre proposta de backups pendente; não bloqueia runner/correções. Fluxo de oito arquivos parou por RAM0,86/0,90GiB nas últimas repetições. Login Spotify continua adiado pelo usuário.

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
- 01/11/2026 12:59 — Pacote lido e instalado sem sobrescrever arquivos existentes;
  branch nyx-2 preserva todos os commits. Plano em PLANO_EXECUCAO.md. Repositório
  público/branch backup confirmados por metadados; proposta ainda não executada.
- 31/10/2026 — Última regressão antes do pacote: 913 aprovados,27 pulados,zero
  falhas,52,136s,saída0; Ruff limpo. Windows/browser habilitados,LPAC opt-in pulado.
- 31/10/2026 — Baseline Shadow DOM: 0/3, erros reais de localizador não aceito;
  fixture e driver ainda em preparação, nenhuma mudança de runtime aplicada.
