# M2/M3/M7 · integração real · 02/11/2026

Estado: **parcial**, com limitações separadas abaixo. Pet/overlay preservados.

## O que mudou e o que aconteceu de verdade

- M7 integrado: conversa primeiro, Midnight/Daylight, SVG/fontes licenciados,
  painel Agora, cartões de ação e confirmação inline, pausa de contexto sem
  apagar consentimento/histórico. [QA visual M7](m7_hud_2026-11-02.md).
- M3 integrado: Shadow DOM, frames de mesma origem, AX com refs ligadas a
  documento/aba e TTL, ações click/type/select/hover/press. Navegador visível e
  perfil próprio persistente por padrão; opt-out explícito preservado.
  [Shadow/AX](m3_shadow_ax_2026-11-02.md),
  [ações/perfil](m3_actions_profile_2026-11-02.md).
- Roteador por regex de saudações removido. Classificador local decide conversa
  × tarefa, sem conceder permissão; erro/incerteza usa planejador com aviso.
  Histórico recente é considerado, pedido grande nunca é cortado para classificar.
  Conversa geral recebe texto livre com streaming, sem ferramentas/schema de ação.
- Inicial encontrou pedido misto classificado incorretamente: 17/18, preservado
  em [rodada inicial](intent_route_initial_2026-11-02.json). Critério de intenção
  mista reforçado com exemplos distintos. Nova amostra de 24 pedidos ×3:
  **72/72**, incluindo seis pedidos adicionais. Não é teste universal de intenção.
  [Resultados](intent_route_2026-11-02.json).
- TaskRunner real: duas conversas gerais, zero ações, primeiro delta incluindo
  classificação em 0,531/0,594s. HUD de produção com modelo 4B: primeiro rótulo
  em **0,672s**, zero ações. [HUD](hud_conversation_2026-11-02.json).

## RAM fria, padrão e degradação

[Três cargas frias 4B](cold_load_2026-11-02.json), em servidor próprio isolado,
sem downloads ou alterações da instância pessoal: **3/3**, contexto8192, pesos
e contexto totalmente na GPU pelo inventário do runtime. Tempos14,219/3,328/3,032s;
cache de arquivos do Windows não esvaziado. Pico RSS agregado do servidor/filhos
~1,20GiB; private commit ~6,15GiB. RSS e commit **não são a mesma métrica**.
RAM livre no início5,21–5,26GiB; mínimo durante amostragem~4,09GiB.

O mínimo necessário real continua desconhecido: não se preencheu RAM artificialmente
nem se forçou paginação no disco do sistema. O piso antigo de RAM2,5GiB não foi
validado e foi substituído por uma faixa operacional provisória arredondada para
**5,3GiB** na admissão fria dos perfis GPU. Isto é conservador e pode recusar
cargas que funcionariam abaixo desse valor; não o chamar de mínimo físico.
Reuso exato já residente continua distinto de carga fria. Piso crítico1GiB e
reservas/proteções de GPU preservados.

Sem escolha manual salva: Normal passa a padrão com RAM na faixa observada e
VRAM suficiente; fora dela, Conservador com motivo visível. Escolhas manuais
existentes preservadas. Preferência principal continua salva; se não admitida,
pode ser usado um modelo menor **já instalado**, com aviso persistente no chat.
Sem candidato seguro, espera recursos. Não retorna ao principal silenciosamente.

[Seleção real pelos recursos atuais](automatic_runtime_2026-11-02.json):
Conservador e Qwen3B no lugar do4B, com aviso; três cargas3/3 em
9,140/2,312/2,312s, contexto2048 e GPU~1,94GiB. Pico RSS agregado~746MiB;
private commit~3,01GiB. Não mede limite mínimo desse modelo.
[HUD com seleção de produção](hud_degradation_2026-11-02.json): aviso realmente
visível e primeiro delta0,391s, zero ações.

**Qualidade factual não aprovada pelo teste de streaming:** os textos sintéticos
incluem imprecisões, como dizer que estrelas “refletem” a luz de seus núcleos e
generalizar distâncias em bilhões de anos-luz. Os JSONs preservam as respostas;
`passed` nesses probes mede entrega/rota/ausência de ações, nunca verdade factual.
Modelos menores têm perda de capacidade real; a UI informa essa degradação.

## Falha real do app e correção

Pelo HUD e modelo3B, “abre a Calculadora” inicialmente escolheu a ferramenta
aritmética: **0/3**, zero janelas, zero falso sucesso entregue. Preservado em
[ensaio inicial](native_hud_2026-11-02.json). Não é bloqueio de ambiente.

Corrigidos catálogo e grounding de pedidos simples de abrir app: só ui_action
é candidata; calculator faz contas, não abre a Calculadora. Conclusão exige
observação verificada do alvo correto. Confirmação/permissões continuam no motor.

[Novo ensaio](native_hud_recheck_2026-11-02.json): **1 abertura nova/1 executada**,
8,704s, uma confirmação no cartão de produção, uma ação, janela visível/identificada/
sem cloaking pelo verificador Win32 independente, foco separado confirmado,
zero falso sucesso. As outras duas rodadas foram **BLOCKED_ENVIRONMENT**: a
Calculadora permanecia aberta, com instrução para fechar antes. Não fechada por
nome/PID sem ownership. Não apresentar esse resultado como3/3 ou gate Apps95%.
Pico RSS do harness/filhos280,95MiB; GPU total do sistema3273,39MiB. Não mede
isoladamente a UI nem alocação exclusiva da Nyx.

## Gate, riscos e próximo marco

Ruff e testes agregados: [resumo sanitizado](integration_gate_2026-11-02.json).
**Gate completo final:987passes/65skips,0falhas,47,432s**; após a pequena limpeza
do aviso automático numa escolha manual, teste de persistência de perfil passou.
Compatibilidade do novo estado BLOCKED_ENVIRONMENT com checkpoint corrigida;
quatro testes focados passaram, preservando bloqueio de retomada de efeitos.
Regressão completa anterior à última correção visual:986passes/65skips,0falhas,
48,765s. Windows live:39passes/26skips,0falhas,20,560s (opt-ins indisponíveis
preservados). QA visual integrado:9/9 interações,0cortes horizontais medidos,
contraste aprovado. Capturas privadas em build/previews, fora do Git.

[Runner Navegador3×](bench_browser_hud_2026-11-02.json):30/30 **BLOCKED_HARNESS**,
porque os dez cenários completos ainda não têm setup/verificador seguro; isso é
implementação pendente do harness, não prova de incapacidade ou gate aprovado.
Os26 casos reais de browser/componentes não substituem esses fluxos pelo modelo/UI.

M0/M1 continuam **parcial: bloqueado por ambiente** (reset/foco/RAM). M2 parcial
por mínimo frio/qualidade/modelos/tarefas complexas não qualificados. M3 parcial
por gate completo, OOPIF, mídia/login/upload/download/pesquisa pendentes. M7
parcial: primeira pintura nativa3,541s excede meta1,2s; sensores Agora, onboarding,
OBS e processo completo com modelo não aprovados. UI demo nativa145,28MiB/
0,312%CPU não equivale à sessão completa.

Próximo: conectar cenários browser seguros ao runner via HUD/modelo, medir
inicialização nativa e retornar aos apps apenas com reset comprovadamente próprio.
