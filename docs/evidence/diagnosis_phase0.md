# Diagnóstico real — 31/10/2026

Base: `8bc57b5`. Fase 0 **parcial**, sem aceite das fases 0/1 nem alegação de
AGI. O prompt novo substitui a prioridade anterior: núcleo funcional primeiro.
Pet/overlay não alterados. Sensores, permissões e reservas não foram ampliados.

## Método e baseline

`tools/diagnose_capabilities.py --open-apps --output <json>` usa UITool,
catálogo e verificador de produção no Windows real, três vezes por nome.
Não usa LLM nem respostas simuladas; portanto não mede planejamento ponta a
ponta. Não fecha programas nem digita em janelas pessoais. Spotify/WhatsApp
seguem a rota web existente em perfil temporário headless, sem login.
Esse modo é exclusivo do diagnóstico; não altera preferências do desktop.

`baseline_2026-10-31.json`: 15 nomes, três repetições, cinco retornaram `ok`
em todas as chamadas, mas **só três tiveram verificação positiva**: Steam e
duas navegações web. Calculadora/Bloco de notas receberam o comando, mas não
tiveram janela confirmada. Não são sucessos. Nomes não resolvidos não provam
que o programa esteja instalado ou ausente. Chrome/VS Code ainda precisam de
inventário independente; não foram instalados para aumentar a pontuação.

Tempos individuais e mediana por nome estão nos JSONs. Repetições incluem
estado já aberto; não equivalem a três cold starts. Recursos são amostras antes
e depois, **não picos**. Top 10 RSS contém nomes/bytes, sem linha de comando,
PID, hostname, títulos ou conteúdo do usuário. Resultados brutos ficam somente
em `build/diagnostic/`. Não há ainda verificador independente completo.
Traces por tarefa foram conectados ao runtime principal após o baseline:
decisões, resposta bruta limitada pela auditoria existente, ações, verificação,
saúde e metadados de geração vão para logs/traces/<task_id>.jsonl, ignorados
pelo Git. O prompt completo e ToolResult completo ainda não são capturados.

Regressão baseline: **830 aprovados, 27 pulados, zero falhas, 63,029 s**
(857 casos), Windows e navegador opt-in habilitados. Fonte local:
`build/diagnostic/phase0-regression.xml`. Ruff src/tests/tools aprovado.
O ensaio isolado de navegador real passou 11 casos, incluindo entrada Unicode,
abas, persistência do perfil próprio e mídia silenciosa; não prova login nem
som físico. Não cobre os seis sites reais, iframe/shadow DOM ou a bateria total.

## P1–P12: diagnóstico dividido por afirmação

| Item | Veredito e evidência |
|---|---|
| P1 | CONFIRMADO em reprodução: três aberturas de aplicativo inexistente desativaram ui_action e bloquearam list_windows (`breaker_before_2026-10-31.json`). REFUTADO como explicação universal de seis passos: extensão até 48 já existe; causas de cada tarefa exigem seu trace. |
| P2 | CONFIRMADO: catálogo limitado e aliases ausentes; 3/15 nomes resolvidos na sondagem inicial somente leitura. Abertura é medida separadamente. |
| P3 | CONFIRMADO para Calculadora/Notepad: despacho sem janela verificada em três execuções. Limite de quatro segundos no código. Steam já reconhecia renderer por ancestral. |
| P4 | CONFIRMADO: contrato anuncia dez ações. Outras existem no dispatcher; dizer que são tecnicamente impossíveis de emitir seria excessivo. |
| P5 | CONFIRMADA restrição: amostra inicial com 2,25 GiB RAM/10,22 GiB VRAM livres produziu contexto 1024. REFUTADA conclusão causal definitiva de que todo modelo 4B é incapaz: ensaio de nove ações passou em 30/10. Benchmark comparativo pendente. |
| P6 | CONFIRMADO no código: sete chaves e stream=false. Latência por primeiro token ainda não medida. |
| P7 | REFUTADO padrão invisível no desktop: browser_visible=True. Persistência opt-in comprovada na fixture. CONFIRMADAS limitações de frames/shadow DOM; scraping ainda depende dos provedores. |
| P8 | CONFIRMADO no registro/configuração: ui_action sensível inteiro e autônomo não persiste. Bateria de contagem de confirmações ainda pendente. |
| P9 | CONFIRMADO: sensores externos desligados por padrão, sem percepção geral; eventos internos existem. Não habilitados nesta revisão. |
| P10 | CONFIRMADO FTS sem busca vetorial integrada. REFUTADA ausência absoluta de UI de memória: interesses já podem ser corrigidos/apagados em desktop.py. Consolidação/recordação ampla não validadas. |
| P11 | CONFIRMADO wake word textual; REFUTADA inferência de transcrição contínua obrigatória: main.py inicia captura por atalho/botão. Latência/voz real não medidas. |
| P12 | CONFIRMADOS dois JSONs de runtime versionados e empacotamento UIA pendente. Não foi calculada proporção de mocks nem executada varredura completa de segredos no histórico. |

