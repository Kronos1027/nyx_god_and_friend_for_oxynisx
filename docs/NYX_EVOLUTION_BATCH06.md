# Nyx Evolution — Lote 06: entregas verificáveis, diagnóstico e auditoria privada

**Status:** desenvolvimento experimental, sem Codex, sem merge em `main`
e sem substituição da instalação Windows atual. Baseado nos Lotes 01–05.

## Problema observado

Antes deste lote, `TaskRunner` reconhecia uma pós-condição para
**um** arquivo com hash. Um projeto de código, no entanto, costuma
entregar várias coisas (por exemplo `app.py`, `test_app.py` e
`config.json`). A execução de somente um arquivo não deveria validar
a tarefa toda. Além disso, a interface listava qualquer
`PLANNING_FINISHED` como "resposta concluída", sem distinguir
entrega comprovada de declaração não verificada.

Também foi observado que o `AuditLogger` escrevia em JSONL campos
como `user_input`, `llm_raw`, `result_output`, parâmetros de
ferramenta e `steps`. Esses registros eram úteis, mas ampliavam a
quantidade de dados privados persistidos localmente.

## Módulos implementados

### 06-A — `src/core/goal_bundle.py`

Contrato confiável `file_bundle` de **2 a 8** pós-condições
`file_sha256`. Apenas código de aplicação autorizado define um
contrato; o LLM não cria nem amplia a lista.

- Cada item exige caminho absoluto dentro das raízes autorizadas,
  hash SHA-256 e **registro de gravação verificada na tarefa atual**.
- O conteúdo real do arquivo é verificado pela implementação existente
  `GoalContract`, em streaming de no máximo 8 MiB por item.
- Caminhos duplicados, contratos aninhados, itens de exclusão, excesso
  de arquivos e caminhos externos são recusados.
- Veredito completo `all_files_verified`; parciais somente como
  `verified_N_of_M`, sem nomes de arquivos/segredos.
- Reinícios preservam o manifesto e revalidam contra as raízes confiáveis;
  a existência prévia de um arquivo não cria evidência de escrita.

Exemplo de integração **por código confiável**, não gerado pelo modelo:

```python
import hashlib
from pathlib import Path

root = Path(r"E:\Projetos\meu_app")
runner = TaskRunner(loop, journal=journal, acceptance_roots=[root])
expected = {
    "kind": "file_bundle",
    "items": [
        {"kind": "file_sha256", "path": str(root / "main.py"),
         "sha256": hashlib.sha256(b"print('ok')\n").hexdigest()},
        {"kind": "file_sha256", "path": str(root / "test_main.py"),
         "sha256": hashlib.sha256(b"def test_ok():\n    assert True\n").hexdigest()},
    ],
}
result = runner.start("Produza estes dois artefatos de teste.", acceptance=expected)
```

O conjunto não executa gravações: todas as ferramentas mantêm suas
próprias autorizações. Hashes exigem **conteúdo esperado conhecido**.
Não fornecem um julgamento automático da qualidade de código inventado
pelo modelo, tampouco verificam testes reais de aplicativos sem execução.

### 06-B — `src/core/task_health.py`

Relatório estruturado que separa:
- `GOAL_VERIFIED` (meta e estado de planejamento realmente verificados);
- `GOAL_UNVERIFIED` (modelo terminou sem provar toda a entrega);
- `NO_GOAL_CONTRACT` (relatório final sem métrica semântica de meta);
- `NEEDS_MANUAL_REVIEW` (efeito externo incerto);
- `RESOURCE_PAUSED`, `IN_PROGRESS`, `WAITING_CONFIRMATION` e
  `INTERRUPTED`.

Calcula quantidade de ações verificadas/falhas/incertas, sequência
de falhas da mesma ferramenta e se é seguro **oferecer** retomada
explícita. Não fornece ferramenta, permissão ou execução automática.
A interface `ui/desktop.py` apresenta esses diagnósticos no histórico.

### 06-C — `src/core/task_diagnostics.py`

Leitura **SQLite somente leitura**, sem adquirir o lease exclusivo do
executor. Permite diagnosticar tarefas durante o uso da Nyx.

- Limite de 1–100 registros;
- Sem texto original dos pedidos, caminhos, argumentos, saídas ou
  respostas do modelo;
- Linhas inválidas são contadas e ignoradas;
- Não modifica o banco e não solicita GPU/modelo.

No diretório do projeto, o comando é:

```powershell
py -3.11 tools/nyx_task_report.py --db data/nyx_tasks.db --limit 20
```

### 06-D — `src/audit/privacy.py`

Camada de minimização para `AuditLogger.log_event`. Campos livres como
`user_input`, `llm_raw`, resultados, parâmetros, histórico, conteúdo
de ferramentas e erros passam a ser **omitidos ou descritos por tamanho e
tipo**. Eventos continuam armazenando estado, tipo de ferramenta,
`parse_ok`, confirmações, contagens e métricas numéricas de uso.

A auditoria de decisões continua append-only JSONL; não equivale a um
cofre criptografado. Uma entrada já gravada em versões anteriores
**não é retroativamente apagada**, e logs/erros de bibliotecas externas
podem exigir revisões próprias. O `TaskJournal` mantém outra política
de mascaramento e não é alterado por esse módulo.

## Testes e portões

- Testes unitários de limites, duplicação, symlinks/roots e manipulação de
  conteúdo dos dois ou mais arquivos;
- Testes fim a fim com ferramentas reais no sandbox, confirmações
  individuais, conclusão parcial e retomada após pausa;
- Status de tarefa com evidência vs afirmação do modelo e bloqueio de
  retomada após efeito incerto;
- Leitura paralela do SQLite ativo, sem lock exclusivo e sem vazamento
  de conteúdo para terminal;
- Logs JSONL sem prompts, parâmetros nem respostas pessoais; testes de
  regressão da aplicação, Linux e Windows;
- Nenhum merge ou publicação antes de todos os testes e da verificação
  no Windows real com Qwen/RTX 3060.

## Próximas oportunidades, ainda não implementadas

1. Testes de ponta a ponta com **Qwen real** em tarefas que alteram
   código, usando pastas descartáveis e aprovações humanas;
2. Verificador adicional para suíte de testes: **executar comandos
   permitidos em sandbox**, verificar exit code e relatório de testes,
   sem aceitar "todos passaram" apenas porque o modelo afirmou;
3. Planos por dependência com pós-condições verificadas entre subtarefas;
4. Telemetria contínua de VRAM com baixo overhead, sem processos sempre
   residentes, para avaliar gargalos reais;
5. Ações de voz/Windows e um kit de tarefas cotidianas com aprovação,
   cancelamento, verificação e rollback;
6. Auditoria privada de logs históricos já gerados, com opção explícita
   de retenção e expurgo a cargo do proprietário.

A meta de 1.800 módulos permanece uma aspiração, não uma contagem de
funcionalidades já implementadas ou prontas para uso.
