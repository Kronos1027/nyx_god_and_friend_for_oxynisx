# Nyx Evolution — Lote 02: o que aproveitamos da DeepSeek

## Verificação da publicação

**DeepSeek Harness:** runtime de agentes com composição por plugins, sessão
persistente, chamadas de ferramentas, política de permissões/sandbox,
compactação de contexto e adaptação de modelos. Código publicado pelo projeto
deepseek-ai/deepseek-harness, licença própria a verificar antes de reaproveitar
qualquer código. Nesta implementação **nenhum código do Harness foi copiado**.
Referência: https://github.com/deepseek-ai/deepseek-harness

**DSec:** infraestrutura distribuída da DeepSeek para FnCall, contêineres,
microVMs e VMs. O relatório "DeepSeek Elastic Compute" menciona mais de
380 mil sandboxes simultâneos, em uma unidade de grande escala com cerca de
160 máquinas. Isso **não** demonstra que o Harness executa 380 mil agentes no
computador de um usuário, nem é um parâmetro razoável para a Nyx.
Fonte: https://arxiv.org/abs/2609.22978

**Benchmark de harness:** "Same Model, Different Harness", 8090 Labs
(2026-10-09), 113 tarefas de programação repetidas duas vezes por combinação,
observou diferenças de até 35 pontos dependendo do modelo/harness. Diferenças
até nove pontos foram tratadas como possivelmente indistinguíveis de ruído.
Nenhum ganho numérico deve ser atribuído à Nyx sem avaliação do **mesmo
modelo** e das **mesmas tarefas** antes/depois.
Fonte: https://www.8090.ai/blog/same-model-different-harness

**Segurança:** README/SAFETY da DeepSeek destaca que seu Harness é experimental
e não auditado; seu sandbox não é proteção absoluta. Nyx preserva aprovações,
raízes autorizadas e interrompe efeitos externos de resultado incerto.
Fonte: https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md

## Decisão para PC de 16 GB de RAM e RTX 3060 12 GB

Não executar centenas de sandboxes, nem carregar vários modelos grandes ao
mesmo tempo. Priorizar **um modelo residente**, filas já existentes,
compactação vinculada ao contexto escolhido pelo runtime Ollama, estado
persistente SQLite, ferramentas com permissões mínimas e pós-condições
independentes antes de declarar conclusão.

### Interfaces novas

- `core.goal_contract.GoalContract.parse(spec, roots)`: somente uma camada
  **confiável do aplicativo**, nunca a resposta do modelo, define um contrato.
- `file_sha256`: exige registro de `write_file` executado e verificado na
  tarefa atual, mais bytes em disco idênticos ao hash esperado.
- `file_absent`: verificador isolado que exige um registro confiável de
  exclusão verificada e ausência do arquivo. **Ainda não acionável pelo
  modelo**: `delete_file` não consta dos tipos de ação autorizados na Nyx.
  O contrato NÃO acrescenta essa permissão. Serve apenas para futuras
  integrações confiáveis que já possuam autorização explícita.
- `TaskRunner(..., acceptance_roots=[trusted_workspace])` /
  `runner.start(goal, acceptance=contract)`: contrato opcional; tarefas sem
  contrato mantêm o comportamento anterior.
- Contrato, tentativas e último veredicto sobrevivem no `TaskJournal`;
  ao retomar, o caminho volta a ser validado contra as raízes permitidas.
- No modo de execução prolongada da interface, quando o modelo diz `none`
  antes de atingir a pós-condição e a ferramenta apropriada existe, ocorre
  no máximo **uma** nova tentativa de planejamento. Nenhuma ação externa é
  repetida automaticamente; cancelamento, permissões e limites existentes
  continuam valendo.
- Se o modelo terminar sem evidência, um alerta explícito é anexado e o
  registro guarda `goal_verdict.status=UNVERIFIED`.
- A verificação de arquivo usa streaming de no máximo 8 MiB, sem carregar
  o arquivo inteiro em RAM, e não faz chamadas a modelos ou rede.

Exemplo de integração por código confiável:

```python
import hashlib
from pathlib import Path

workspace = Path("E:/projetos/nyx_workspace").resolve()
target = workspace / "answer.txt"
expected = hashlib.sha256(b"resposta exata\n").hexdigest()
runner = TaskRunner(loop, acceptance_roots=[workspace], journal=journal)
result = runner.start(
    "Grave a resposta no arquivo autorizado.",
    acceptance={"kind": "file_sha256", "path": str(target), "sha256": expected},
)
```

O contrato não é um comando: `start` ainda solicita aprovação sempre que
uma ferramenta o exigir. O algoritmo não conhece a intenção de qualquer
pedido em linguagem natural, nem prova que um relatório verbal é verdadeiro.

## Portões de qualidade

- `pytest tests/test_goal_contract.py tests/test_task_goal_contract.py`;
- suíte geral Linux com Ruff e smoke ampliado Windows; avaliar 100+ tarefas
  reais somente com autorização do usuário e equipamento local;
- incluir cenários de symlink, dados antigos, exclusão proibida, arquivo incorreto,
  recusa de aprovação, pausa/reinício, caminhos proibidos e arquivos grandes;
- instrumentar latência, pico de RAM e taxa de conclusão com o **mesmo Qwen**
  antes e depois; sem esse ensaio, ganho de capacidade é uma hipótese;
- manter o PR como **draft** e sem merge para o aplicativo Windows estável.

Limitações: não substitui isolamento do SO; não impede TOCTOU de outros
processos com acesso à mesma pasta; confirma apenas as pós-condições
suportadas e não prova autonomia geral.