## Inferência local

Primeira consulta /api/ps e /api/tags: WinError 10061, serviço indisponível.
O serviço existente foi iniciado pela função de produção ensure_local_ollama,
com limites locais. A segunda abordagem encontrou os modelos, mas o ensaio de
oito leituras foi recusado: **"O modelo não cabe no orçamento atual ou seu tamanho
não pôde ser confirmado. Libere memória e tente novamente."** Zero ações, 0,17 s.
Inventário confirmou Qwen3.5:4b instalado; amostra posterior mostrou orçamento
3.209.195.520 bytes com 2.143.473.664 bytes RAM livres, abaixo dos pesos do 4B.
Nenhum modelo menor substituiu o escolhido; nenhum aplicativo foi encerrado.

## Correções medidas após reprodução

- Breaker passa a escopo ferramenta/operação/alvo, cooldown de 60 s, uma tentativa
  de recuperação, backoff até 600 s. Não verificado tem contador separado e não
  abre o breaker. Registro central cobre microagentes; novas tarefas limpam
  bloqueios transitórios, preservando disabled_tools administrativo.
- Ensaio idêntico `breaker_after_2026-10-31.json`: três falhas reais preservadas,
  list_windows passa. 0,2032 s antes/0,3437 s depois; não há ganho de velocidade
  alegado. Testes unitários usam relógio injetável para cooldown/concorrência.
- Aliases falados, pastas fixas, atalhos sem argumentos e AppsFolder registrado.
  UWP exige identidade do processo via GetApplicationUserModelId, incluindo
  filhos do host de janela. Não usa título como prova. Nomes aproximados geram
  sugestões, nunca abertura automática. Executáveis explícitos mantêm restrições.
- `apps_after_2026-10-31.json`: 9/15 nomes verificados em todas as repetições,
  dois pela rota web. `apps_uwp_after_2026-10-31.json`: 10/15; Calculadora e
  Configurações passam. Antigravity falha nas duas primeiras verificações e passa
  na terceira: não ocultado. A espera foi ampliada para 20 s após esse resultado.
- Uma regressão intermediária detectou que a operação `op` de skills não entrava
  na chave do breaker; corrigido no núcleo, sem alterar a ferramenta congelada.
  Relatório com a falha preservado em build/diagnostic/phase1-regression.xml.
- Rodada final de aplicativos: **13/15 nomes verificados três vezes**, 11 por
  janela nativa e dois pela rota web. Discord reconhecido somente pelo executável
  versionado na mesma instalação; PID/HWND continuam sendo revalidados. Chrome e
  VS Code não encontrados nas fontes consultadas. Planilha comparativa com tempos
  e desvio padrão: `baseline_2026-10-31.md`; dados: `apps_verified_2026-10-31.json`.
- Regressão integrada final: **845 aprovados, 27 pulados, zero falhas, 54,694 s**.
  Ruff aprovado; metadados sanitizados em `regression_2026-10-31.json`.
  Windows/navegador reais habilitados; LPAC opt-in não habilitado nesta rodada.
- Central → Saúde das ferramentas mostra escopo, falhas, resultado sem verificação
  e cooldown. Reativação explícita preserva interrupção de emergência e desativação
  administrativa. Teste Qt comprova ambos; prévia visual local revisada com fonte
  Segoe UI em build/previews/tool-health-readable.png. A primeira prévia offscreen
  não tinha fonte carregada; não foi aceita como revisão visual.
- Contrato de desktop ampliado de 10 para 16 ações existentes. Não anuncia scroll
  livre nem entrada sem alvo: essas rotas ainda precisam de revisão de segurança.

Referência da identidade de processo: [Microsoft GetApplicationUserModelId](https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getapplicationusermodelid).

## Pendências para aceite

Diagnóstico completo via modelo/UI; 40+ tarefas com verificador independente,
três repetições, variância e picos; pesquisa externa; ações desktop diversas;
comparativo de modelos; progressão por objetivo; catálogo de
atalhos com argumentos/launchers arbitrários; bateria adversarial de identidade.
As fases seguintes permanecem pendentes. Nenhuma reserva foi afrouxada para
forçar aprovação do modelo e nenhum resultado parcial significa fase concluída.
