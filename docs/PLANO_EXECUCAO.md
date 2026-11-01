# Plano de execução — Nyx 2

Atualizado em 01/11/2026. Branch `nyx-2`, criada a partir de `5fc8ee5`, preservando
os commits de correção da branch anterior. O pacote recebido define o roteiro;
os diagnósticos estáticos do SPEC serão confrontados com o código e as evidências,
não considerados fatos atuais automaticamente. Não há mudança de modelo do Codex
ou de modo de colaboração por instrução de documento; este plano é executável
no modo atual, sem aguardar aprovação entre decisões reversíveis.

## Estado herdado e lacunas

- P1–P12 já têm confirmação/refutação por afirmação em
  [diagnosis_phase0.md](evidence/diagnosis_phase0.md). Breaker por alvo,
  catálogo/UWP/aliases, espera de janela, contrato, traces e observação R0 existem.
  Apps: 13/15 nomes, dois pela rota web; não prova o gate de 15 apps nativos.
- Perfis manuais Normal/Jogo/Foco e Conservador, comparação real 4B/9B, soma
  guardada e seis tarefas finais aprovadas antes da última compactação de prompt.
  Repetição mais recente interrompida por RAM baixa; não requalificada.
- Saudações em fluxo medidas com Qwen4, primeiro trecho abaixo de 1,5 s nesses
  casos aquecidos. Persona teve falha real, preservada e parcialmente tratada.
  Tool calling nativo, roteador geral, KVq8/flash-health e detecção automática faltam.
- Diálogo sob demanda de recursos validado com dados reais e consulta explícita.
  Última suíte anterior à adoção do pacote: 913 aprovados, 27 pulados, saída 0.
- Baseline de Shadow DOM: três falhas reais, arquivo versionável preparado;
  nenhuma correção dessa capacidade aplicada ainda. Não declara M3 aprovado.

## Marcos, entrega e verificação

| Marco | Trabalho e ordem | Evidência/gate | Risco e contenção |
|---|---|---|---|
| M0 | Integrar regras; revisar higiene; adaptar baseline existente; criar manifesto, runner e script live; verificar sessão interativa; proposta de backups | Baseline por tarefa, três execuções, verificador independente, P1–P12, falhas e métricas preservadas | Não reescrever histórico, mover backups ou publicar; ações pessoais não fechadas por harness |
| M1 | Completar erros tipados, contratos e estratégias por alvo; catálogo/verificação já corrigidos serão requalificados pelo runner | Apps≥95%, Desktop≥90%, falso sucesso0 | Fixtures isoladas; fechar somente janelas comprovadamente criadas pelo ensaio; nunca processos pessoais |
| M2 | Completar roteador geral e protocolo nativo com fallback explícito; saída por tipo; saúde de KV/flash e modelo por evidência | Primeiro trecho<1,5s, multi-etapa≥80%, pico Normal≤9,5GiB, preferido não adiado indevidamente | RAM/VRAM reais, sem reduzir reservas; modelos existentes antes de qualquer download |
| M3 | Spike CDP/Playwright; AX refs; frames/shadow; abas/arquivos/mídia; pesquisa com fontes | Navegador≥85%, Pesquisa≥85%, três fontes, três execuções | Perfil Nyx isolado; login humano; nenhum cookie/senha pessoal exportado |
| M4 | UIA auxiliar empacotável; entrada/janelas; habilidades verificáveis por app; OCR/visão sob demanda | Desktop≥90%, dez apps e DPI100/125/150% | Nada de injeção em jogos; não operar sessão pessoal da Nyx sem nova instrução |
| M5 | Riscos R0–R3, aprovação vinculada ao plano, Parceira persistente, allowlists/revogação/parada | Seis passos R0/R1≤uma confirmação; R3 sempre confirma em casos adversariais | Não promover efeitos externos a R1 por conveniência ou saída do modelo |
| M6 | Presença consentida, Privado/Live, memória relevante/proveniência e voz por ativação | Presença/memória≥90%, nenhuma coleta/fala em Privado/Live, wake→fala<2,5s | Sensores ficam desligados até aceite; não gravar imagens/áudio por padrão |
| M7 | Tokens e shell HUD em módulos, fontes/ícones locais licenciados, cartões e Agora com dados reais | QA de todas as telas, dois temas/três escalas, check_ui, QTest, RAM≤180MiB/CPU<1% | Preservar assets, renderer, rotina e comportamento do pet; refatoração separada de comportamento |
| M8 | Bateria completa, segurança, soak2h, documentação final e branch revisável | Todos os gates anteriores e falso sucesso0 | Não publicar/mesclar/release sem decisão do usuário |

Os mínimos enumerados no bench-spec somam **50 tarefas** (15+8+10+5+4+6+2),
embora o cabeçalho diga 40. O manifesto usará a lista completa; não reduzirá
exemplos para obter taxa maior. Taxa por execução, mediana das três execuções,
contagem agregada e variância serão mantidas, com bloqueados/indisponíveis
separados de passes. Um verificador de produção não conta como independente.

## Sequência imediata e decisões

1. Salvar documentação/progresso e baseline já observado; nenhuma perda de trabalho.
2. Checar foreground/clipboard sem ler conteúdo para saber o que pode ser executado
   nesta sessão; providenciar `tools/run_live.ps1` para as partes indisponíveis.
3. Estruturar runner e manifesto com verificadores independentes e sem sucesso
   padrão. Completar baseline M0 antes de promover qualquer marco.
4. Retomar M1 pelas lacunas medidas. A correção Shadow DOM iniciada antes do pacote
   fica explicitamente em fila M3; não será apresentada como fechamento antecipado.
5. Aguardar decisão só para backups (AGENTS§10); trabalho independente continua.

Não estimar horas de aceite sem conhecer o baseline completo. O número de testes
unitários não substitui os gates. `docs/PROGRESS.md` registra o próximo comando
exato e cada erro que impeça a verificação real.
