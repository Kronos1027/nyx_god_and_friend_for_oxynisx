# M0 parcial e correção do método de soma — 01/11/2026

## O que foi observado

O inventário tem50casos/150tentativas. No incremento inicial, nove tentativas
foram executadas no modelo real;141 ficaram BLOCKED_HARNESS, sem sucesso padrão.
Isso não fecha M0 nem indica que as capacidades bloqueadas sejam impossíveis.

O checker inicial de arquivos validava valores e soma, mas não conferia a etapa
explicitamente pedida de calculator. A auditoria posterior encontrou:

| Rodada original | Leituras verificadas | Cálculos verificados | Números corretos | Método integral |
|---|---:|---:|---|---|
| 1 | 8 | 0 | sim | falhou |
| 2 | 8 | 1 | sim | passou |
| 3 | 8 | 1 | sim | passou |

**Não interpretar o PASS antigo da primeira rodada como cumprimento completo.**
O JSON bruto foi preservado; a revisão está em
bench_2026-11-01_M0_partial_assessment.json. O verificador foi apertado, não
afrouxado: agora exige também o método pelo ledger de ações de produção.
O checker independente continua conferindo os valores/soma pelos arquivos e
texto final; o ledger não é apresentado como auditoria independente de leitura.

## Correção e medição posterior

`final_sum_issue` agora interrompe a conclusão numérica quando o pedido estreito
de soma de arquivos exige calculator e não há soma verificada da ferramenta.
O TaskRunner usa o replanejamento existente, limitado a duas correções, antes
de retornar erro. Não altera permissões, modelo ou orçamento de recursos.
Pedidos de esclarecimento sem total numérico não são forçados a calcular.

bench_2026-11-01_calculator_required.json: **3/3 passaram**, cada um com oito
leituras distintas e uma soma verificada por calculator, resultado396. Tempos:
26,468 / 28,640 / 26,375 s. Correções automáticas:1 /2 /1. Método estrito
**2/3→3/3**. Mediana de tempo24,093→26,468s; cache e carga não controlados,
portanto não atribuir toda a diferença ao código. Somente um tipo de tarefa;
a categoria multi-etapa inteira permanece abaixo do gate por cobertura faltante.

## Conversa, retomada e qualidade

O relatório parcial também contém três saudações e três identidades corretas.
Primeiro trecho de saudação:0,266 /0,297 /0,250s. Identidade é retida para
conferência, com entrega0,766 /0,719 /0,781s. São medições do executor, não áudio
ou apresentação física no monitor. O script run_live passou o subconjunto de
conversa com saída0; JSON do gate termina em14-19-13_M0.

A execução inicial terminou durante uma leitura, sem finalizar150linhas; causa
externa não determinada. Um trace local tem cauda incompleta iniciada por NUL,
preservada fora do Git. A retomada preservou linhas concluídas; uma gravação
encontrou WinError5 de compartilhamento. Escrita atômica, tentativa limitada e
retomada explícita foram adicionadas e exercitadas; todas150linhas foram
finalizadas, sem repetir casos já registrados. Somente rotas R0 podem retomar.

Regressão final após a guarda: **927 aprovados,27 pulados,zero falhas,48,889s**,
saída0; Ruff limpo incluindo bench/. Windows/browser reais habilitados; LPAC
opt-in pulado. Fonte local: build/diagnostic/m0-method-final.xml.
Antes da guarda, o script oficial também passou902testes unitários+23Windows
reais;27pulados no total. Números distintos são execuções distintas.

Não validados: 47setups/verificadores seguros restantes, bateria de apps/desktop
do planejador, seis sites reais, login Spotify, voz, Modo Privado/Live, UI HUD
completa, pico exclusivo de VRAM/RAM da Nyx e soak2h. Pet/overlay preservados.
