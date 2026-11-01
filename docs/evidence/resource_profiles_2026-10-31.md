# Perfis de recursos e modelo real — 31/10/2026

## Retomada com memória disponível

RAM inicial: 4.569.915.392 bytes; VRAM livre: 11.624.050.688 bytes. Com a política
conservadora, Qwen3.5:4b executou **nove ações, oito leituras verificadas e soma
396 em 45,74 s**, com ampliação além de seis. Steam consultada de verdade:
o modelo propôs list_steam_games e escolheu Stardew Valley entre os observados.
Não iniciou jogo nem controlou interface. JSONs: task_memory_restored e
steam_memory_restored desta data. Isso resolve o adiamento desses ensaios,
não a bateria completa de desktop/planejamento.

## Perfis manuais implementados

Personalizar → Modelo local → Perfil de recursos. Escolha persistida e carregada
antes da seleção inicial do modelo. Mudança bloqueada durante tarefa em andamento.
O padrão continua **Conservador**, preservando instalações existentes. Nenhum
modelo principal fixado foi alterado. Modelos ausentes não são baixados.

| Perfil | Contexto máximo de carga nova | Reserva VRAM livre | Reserva estimada de KV | Residência |
|---|---:|---:|---:|---|
| Conservador | 4K, dinâmico 1–4K | 4 GiB | política anterior | 5 min |
| Normal | 8K | 2,5 GiB | 1 GiB | 10 min |
| Jogo/Live | 4K | 7 GiB | 0,5 GiB | keep_alive=0 |
| Foco | 16K | 2,5 GiB | 1,5 GiB | 15 min |

Novos perfis exigem pelo menos **2,5 GiB RAM livres para carga fria**. Pesos
candidatos são limitados por VRAM livre menos reservas, sem multiplicar o
orçamento dos pesos pela RAM. CPU e modo conservador mantêm sua regra anterior.
O piso duro de 1 GiB RAM/768 MiB VRAM continua. Residência só é reutilizada com
nome/digest exatos e size==size_vram; contexto compatível já alocado não cresce
automaticamente. Perfil Jogo recusa residentes acima de 5 GiB e suspende trabalho
de fundo, sem escolher silenciosamente outro modelo.

Reservas de KV são estimativas, não cálculo universal por arquitetura. Não foi
forçado flash attention nem q8_0 nesta entrega: continuam dependentes de teste de
saúde do serviço/versão. Contexto maior não garante melhor planejamento.

## Conversa real: três chamadas por combinação

Medida é resposta JSON completa, **não primeiro token**. Uma carga fria por
combinação, duas chamadas residentes; Jogo descarrega a cada resposta e não tem
amostra residente. Datas/versão/cache/condições podem mudar entre combinações;
tempos frios não isolam ganho do perfil. Todos os 15 cumprimentos retornaram
JSON válido e nenhuma ação. Fontes: profile_bench_4b, profile_bench_9b e
profile_bench_modes desta data.

| Modelo/perfil | Contexto observado | Tempos (s) | Pico GPU do sistema amostrado |
|---|---:|---|---:|
| 4B Conservador | pedido 1K inicial; residente 2K | 8,439 / 1,682 / 1,605 | 4,78 GiB |
| 4B Normal | 8K | 5,016 / 1,662 / 1,693 | 5,06 GiB |
| 9B Normal | 8K | 22,274 / 2,756 / 2,883 | 7,61 GiB |
| 4B Jogo/Live | 4K | 15,978 / 5,756 / 7,141 | 4,99 GiB |
| 4B Foco | 16K | 15,807 / 1,826 / 1,678 | 5,42 GiB |

Amostragem a cada 250 ms, incluindo antes/depois. Pico do **sistema inteiro**,
não atribuição exclusiva à Nyx; pode perder transientes entre amostras.
9B Normal reportou size_vram=5.862.210.928 bytes, contexto 8192, inteiramente
GPU segundo size==size_vram. Menor RAM livre nessa combinação: 3.719.127.040
bytes. Em Foco 4B a RAM mínima foi 2.389.319.680 bytes. Jogo/Live reportou lista
de residentes vazia após as três respostas. Não é promessa de latência de voz
nem de ausência de disputa com jogo/OBS em uso real.

## Estratégia e limites do ensaio de arquivos

O primeiro ensaio 9B foi bloqueado pela guarda antes de qualquer leitura:
ele escolheu agent_team, que o catálogo de stress anuncia mas o diagnóstico
não permite executar. Nova tentativa registrou a proposta e confirmou delegação.
Isso não comprova incapacidade de ler arquivos. Foram preservadas as tentativas.

Quando pedido explicitamente o método direto, o 9B ainda tentou delegar após
duas leituras. Restrição explícita agora retira agent_team do catálogo e a guarda
impede sua execução mesmo se um backend ignorar o catálogo. Conteúdo observado
não modifica essa restrição; ela vem somente do objetivo original do usuário.

Testes 4B em 8K com catálogo amplo também mostraram leitura de numero-9.txt fora
do conjunto e proposta de ferramenta sensível após as oito leituras. A guarda
recusou; essas rodadas não passaram. Três rodadas 4B anteriores foram recusadas
por falta de VRAM porque outro modelo do próprio benchmark permanecia residente;
não são falhas semânticas. O driver novo descarrega somente os modelos escolhidos
entre fases para corrigir essa confusão de comparação.

