# Nyx — assistente local para Windows

Nyx é um projeto Python para um assistente desktop que usa modelos locais por Ollama ou llama.cpp. O código já inclui interface PyQt, voz, ferramentas para Windows, memória local, auditoria e confirmações para ações sensíveis.

## O que está implementado

- Interface nativa de conversas, histórico pesquisável, agenda e painéis móveis/destacáveis. Três temas, cores, fonte e movimento configuráveis; `--overlay` abre apenas a companhia flutuante.
- Conversa local por Ollama ou modelo GGUF via llama.cpp; modo `--offline` para desenvolvimento.
- Se já estiverem instalados, Nyx prioriza Qwen 3.5 e Gemma 4. Ela não baixa modelos automaticamente.
- Antes de escolher um modelo Ollama, Nyx compara o tamanho instalado com RAM e VRAM livres, reservando espaço para Windows e tela. Cada requisição reduz o contexto entre 1k e 4k conforme a memória disponível.
- Voz local com faster-whisper e Kokoro, com fallback SAPI5 no Windows.
- Agenda local de lembretes únicos com persistência, listagem, cancelamento e aviso no overlay.
- Equipe inicial de microagentes: até duas investigações simultâneas, com inferência serializada e papéis somente de leitura para web, arquivos ou estado do sistema. Escritas, shell e automação de interface continuam no agente principal, com confirmação.
- Ferramentas para arquivos em sandbox, pesquisa web, automação Windows, clipboard, macros, projetos e workspace.
- Calculadora decimal limitada para valores observados e consulta somente leitura dos jogos Steam instalados por manifests locais.
- Na interface Windows, tarefas continuam além de seis ações quando há progresso verificado: blocos ampliados automaticamente até 48 ações/30 minutos, com observação entre etapas, confirmações individuais e botão Interromper. O prazo é cooperativo; uma operação já iniciada pode precisar terminar. [Limites e validação do executor](docs/TASK_EXECUTION.md).
- Memória SQLite, trilha de auditoria e modo assistido como padrão.
- Inferência e ações aprovadas rodam em segundo plano. Todas as inferências Ollama da Nyx usam uma fila FIFO limitada: uma ativa e no máximo duas aguardando; a próxima é recusada até haver espaço. O limite vale para chamadas originadas pela Nyx, não para outros aplicativos que compartilham o mesmo serviço Ollama.
- Fila de fala limitada para não acumular áudio indefinidamente.
- Companheira Oxynisx animada usando o pet criado pelo usuário; nove ciclos, reações ao clique e efeitos leves, pausados quando ocultos.
- Laboratório de aprendizado: notas com URLs, busca persistente e propostas de habilidades com simulação estrutural. Simular não executa ações nem comprova funcionamento.
- Estudo em intervalos: fila persistente, cancelamento e prévia de trechos de documentação Python/Windows/Ollama. Até quatro leituras por dia, uma a cada 15 minutos, quando não há pedidos ativos e há recursos disponíveis. A coleta não treina o modelo e pode ser pausada no painel Aprendizado.
- Backup local criptografado dos bancos a cada 30 minutos com o app aberto; cópia na branch `nyx-backups` do [repositório privado autorizado](https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx). Requer Git e credenciais previamente configuradas. A chave de recuperação fica separada; exporte-a pelo painel Aprendizado e guarde-a em local privado.

A [arquitetura adaptativa](docs/EVOLUTION_ARCHITECTURE.md) separa o que está implementado das próximas etapas de pesquisa ociosa, testes isolados, promoção de código e aprendizado de modelos. A [meta completa](docs/PRODUCT_GOAL.md) permanece ativa.

## Executar no Windows

Requer Python 3.11. Para a experiência de desktop, instale as dependências do Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-windows.txt
```

O launcher `run_nyx.ps1` verifica a GPU e Ollama e inicia a interface. Ollama e um modelo local compatível devem estar instalados para conversar com um modelo. Também é possível iniciar diretamente:

```powershell
.\.venv\Scripts\python.exe src/main.py
.\.venv\Scripts\python.exe src/main.py --offline
.\.venv\Scripts\python.exe src/main.py --model caminho\para\modelo.gguf
```

## Criar o aplicativo Windows

Com as dependências de Windows instaladas, adicione o empacotador e gere uma pasta portátil com `Nyx.exe`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\packaging\build.ps1 -Clean
```

O ZIP aparece em `dist/`. Extraia tudo e execute `install.ps1` para instalar por usuário e criar um atalho no menu Iniciar; `uninstall.ps1` remove o programa e preserva dados. Configurações, memória, lembretes, logs, modelos de voz e caches ficam em `%LOCALAPPDATA%\Nyx`. Pesos Ollama/GGUF não são embutidos no aplicativo. Na instalação padrão, o botão **Atualizações** consulta a última versão estável publicada no GitHub. A Nyx pede confirmação, verifica SHA-256 e os caminhos do pacote, instala ao fechar e roda autoteste com restauração da cópia anterior se o autoteste falhar. O botão só aparece em builds instalados na pasta padrão; uma publicação compatível precisa existir no GitHub para o recurso baixar uma versão.

## Segurança e limites atuais

- Ações de risco exigem confirmação e operações de arquivo respeitam raízes permitidas.
- O modo autônomo pode ser habilitado pela interface e volta ao modo assistido após o prazo configurado. Ações destrutivas continuam exigindo confirmação.
- A inferência em segundo plano mantém a janela livre, mas fechar o aplicativo durante uma chamada longa pode aguardar o encerramento do processo.
- Quando o launcher inicia Ollama, limita a um modelo carregado, uma geração paralela, oito pedidos na fila e descarrega modelos após cinco minutos; também desativa os modelos cloud. Um Ollama que já estava aberto precisa ser reiniciado para receber esses limites.
- O broker de VRAM ainda não está ligado ao ciclo real de carregamento dos modelos; não deve ser tratado como um limitador global de GPU.
- A agenda cobre lembretes únicos; não executa tarefas ou comandos em segundo plano. Microagentes ainda não fazem escrita, shell ou automação, nem cooperam em planos longos com memória compartilhada. Ainda não há MSI, assinatura Authenticode, treinamento próprio ou modelo de visão conectado ao fluxo padrão.
- Nyx não é AGI e não pode executar literalmente qualquer tarefa. O que consegue fazer depende do modelo local, das ferramentas instaladas, das permissões do Windows e da conexão disponível para pesquisa.

## Verificação

Execute `python -m pytest` e `ruff check src/ tests/` no ambiente virtual. O [STATUS.md](STATUS.md) registra a última validação detalhada; atualize-o quando os resultados mudarem.
