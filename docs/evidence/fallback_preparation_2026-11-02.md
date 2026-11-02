# Qualificação de fallbacks · preparação · 02/11/2026

Inventário read-only confirmou os três candidatos já instalados:

| Modelo | Quantização | Bytes de pesos no inventário |
|---|---|---:|
| qwen2.5:3b-instruct | Q4_K_M | 1929912432 |
| llama3.2:1b | Q8_0 | 1321098329 |
| qwen2.5:0.5b | Q4_K_M | 397821319 |

**Nenhuma inferência foi executada nesta preparação. Nenhum vencedor foi escolhido.**
O navegador usa a GPU na frente principal; a qualificação aguarda liberação
desse lote. Não houve download, instalação ou troca de preferência pessoal.

`src/core/model_prompts.py` fornece candidatos específicos para cada família e
tamanho, distintos do prompt geral usado no4B. São curtos, em português, com
incerteza explícita, identidade de software e limites de observação/execução.
Eles não contêm respostas do gabarito. Sua existência não os torna qualificados.
O código de produção ainda precisa adotá-los após a medição; não foi alterado
`llm_client.py` nesta frente.

O scanner de segredos foi mantido ativo. Quatro candidatos foram auditados
pontualmente no baseline: três digests públicos dos pesos, conferidos com
`/api/tags`, e a palavra sintética `secret` no URL loopback de uma regressão que
exige rejeitar credenciais no endpoint. Nenhuma credencial real está presente
ou foi verificada na rede. Não se excluiu arquivo, detector ou padrão inteiro.

`tools/qualify_fallback_models.py` usa a rota real `OllamaClient.converse`, em
streaming, sem HUD, ferramentas, memória ou sensores pessoais. Só inventaria por
padrão; para inferir, exige `--run` e endpoint loopback diferente da porta pessoal
11434. Não inicia, encerra ou descarrega servidores/modelos. O chamador deve
fornecer uma instância própria sem trabalho concorrente e cuidar do ciclo dela.

O corpus independente possui16casos:10fatos,4pedidos sem informação observável
e2conversas/identidade. Com três candidatos e três rodadas, são144gerações.
Cada questão é enviada sem gabarito ou fontes do avaliador. `--prompt-variants
shared tailored` permite comparar também o prompt compartilhado, duplicando
as gerações; esse modo não foi executado. Relatórios guardam respostas sintéticas,
erros, primeiro delta, tempo total, memória disponível do host, RSS da árvore de
runtime fornecida por PID e pico de VRAM do sistema. A VRAM de outros programas
participa dessa última métrica. O contexto real consta do relatório da geração.

Os gabaritos foram conferidos em fontes primárias nesta data:

- [NASA — planetas](https://science.nasa.gov/solar-system/planets/): oito planetas.
- [NASA — Júpiter](https://science.nasa.gov/jupiter/jupiter-facts/): maior planeta.
- [NASA — Vênus](https://science.nasa.gov/venus/venus-facts/): planeta mais quente.
- [NASA — Mercúrio](https://science.nasa.gov/mercury/facts/): mais próximo do Sol.
- [NASA — Sol](https://science.nasa.gov/sun/facts/): uma estrela.
- [NASA — Lua](https://science.nasa.gov/moon/facts/): satélite natural da Terra.
- [NASA — Terra](https://science.nasa.gov/earth/facts/): nitrogênio predomina na atmosfera.
- [PubChem — água](https://pubchem.ncbi.nlm.nih.gov/compound/WATER): fórmula H2O.
- [BIPM — SI](https://www.bipm.org/en/measurement-units/): luz no vácuo, exatamente299792458m/s.
- [Governo Federal — Brasília](https://www.gov.br/g20/pt-br/sobre-o-g20/cidades-sede/brasilia-df): capital brasileira.

Regressões:17testes aprovados em `tests/test_fallback_qualification.py`; Ruff
limpo nos novos módulos. Cobrem respostas erradas que citam o gabarito negado,
unidades erradas, uma abstenção seguida de número inventado, fluxo incompleto,
identidade/ação falsa, bloqueio do endpoint pessoal/remoto e ausência de seleção
com rodadas incompletas. São testes do método, sem medir qualidade dos modelos.

Limites: corpus pequeno e concentrado em ciência básica, sem poder certificar
conversa factual geral. O verificador confere respostas estreitas e retém texto
para revisão humana; uma palavra correta não prova todas as frases adicionais.
Abstenção é uma heurística de português, e o caso de conversa livre mede entrega,
não afeto, criatividade ou utilidade. Ranking só será calculado com candidatos
completos e não altera automaticamente a produção. A escolha de fallback
precisará de aviso persistente na tela e relatório real, inclusive erros.

Retomada, com servidor próprio disponibilizado pela frente principal:

```powershell
python tools/qualify_fallback_models.py --run --host http://127.0.0.1:11435 --server-pid <PID_PROPRIO> --runs 3 --output docs/evidence/fallback_qualification_2026-11-02.json
```

Inventário completo e corpus: [JSON read-only](fallback_inventory_2026-11-02.json).
Não substitui a bateria M3 nem fecha o marco de runtime.
