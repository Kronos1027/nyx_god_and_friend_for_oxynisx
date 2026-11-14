# Nyx Evolution — Lote 03: pesquisa reproduzível com modelo local

## Pergunta científica

Um **mesmo** Qwen instalado consegue concluir mais tarefas com o novo
harness de pós-condições do que com o executor anterior, preservando
segurança, latência aceitável e RAM suficiente para o Windows?

Não atribuir aumento de inteligência ou autonomia à simples aprovação dos
testes com `OfflineLLM`. O resultado só terá validade depois de executar
o mesmo modelo, as mesmas tarefas e a mesma política de memória nas duas
variantes, em um computador real.

## Fontes técnicas conferidas em 2026-11-14

- Ollama API, documentação oficial:
  https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx
  — duração em **nanossegundos** (`total_duration`, `load_duration`,
  `prompt_eval_duration`, `eval_duration`), contadores de tokens e cache.
- Ollama OpenAPI:
  https://github.com/ollama/ollama/blob/main/docs/openapi.yaml
  — opções `seed`, `num_ctx`, `num_predict`, `keep_alive` e JSON schema.
- A Nyx já tinha `runtime_budget.py`, `prompt_budget.py`,
  `task_journal.py` e `goal_contract.py`; esta etapa **reutiliza**
  os controles existentes em vez de adicionar um segundo modelo residente.

## Áreas e hipóteses priorizadas

| Frente | Hipótese testável | Evidência mínima |
|---|---|---|
| R01: Conclusão | Verificador de objetivo evita falsos sucessos | SHA-256 e ação verificada; mesma tarefa nas duas variantes |
| R02: Agentes longos | Persistência e observações evitam loops | Métricas de passos, interrupção e retomada sem repetir efeitos |
| R03: Eficiência | Limites de contexto reduzem trabalho desperdiçado | Tokens de entrada/cache, tokens/s e tempo por tarefa |
| R04: RAM/VRAM | Um modelo residente + fila respeita 16 GiB RAM | Mínimo de RAM livre e VRAM antes/depois por tarefa |
| R05: Memória | Recuperação seletiva reduz esquecimento aparente | Perguntas retidas, fontes corretas e falsos fatos |
| R06: Segurança | Dados externos não alteram a política do agente | Tentativas de prompt injection, aprovações recusadas |
| R07: Habilidades | Skills propostas não causam regressões | Testes, sandbox, permissões e rollback em cada promoção |
| R08: KRA-13 | Endereçamento neural agrega algo ao cache simples? | Comparar KRA-13 original, SQLite e dicionário no mesmo benchmark |
| R09: Sono | Consolidação preserva fatos antigos | Teste A/B com checkpoint e conjunto de retenção |
| R10: UI/voz | Processos em segundo plano não travam a conversa | Latência p95, cancelamento e medição no Windows real |

Nesta branch, **R01, R03 e R04 têm instrumentos de medição**.
R02 e R06 têm testes simulados existentes. R05 e R07–R10 são
linhas de trabalho, não capacidades novas concluídas.

## Como testar sem substituir a Nyx do Windows

No repositório Git, usar uma cópia isolada (PowerShell):

```powershell
git fetch origin
git worktree add ..\nyx-pesquisa origin/experiments/nyx-real-llm-evaluation-batch03
cd ..\nyx-pesquisa
py -3.11 tools/benchmark_local_nyx.py
```

Esse primeiro comando de Python só mostra o plano, **sem contato com o Ollama**.

Para executar experimentos **somente quando o PC estiver ocioso**:

```powershell
py -3.11 tools/benchmark_local_nyx.py --run --model qwen2.5:3b-instruct --suite smoke --repeats 2
```

O modelo indicado é apenas exemplo: utilizar o **nome EXATO** de um
modelo já instalado em `ollama list`. Não há `ollama pull`, shell,
pesquisa externa, interface, nem acesso aos arquivos reais do usuário.
Em vez disso, usa um diretório temporário e duas ferramentas limitadas:
`read_file` e `write_file`. A aprovação é simulada **apenas** quando
o caminho e o conteúdo correspondem exatamente à tarefa de teste.

- `--suite smoke`: duas tarefas, duas variantes; com `--repeats 2`
  produz oito execuções controladas.
