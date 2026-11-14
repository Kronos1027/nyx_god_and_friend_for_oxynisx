# Nyx Evolution — Lote 07: verificação estática antes de alterar código

**Estado:** experimental, baseada no Lote 06. Sem uso de Codex, sem merge
em `main` e sem alterar automaticamente a instalação local.

## Necessidade identificada

O fluxo `CodeTaskRunner` já gera propostas de reparo e, quando recebe
um executor de testes **confiável injetado pela aplicação**, pode aplicar
edições com backups e rollback. Porém, antes deste lote, não era feita
uma verificação estática das propostas: uma resposta do modelo com
Python sintaticamente inválido ou JSON/TOML malformado poderia ser
proposta ou aplicada antes da próxima rodada.

O backend padrão **deliberadamente bloqueia testes arbitrários de
repositórios**, porque `pytest`, `conftest.py` e plugins executam
código. A pasta do projeto e o consentimento do usuário **não** são uma
sandbox de sistema operacional. Este lote não remove essa proteção.

## Implementado

### 07-A — `src/tools/code_patch_preflight.py`
- Análise `ast.parse` para arquivos `.py`, `json.loads` com
  detecção de chaves duplicadas para `.json`, `tomllib.loads` para
  `.toml`. Não importa nem executa arquivos do projeto.
- No máximo 200.000 bytes por fonte. Propostas de no máximo cinco
  arquivos e inspeção explícita de até doze arquivos locais.
- Rejeita alvos duplicados (também com diferenças de maiúsculas,
  visando compatibilidade Windows), links simbólicos, traversal,
  caminhos absolutos, arquivos grandes e codificações inválidas.
- `.yaml`, `.yml`, `.cfg`, `.md` e `.txt` são
  `UNSCANNED`, **não** marcados como sintaxe válida.
- Retorna somente status/códigos/linhas, não o código-fonte ou o
  traceback do parser.

### 07-B — integração `src/tools/code_task_tool.py`
- Toda proposta produzida pelo LLM é inspecionada antes de ser
  entregue ao usuário ou aplicada.
- Se qualquer arquivo suportado falhar na análise, a operação
  é interrompida, **antes de qualquer escrita**.
- O modo `operation="preflight"` recebe `files` relativos
  ao diretório autorizado, é apenas leitura e não invoca nem o LLM
  nem o executor de testes.
- Os metadados do resultado distinguem `preflight_checks` de
  `tests_executed`. Um patch que só passou no parser **não**
  equivale a testes aprovados.

### 07-C — `src/core/test_failure_triage.py`
- Classifica falhas em sintaxe, dependência, assertion, timeout,
  permissão ou categoria desconhecida.
- Apenas o código real de saída recebido do **executor injetado**
  pode marcar `EXIT_ZERO`. Texto externo como "999 passed" com
  retorno diferente de zero **não** significa sucesso.
- A classificação preserva somente a categoria, tamanho da
  saída e informações numéricas; nunca o texto bruto do erro.
- Ao pedir ao modelo uma correção, o prompt reforça que
  logs de testes são observações **não confiáveis** e não podem
  conceder novas permissões. Isso reduz risco, mas não prova
  imunidade completa a prompt injection.

### 07-D — CLI `tools/nyx_code_preflight.py`
O comando abaixo roda em Python 3.11, sem Docker, Ollama ou Codex:

```powershell
py -3.11 tools/nyx_code_preflight.py --repo "E:\Projetos\MeuApp" app.py tests/test_app.py pyproject.toml
```

O código de saída é `0` quando todos os arquivos selecionados
foram analisados, `1` quando há arquivos sem verificação suportada,
e `2` para entrada insegura, arquivo ilegível ou erro de sintaxe.
A resposta JSON não revela conteúdo dos arquivos.

## Portões e limitações

- `ast.parse` e parsers de configuração **não** provam que
  o programa compila todas as dependências, importa corretamente,
  passa nos testes, é seguro ou realiza o objetivo do usuário.
- Não há execução de `pytest` dentro do processo da Nyx.
  Testes reais de projetos externos continuam exigindo um executor
  separado, limitado e aprovado que ofereça isolamento de verdade.
- Atestação de saída 0 de um executor injetado só é tão confiável
  quanto o executor de origem; não é uma assinatura criptográfica.
- O monitoramento de RAM/VRAM e inferência real com Qwen no
  Ryzen 7 5700X/RTX 3060 continua dependente de validação
  no computador do usuário.
- O LLM ainda pode propor lógica incorreta que tem sintaxe válida.
  Esse é o próximo obstáculo, não resolvido pelo parser.
- `main` continua intacta, e a meta de 1.800 módulos
  não foi atingida.

## Próximo incremento planejado

1. Definir um contrato de executor de testes **isolado**, com
   bloqueio de rede, CPU/memória limitadas, área temporária, sem
   acesso a dados pessoais e sem privilégios elevados.
2. Construir avaliações pareadas com projetos descartáveis,
   comparar quantidade de correções válidas e custo de inferência.
3. Só permitir promoção depois de testes no Windows alvo,
   confirmação de política de autorização e revisão humana.
