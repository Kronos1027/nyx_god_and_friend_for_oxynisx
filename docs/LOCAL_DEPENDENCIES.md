# Dependências locais e espaço no Windows

Nesta máquina, o ambiente `.venv` e os modelos de voz da Nyx já ficam no projeto,
no disco E. O Ollama usa `E:\OllamaModelos`, fora do projeto.

A pasta `.local-deps/`, ignorada pelo Git, armazena componentes realocados do C:

| Pasta | Conteúdo | Caminho de compatibilidade |
| --- | --- | --- |
| `pip` | Cache de instalação do pip | `%LOCALAPPDATA%\pip\Cache` |
| `uv-cache` | Cache de instalação do uv | `%LOCALAPPDATA%\uv\cache` |
| `python311` | CPython 3.11.15 usado pelo `.venv` | `%APPDATA%\uv\python\cpython-3.11.15-windows-x86_64-none` |
| `playwright` | Navegadores instalados para automação | `%LOCALAPPDATA%\ms-playwright` |

Esses componentes podem ser compartilhados com outras ferramentas. Junctions
do Windows preservam os caminhos originais, inclusive o alias de Python usado
em `.venv/pyvenv.cfg`. Não é necessário editar os executáveis do ambiente virtual.
O destino físico está no E, mesmo quando uma ferramenta exibe o caminho do C.

O uv 0.11.32 falhou ao consultar o interpretador usando a junction como raiz
do cache (`too many temporary files exist`). Por isso, foi criado
`%APPDATA%\uv\uv.toml` com `cache-dir` apontando diretamente para
`E:\projeto\Nova pasta\.local-deps\uv-cache`, conforme a
[configuração oficial do uv](https://docs.astral.sh/uv/configuration/files/).
Após esse ajuste, `uv pip check` validou os 72 pacotes instalados. Essa configuração
vale para o usuário, não apenas para a Nyx; ao desfazer a migração, ajuste também
essa entrada. Não existia arquivo de configuração anterior nesse caminho.

**Não apagar ou renomear `.local-deps` nem mover a pasta do projeto sem ajustar
essas junctions.** Outros programas que usam esses caminhos também dependem
delas. Não incluir essa pasta em commits, ZIPs de código ou releases.

A migração local copia os arquivos, compara SHA-256, troca a pasta original
por uma junction e verifica novamente antes de remover a cópia antiga.
Os registros por componente ficam em `build/storage-migration/*.json`;
o script local da operação fica ao lado desses registros. Os registros incluem
bytes copiados e espaço livre antes/depois. Alterações concorrentes detectadas
preservam o diretório original para inspeção.

Para desfazer, primeiro encerre os programas que usam o componente e confirme
espaço suficiente no C. Copie o destino para uma pasta temporária no C, compare
os arquivos, remova **somente a junction**, e renomeie a cópia verificada para
o caminho original. Não use exclusão recursiva sobre a junction.

Essa realocação não inclui instalações de outros aplicativos, dados pessoais,
temporários gerais do Windows ou os runtimes do Codex. Novas versões do Python
instaladas fora desse caminho podem precisar de configuração adicional.

Desde 27/10/2026, a suíte pytest da Nyx usa `build/test-temp` no volume do projeto
para seus temporários por padrão. `tests/conftest.py` configura
`PYTEST_DEBUG_TEMPROOT` somente dentro do processo de testes; não muda TEMP/TMP
do usuário. `--basetemp` ou um `PYTEST_DEBUG_TEMPROOT` explícito continuam sendo
respeitados, e o pytest mantém sua retenção normal dos diretórios numerados.
Na verificação inicial, 69 testes de LPAC/snapshots/aprovação passaram no E.
Os três diretórios anteriores em `%LOCALAPPDATA%\Temp\pytest-of-darlan`
(`pytest-272`, `pytest-273`, `pytest-274`) somavam aproximadamente 208 MiB e
foram preservados para diagnóstico; não houve limpeza geral do disco.
Regressão completa no novo caminho: 762 aprovados, 1 pulado em 52,21 s, saída 0;
`build/sandbox-probes/project-temp-regression.xml` e `.log`.

Na operação de 25/10/2026, parte da cópia antiga do Python permaneceu em
`%APPDATA%\uv\python\cpython-3.11.15-windows-x86_64-none.nyx-migration-be9f1c1f7e3e471f907bf43390115669`:
algumas DLLs estavam abertas por outro processo. O novo interpretador e o Qt
foram iniciados pelo destino no E. O registro `python311.json` informa o resíduo
preservado; sua remoção deve ocorrer somente depois de liberar esses arquivos
e conferir o destino. Nenhum aplicativo de terceiros foi encerrado para isso.