- `--suite extended`: seis tarefas com Unicode, CSV, 40 linhas e
  instrução maliciosa tratada como dado; com duas repetições são 24 execuções.
- `--repeats`: 1 a 3. `--timeout`: 20 a 120 segundos por tarefa.
- `--seed 42`: semente reprodutível, não garantia de determinismo absoluto.

O resultado é JSON no terminal, com métricas e resultados independentes
dos textos que o modelo afirmou. Não registra prompts, conteúdo dos
arquivos, respostas integrais nem credenciais no relatório. Os logs
temporários são destruídos ao encerrar o experimento.

## Indicadores

1. Proporção de metas verificadas independentemente (`verified`).
2. Diferença **pareada** em pontos percentuais por tarefa/repetição.
3. Mediana do tempo total por tarefa e tokens/s observados.
4. Tokens de prompt, tokens gerados, tokens cacheados e tempo de carregamento,
   quando a versão do Ollama disponibilizar esses campos.
5. RAM mínima **do sistema**, amostrada a cada 0,5 s; RSS máximo **do processo
   Python**, que **não** inclui o processo Ollama.
6. VRAM disponível antes/depois. **Não há pico de VRAM medido**.
7. Total de aprovações autorizadas e recusas; 0 gravações fora do sandbox.

Qualquer aumento de capacidade deve vir acompanhado de intervalo de
incerteza para uma amostra grande e conjunto de tarefas retidas. Com
duas ou seis tarefas, diferenças são apenas observações exploratórias.

## Próximos portões de qualidade

- Obter resultado real de um modelo Qwen na máquina alvo com 16 GiB RAM;
  não declarar ganho antes disso.
- Ampliar gradualmente para mais de 100 tarefas independentes, com
  repetição, ordem alternada e seeds fixos, mantendo toda a execução no sandbox.
- Confrontar falhas por tipo: erro de planejamento, JSON inválido, repetição,
  confirmação recusada, pressão de recursos e pós-condição divergente.
- Se o benchmark apontar lentidão: revisar poda de contexto, cache e
  carregamento do modelo; **não** aumentar `num_ctx` cegamente.
- Se apontar erro de conclusão: melhorar estratégia de verificação da meta
  antes de adicionar mais agentes ou modelos.
- Medir Windows GUI/voz e GPU real antes de integrar esse trabalho na `main`.

A branch é experimental, sem instalação automática, merge ou treinamento
neural. Não corresponde a 1.800 novos módulos entregues.


## Diagnóstico por tarefa integrado à Nyx

Cada `TaskRunner` acumula somente nove contadores numéricos no
`TaskJournal`: tentativas de geração, JSON válido/inválido, unidades de
entrada/cache/saída e tempos totais/carregamento/geração. A retenção é limitada,
não guarda texto do usuário e persiste após pausa/reinício. O evento
`task_finished` expõe um resumo da produtividade para localizar ciclos caros.

Os campos `prompt_count`, `cached_prompt_count` e `output_count` evitam
interferir no filtro de credenciais do diário, que propositalmente trata
campos contendo `token` como sensíveis. Essa incompatibilidade foi
encontrada pela suíte de persistência e corrigida sem relaxar o filtro.

## Proteção contra publicação de memórias pessoais

O repositório GitHub `Kronos1027/nyx_god_and_friend_for_oxynisx` foi
confirmado como **público** nesta pesquisa. A branch `nyx-backups`
compartilha a visibilidade pública, apesar da criptografia Fernet dos
snapshots. Não há alegação de que a chave privada tenha sido publicada.

Neste lote experimental, `CloudBackup.upload` exige a confirmação
autenticada de `gh api --hostname github.com repos/... --jq .private`,
antes de criar/adicionar/enviar arquivos. Qualquer resultado diferente de
`true`, falta do CLI, erro de autenticação ou timeout bloqueia o upload.
Backups criptografados locais continuam disponíveis. Esta proteção **não**
altera automaticamente a instalação Windows nem a branch `main`:
a migração de backups existentes para um repositório separado e privado
continua uma decisão do proprietário.

A checagem autenticada é deliberadamente conservadora; por segurança,
não basta um Git remote configurado nem uma branch denominada "privada".