Foi acrescentada seleção pequena de ferramentas para pedidos estritamente de
leitura+cálculo. Pedidos mistos (salvar, pesquisar, enviar, delegar etc.) preservam
o catálogo amplo. Isso limita descoberta e schema, sem conceder permissões.
Comparação após essa correção usa o mesmo método direto nos dois modelos e exige
oito leituras, soma, extensão, nenhuma ação recusada e nenhuma confirmação pendente.

Não foi promovido automaticamente o 9B como melhor planejador. Faltam tarefas
variadas, verificador independente completo, streaming, voz, auto detecção
consentida de Jogo/Live e coordenação completa de Whisper/Kokoro/visão.

## Falso sucesso encontrado e correção de aritmética

Na comparação após poda, 4B entregou 396 em duas de três rodadas. 9B teve uma
rodada que entregou 396 após reler um arquivo (método estrito reprovado por leitura
extra), uma rodada estrita aprovada e uma que entregou **484**, incorretamente.
Os relatórios originais estão em files_pruned_2026-10-31. Esse último caso é
**falha crítica**, não simples problema do avaliador. Os gates seguem bloqueados.

Acrescentada conferência estreita para pedidos explícitos de ler arquivos
numéricos e somar: operandos devem corresponder às leituras verificadas, um
valor por caminho, preservando números iguais vindos de arquivos diferentes.
Não aceita somar novamente um subtotal ou trocar soma por produto. Se a resposta
final declarar total diferente da calculadora observada, pede replanejamento
sem executar a proposta errada. Até duas correções, sujeitas ao prazo original;
persistindo a contradição, encerra com erro em vez de afirmar sucesso.

Isso não é verificador semântico universal. Declina restrições quando o conteúdo
não é um único número, o pedido mistura outras operações ou os dados são
insuficientes. Normalização de caminhos é lexical: aliases absolutos/relativos
do mesmo arquivo ainda precisam de identidade canônica no resultado da ferramenta.
A validação da fala cobre declarações numéricas explícitas de soma/total/resultado;
não compreende qualquer frase ou número por extenso. Pedidos de média/composição
de operações não são tratados por essa regra estreita.

Novos passos agora guardam o caminho resolvido retornado pela ferramenta de
arquivo e o resultado estruturado da calculadora. Isso permite deduplicar aliases
absolutos/relativos do mesmo caminho sem depender da representação pedida pelo
modelo, e evita perder o resultado numérico quando a prévia JSON é truncada.
Históricos legados sem esses metadados mantêm apenas a normalização lexical;
hardlinks/identidade por handle e variantes ambíguas não são generalizados aqui.

O benchmark agora também distingue método estrito (oito leituras) de entrega do
objetivo (todos os valores, soma correta, nenhuma ação recusada ou pendência),
registrando leituras redundantes. Essa métrica adicional não converte uma resposta
484 em sucesso e não altera os resultados estritos originais.

## Rodada final após guarda de intervalo

**6/6 aprovadas**, três por modelo, todos os oito valores, soma 396 e nove ações.
Nenhuma leitura fora do conjunto foi executada. 4B: 38,84 / 25,86 / 24,72 s;
9B: 59,58 / 33,59 / 41,20 s. Medianas 25,86 e 41,20 s, respectivamente.
Cada rodada 4B usou uma correção automática antes de tentar ler um arquivo extra.
Replanejamentos e resultados estão nos relatórios files_interval_guard_2026-10-31.

Na primeira geração 4B, a redução de catálogo baixou prompt_eval_count de 1671
para 404 tokens (estimativa interna 2237 → 616), comparando as rodadas diretas
task_scoped_4b_2 e files_pruned/model-1-run-2. Esses números são de entrada;
as mudanças de tempo também dependem de carga/cache, não apenas da poda.

Decisão local: manter a preferência existente 4B e o padrão Conservador; Normal
fica disponível explicitamente para quem deseja 8K. 9B é opção manual medida,
não promoção automática por três cumprimentos. Seis execuções de um único tipo
de tarefa não comprovam 80% de sucesso em tarefas variadas nem eliminam todo
falso sucesso. A fase 2 inteira permanece aberta.

Regressão final com metadados canônicos: **883 aprovados, 27 pulados, zero falhas,
59,237 s**, saída 0; Ruff aprovado. O teste real de smoke com adaptadores reais
(real_adapter_smoke) entregou 396 em 35,76 s. Uma tentativa posterior em paralelo
à suíte ficou abaixo do piso de carga fria Normal (1,70 GiB RAM livre) e não
enviou geração: canonical_sum_smoke. Os resultados estão preservados, sem
substituir a medição 6/6. O driver agora retorna erro de processo se qualquer
rodada falhar, além do JSON detalhado; a pontuação anterior sempre veio do JSON.

Após a suíte encerrar e a RAM voltar a 2,65 GiB, canonical_sum_retry passou com
adaptadores reais e metadados canônicos: nove ações, oito leituras, soma396 em
37,20 s, sem replanejamento. A recusa anterior permanece preservada.

Referências: [contexto e offload Ollama](https://docs.ollama.com/context-length),
[configuração e residência](https://docs.ollama.com/faq). A documentação confirma
que contexto maior aumenta a memória necessária; os números acima são locais.
