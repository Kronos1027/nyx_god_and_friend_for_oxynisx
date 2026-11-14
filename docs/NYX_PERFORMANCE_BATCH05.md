# Nyx Evolution — Lote 05: menos CPU ociosa, menos chamadas Ollama, mais visibilidade

**Status:** branch experimental, sem merge, sem alteração automática no Windows
ou nos pesos do modelo. Depende dos lotes 01–04 ainda experimentais.

## Pesquisa e decisão de arquitetura

A documentação oficial do Ollama separa:
- \`GET /api/tags\`: inventário local (nome, tamanho e digest do modelo);
- \`GET /api/ps\`: processos/modelos **residentes em memória**
  (size_vram, context_length, digest, etc.).

Referência oficial: https://github.com/ollama/ollama/blob/main/docs/api.md

A Nyx anterior consultava ambos em todo \`ollama_request_context\`,
mesmo quando o computador não tinha VRAM conhecida ou o modelo sequer
estava presente. Não devemos guardar uma versão antiga de RAM, VRAM ou
residência para acelerar uma decisão crítica. Portanto o lote mantém
\`/tags\` fresco e só consulta \`/ps\` quando a residência GPU é
**matematicamente possível** segundo a política existente, sem alterar
limites de tamanho/VRAM.

A documentação Python recomenda cache **limitado por LRU** quando
consultas recentes se repetem, porque caches ilimitados crescem sem
controle. O seletor de memória da Nyx é função pura de fatos+consulta,
mas os fatos podem mudar: invalidamos todos os contextos derivados
após qualquer gravação SQLite bem-sucedida.

Referência: https://docs.python.org/3.11/library/functools.html#functools.lru_cache

## Módulos implementados

### A. \`core/context_prompt_cache.py\`

- No máximo **8 resultados** de memória, de no máximo **1700
  caracteres** cada, e consultas de até 256 caracteres.
- LRU em memória apenas; sem thread, banco auxiliar, rede ou disco.
- \`CoreMemory.format_prompt_block\` reutiliza consultas idênticas;
  consultas distintas continuam usando o seletor Python/Rust.
- \`CoreMemory.set\` agora grava no SQLite antes de publicar no dicionário
  e invalida o cache de prompts na mesma seção protegida por RLock.
- Falha na gravação não publica valor que apenas existiria em memória.
- SQLite continua fonte autoritativa. O hot cache KRA-13 é preservado.

**Limite:** consultas novas, sem repetição, não ganham esse tempo.
Atenção à concorrência: bloquear o dicionário durante geração do bloco
pode atrasar uma escrita enquanto a seleção termina (milissegundos).

### B. \`core/ollama_admission.py\`

- Decide de forma pura se a requisição de \`/api/ps\` pode ser útil.
- Não consulta \`/api/ps\` se RAM ≤1 GiB, VRAM desconhecida, VRAM
  abaixo de 4 GiB, modelo não encontrado ou sem digest confiável.
- Para GPU elegível, continua consultando \`/ps\` **sempre** e só
  reutiliza contexto se for o mesmo modelo/digest totalmente residente.
- O orçamento de modelo, disponibilidade de RAM e limites de contexto
  **continuam obrigatórios**; nenhum snapshot de recursos é cacheado.

### C. \`core/inference_queue_metrics.py\`

- Registro de **64 tempos de espera recentes**, sem dados das tarefas.
- Exposição de mediana/p95 (ms), admissão, fila cheia, cancelamento,
  expirado por timeout; integração com \`InferenceGate.telemetry()\`.
- Sem processo novo, sem thread de monitoramento ou gravação de
  mensagens. Ajuda localizar lentidão antes da chamada ao modelo.

## Testes e resultados (CI em 14/11/2026)

- [Execução Linux/Windows](https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx/actions/runs/43645651469):
  **883 testes Linux aprovados**, 96 pulados, 10 reservados para APIs
  Windows. **195 testes selecionados aprovados** no runner Windows.
- Testes de cache: limites, LRU, acerto, invalidação, concorrência,
  falha SQLite e equivalência com a implementação anterior.
- Testes Ollama: CPU-only, VRAM baixa, modelo ausente, GPU totalmente
  residente e cold load. Sem rede/modelo real.
- Testes de fila: p50/p95, lotação, timeout, cancelamento e ausência
  de polling periódico.
- [Benchmark Linux/Windows](https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx/actions/runs/43645651469)
  com 10.000 fatos sintéticos e nove repetições:

| Runner CI | Seleção Python sem cache | Cache quente | Comparação |
|---|---:|---:|---:|
| Linux | 17,374 ms | 0,0103 ms | ~1682× |
| Windows | 21,3666 ms | 0,0164 ms | ~1303× |

**Advertência obrigatória:** isso mede a reutilização de **um mesmo
bloco de contexto já calculado**. Não há ganho de 1000× na geração de
tokens, na inferência do Qwen ou em consultas diferentes. Não foram
medidos memória RSS/VRAM no PC do usuário nem qualidade de respostas.

## Portões antes de promoção

1. Executar com Qwen/Ollama real no Ryzen 7 5700X/RTX 3060, medindo
   p50/p95 de fila, tokens/s, VRAM, latência fim a fim e sucesso da meta.
2. Medir fração real de cache hits em 100 tarefas representativas;
   consultas diferentes podem não oferecer retorno significativo.
3. Se PyO3/Rust estiver ativado, testar paridade Unicode e regressão
   em todos os contextos, inclusive memórias editadas durante a tarefa.
4. Verificar que mudanças em modelos carregados continuam impedindo
   admissão insegura, sem reutilizar digest/tamanho obsoleto.
5. Comparar custo de lock + cache, incluindo carga concorrente e
   efeitos sobre janelas PyQt.
6. Só mesclar em \`main\` após revisão e aceitação no Windows real.

O roadmap dos 1.800 módulos segue aspiracional. Estes três módulos
são componentes específicos com testes e integração, não agentes
inteligentes autossuficientes nem modelos neurais adicionais.
