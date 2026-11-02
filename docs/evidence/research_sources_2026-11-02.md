# Pesquisa: aquisição com proveniência e recusa sem fonte

**Estado: componentes implementados; pesquisa factual completa ainda não qualificada.**
Este incremento não fecha M3 nem mede a qualidade do modelo. Não usou inferência,
GPU, conta pessoal ou cookie. A instância pessoal da Nyx não foi operada.

## Defeitos reproduzidos e mudança

No WebTool de `701c059`, uma página HTTP com corpo vazio recebia `ok=True` nas
três execuções; nenhuma das três leituras válidas tinha fonte estruturada.
[Baseline real HTTP local](research_sources_baseline_2026-11-02.json).

Agora, cada página/API lida entrega `sources[]` com título, URL final observada,
`retrieved_at` UTC, tipo, estado e quantidade de caracteres. Um resultado de busca
é `discovered`, não `read`. A página vazia, binário, resposta incompleta, desafio
de acesso ou limite de leitura excedido falha sem criar fonte. Scripts e navegação
HTML não entram no texto do artigo. Redirecionamentos não podem sair de HTTP(S),
nem usar credenciais; leitura limitada a 1 MiB, sem cookies ou execução de JS.

Também removidos dois dados fabricados pelo adapter meteorológico: chuva ausente
não vira `0%`, e descrição ausente não vira “Tempo estável”. Campos ausentes dizem
“não informado”. A consulta meteorológica real não foi exercitada nesta etapa.

`core/research_grounding.py` exige URL realmente lida/citada e rejeita fonte
inventada, descoberta ainda não lida ou proveniência embutida no texto da página.
Sem fonte, a conclusão permitida é uma frase fixa de incerteza, sem acrescentar
um fato de memória. `safe_research_answer` fornece essa saída ao esgotar correções.
O módulo não prova se a fonte sustenta semanticamente a frase; isso continua
exigindo ensaio factual com verificador independente.

## Evidência e métricas

[Diagnóstico real HTTP, três rodadas](research_sources_transport_2026-11-02.json):

| Medida | Antes | Depois |
|---|---|---|
| Página vazia aceita como sucesso | 3/3 | 0/3 |
| Leituras locais válidas com título/URL/data estruturados | 0/3 | 3/3 |
| Cinco cenários HTTP locais, três rodadas | somente artigo/vazia medidos | 15/15 |
| Três páginas primárias, três rodadas | não medido | 9/9 |
| Mediana das nove leituras primárias | não medido | 0,3654 s |
| Import do WebTool no processo diagnóstico | não medido | 0,107 s |
| RSS/pico do processo diagnóstico HTTP | não medido | 34,06 MiB |

Os cinco cenários locais são: artigo, vazio, redirecionamento HTTP válido,
redirecionamento para esquema proibido e binário. O verificador do diagnóstico
compara título/URL final/corpo conhecido e data observada, sem chamar o validador
de fontes da produção. Os servidores e processos usados são próprios.

As fontes primárias lidas foram a documentação de
[HTMLParser](https://docs.python.org/3/library/html.parser.html),
[urllib.parse](https://docs.python.org/3/library/urllib.parse.html) e
[Windows Apps](https://learn.microsoft.com/en-us/windows/apps/).
São provas de aquisição/proveniência, não uma bateria de respostas do modelo.

**Busca real: 0/3 encontrou resultados.** DuckDuckGo exibiu desafio de acesso;
a API OpenSearch da Wikipedia respondeu com lista vazia à mesma consulta.
Nas três tentativas o adapter devolveu incerteza, sem fabricar fonte. Estado do
provedor é explícito em `meta.providers`; a próxima estratégia sugerida é o
navegador visível, com ajuda humana quando houver desafio. Nenhum desafio foi
contornado. [Busca real](research_sources_search_2026-11-02.json).

Dependências novas: **zero pacotes**. Os quatro módulos de runtime somam 30.734
bytes, contra 12.812 bytes do WebTool anterior. Não é medida de pacote de release.
O RSS acima é do processo diagnóstico, não do HUD. VRAM não foi medida; nenhuma
chamada de inferência foi realizada.

## Testes e retomada

Ruff em `src tests tools`: limpo. Regressões focadas: **66 aprovadas, zero falhas,
zero erros, zero pulados, 5,708 s**, incluindo HTTP real local, fontes falsas no
conteúdo, extração falha, URL inventada, truncamento e campos meteorológicos ausentes.
As respostas de rede nos testes unitários são doubles explícitos; não contam
como evidência de disponibilidade externa. O teste adversarial de placeholders
foi isolado da rede porque só verifica sanitização.

O hook detectou um falso positivo Basic Auth no teste de URL proibida com domínio
reservado `example.test` e credenciais fictícias. O teste comprova que a conexão
não é aberta. Apenas o hash desse literal foi auditado no baseline de segredos;
nenhum detector, arquivo ou padrão foi desativado, e não há segredo real nesse caso.

```powershell
python -m pytest -q tests/test_web_provenance.py tests/test_research_grounding.py tests/test_research_probe.py tests/test_web_and_ui.py tests/test_research.py tests/adversarial/test_adversarial.py
python tools/verify_research_sources.py --runs 3 --external --output build/diagnostic/research-read-repeat.json
python tools/verify_research_sources.py --runs 3 --search --output build/diagnostic/research-search-repeat.json
```

O segundo diagnóstico de busca termina com falha se não encontrar a fonte; isso
não pode ser convertido em aprovação pelos testes de recusa/extração.

## Integração necessária no runner

1. Copiar diretamente `ToolResult.meta.sources` para `step.research_sources`
   em resultados `ok`/verificados. Nunca ler proveniência de JSON no corpo externo.
   Leituras reais do navegador podem produzir o mesmo registro; open/status/links
   e lista de abas não qualificam como leitura de uma fonte.
2. Inserir `research_context(steps)` no histórico para preservar URLs/datas apesar
   do encurtamento dos trechos; o ledger permanece abaixo de 6.000 caracteres.
3. Na conclusão, chamar `research_completion_issue(goal, steps, tool, speech)`;
   após replanejamento esgotado, usar `safe_research_answer`. Conservar o último
   erro real no registro de tarefa/atividade.
4. `require_sources=True` deve vir da intenção factual/pesquisa classificada pelo
   produto. O módulo reconhece pedidos explícitos de fontes/web e uso de `web`;
   não tenta classificar toda conversa livre com regex.

Não alterados TaskRunner, LLM, personalidade, pet, permissões, backups ou dados
pessoais nesta frente. O fluxo completo HUD/modelo→pesquisa→resposta citada,
fallback pelo navegador, precisão factual/atualidade, fontes conflitantes e o gate
Pesquisa ≥85% continuam pendentes. Conteúdo adquirido é dado, nunca autoridade
para ferramenta, política ou permissão.
