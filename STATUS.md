# Nyx — estado verificado

Última atualização: 2026-10-20

## Revisão mais recente: interface, aprendizado e recuperação

- Interface principal nativa com conversas SQLite, busca, Markdown sem carregamento de recursos externos, painéis móveis, três temas, fonte, cores e movimento persistentes. Agenda real e configuração dos caminhos Ollama estão conectadas. Overlay separado via `--overlay`.
- Pet Oxynisx do usuário integrado, nove linhas de animações. Direções do olhar ainda ausentes no atlas original.
- `EvolutionLab` conectado à ferramenta `evolution` e painel Aprendizado: notas com URL/data/hash, busca, deduplicação, limites e propostas declarativas. Simulação é estrutural; não executa código, não demonstra aprendizado de pesos nem aprova habilidades.
- Backup local Fernet dos quatro bancos permitidos, cópia SQLite consistente, limite 32 MiB e restauração com integridade em pasta nova. Timer a cada 30 minutos com app aberto e ocioso; chave exportável pela interface e excluída da nuvem. Restauração guiada pela interface permanece pendente.
- Repositório privado `Kronos1027/nyx_god_and_friend_for_oxynisx` verificado com permissão de escrita e inicializado. Remote local `evolution` adicionado, preservando `origin`. Primeiro backup criptografado enviado e confirmado na branch `nyx-backups`, commit `d71aab9f7ed37fbeb165afa4af3108303371591f`. Chave não enviada. Cópias remotas exigem Git autenticado e ficam limitadas a 5 MiB, sem limpeza automática do histórico remoto.
- Ollama agora é gerenciado pelo Python usando caminhos persistentes verificados: `E:\Ollama\ollama.exe` e `E:\OllamaModelos`. Serviço local iniciado com max_loaded_models=1, num_parallel=1, max_queue=8 e no_cloud=true, confirmados no log. Serviços externos já abertos são reutilizados.
- Orçamento revisado: reserva 2 GiB de RAM e 4 GiB de VRAM; pesos CUDA consideram staging no host. GGUF exige espaço do arquivo inteiro em RAM, pois a wheel instalada é CPU-only. Chamadas compartilham admissão limitada. STT ainda precisa de coordenação global.
- Último diagnóstico real de UI: Qwen2.5 3B respondeu `Olá!` em 3,33 segundos, 166 eventos de UI durante a inferência, JSON válido, zero ferramentas e zero confirmações. Teste curto, sem provar qualidade geral ou velocidade sustentada. Modelo menor de 1B anteriormente propôs ação inadequada para saudação; isso continua sendo uma limitação de qualidade dos modelos pequenos.
- Suíte atual: **226 passed, 1 skipped, 1 warning**; Ruff aprovado. Testes novos cobrem proveniência, deduplicação, simulação sem execução, criptografia, autenticação, recuperação SQLite/WAL e restrições da cópia Git. O aviso é o conhecido COM/STA do pywinauto.
- Pacote Windows reconstruído com a interface e pet atuais; autoteste do executável aprovado incluindo renderização real da janela (1320×860). ZIP SHA256: `7efbb7b874b66848c9edc5e9749a962bcd416e5dc1b99d3cdc02ea0dc1adc765`. Ainda não é uma release publicada e a versão permanece 0.1.0 de desenvolvimento.
- Correção de conexões SQLite da agenda evita bloqueio de arquivo no Windows. Hotkeys agora entregam sinais à thread visual, incluindo bloqueio de controle de tela. O bloqueio de tela não cancela gerações e tarefas já em execução.

A arquitetura e lacunas estão em `docs/EVOLUTION_ARCHITECTURE.md`. Os registros abaixo descrevem revisões anteriores; informações conflitantes de runtime e testes foram substituídas por esta seção.

## O que existe no código

- App desktop Python/PyQt para Windows, com overlay, expressões e controles.
- Conversa local via Ollama ou llama.cpp; existe modo offline determinístico para desenvolvimento.
- Ollama recebe um JSON Schema estrito; o modelo instalado Qwen2.5 3B foi testado e conseguiu emitir uma ação de lembrete válida.
- Seleção automática prefere Qwen 3.5/Gemma 4 quando já instalados; nunca baixa pesos sem ação do usuário. O monitor agora mostra se os pesos ativos do Ollama estão em CPU, GPU ou divididos.
- Fala local via Kokoro/SAPI5 e transcrição via faster-whisper.
- Ferramentas registradas para arquivos em sandbox, shell por templates allowlist, UI Windows, web, clipboard, macros, telemetria, workspace e MCP.
- Agenda SQLite de lembretes únicos, persistente entre reinícios, com listar/cancelar e alerta no overlay. Lembretes só notificam; não executam comandos.
- Memória SQLite/FTS, logs de auditoria, verificação de ações e confirmações sensíveis.
- Inferência, ações aprovadas e captura de voz são serializadas fora da thread visual. A fila de TTS tem no máximo oito falas pendentes.
- O avatar agora é uma coruja pixel art com sete expressões; suas cores indicam modo e erro.
- Equipe de microagentes inicial conectada à ação `agent_team`: até dois especialistas investigam web, arquivos permitidos ou estado do sistema. Inferência compartilhada é serializada para controlar a carga; ferramentas seguras podem executar em paralelo. Agentes filhos não podem escrever arquivos, usar shell ou controlar janelas, e cada decisão é auditada.
- Aplicativo Windows x64 empacotado com PyInstaller 6.22.3, versão 0.1.0. O ZIP portátil contém o executável, runtime, instalador e desinstalador por usuário; dados e pesos ficam fora da pasta do programa.

## Verificação desta revisão

No ambiente Windows do projeto:

```text
python -m ruff check src/ tests/
All checks passed!

python -m pytest
201 passed, 1 skipped, 1 warning
```

O aviso conhecido vem do pywinauto recomendando o modo STA do COM. A suíte não valida áudio real, qualidade do modelo em português ou interação visual completa em diferentes escalas de tela.

- `packaging/build.ps1 -Clean` gerou `dist/Nyx-0.1.0-windows-x64-portable.zip` (147 MB), gravou SHA256 e executou `Nyx.exe --self-check` dentro do pacote. Qt, Kokoro, faster-whisper, llama.cpp, áudio, schema e gravação em AppData passaram.
- O instalador e desinstalador foram exercitados numa pasta temporária: o executável foi copiado com o mesmo SHA256 e removido; os dados em `%LOCALAPPDATA%\Nyx` foram preservados.
- A escrita real no clipboard não pôde ser verificada nesta execução: `OpenClipboard` retorna `Access denied` ao próprio processo de ferramenta e não há janela dona do clipboard. Os testes da lógica usam um clipboard em memória; escrita real deve ser confirmada numa sessão interativa do aplicativo.

## Validação do runtime local (2026-10-20)

- Ollama foi atualizado para 0.40.6; o servidor registrou `version 0.40.6` e detectou a NVIDIA RTX 3060 (compute 8.6, 12 GiB totais, 11 GiB disponíveis). Os cinco modelos existentes continuaram acessíveis no diretório `E:\OllamaModelos`.
- Inferência real com `qwen2.5:3b-instruct` respondeu em português. O primeiro pedido levou 52,1 s, incluindo carregamento do modelo (27,85 s); a geração reportou 22 tokens em 5,96 s (~3,7 tokens/s). Ollama reportou 2,16 GB do modelo na VRAM e contexto 4096. É uma validação funcional, não uma garantia de velocidade sustentada.
- A instância atual foi iniciada fora do launcher da Nyx: seus limites (`MAX_LOADED_MODELS`, fila e modo sem nuvem) ainda não foram aplicados a esse processo. O launcher detecta essa condição e avisa que os limites só passam a valer após reiniciar o servidor.
- O Qwen2.5 3B em Ollama emitiu uma ação `agent_team` válida com dois papéis e tarefas. Um pedido anterior sem limite de saída excedeu 9 mil tokens e atingiu timeout; por isso, Ollama agora tem limite rígido de 512 tokens por geração. Repeti o teste após o limite e o modelo entregou a ação estruturada válida.
- A equipe executou duas chamadas com o Qwen2.5 3B e ferramentas reais em paralelo: pesquisa web (que não retornou resultado direto nessa consulta) e telemetria local (CPU, RAM, RTX 3060 e Ollama). Também foram bloqueados os subcomandos web de localização/clima e consulta Git com caminho arbitrário.
- O roteador revisado leu o inventário instalado e selecionou `qwen2.5:3b-instruct` por caber no orçamento atual de RAM/VRAM; os modelos maiores que não cabiam foram excluídos. Uma chamada real pela mesma função de rota retornou JSON válido em português com contexto dinâmico e `keep_alive=0`; depois, `/api/ps` voltou vazio e o uso da RTX ficou em 841 MiB usados / 11.275 MiB livres.
- As chamadas de inferência Ollama originadas pela Nyx agora compartilham uma fila FIFO global no processo: uma ativa, até duas esperando, prazo de espera de 45 s; contexto limitado dinamicamente a 1k–4k e recusa sob pressão crítica de RAM/VRAM. A escolha do modelo reserva 4 GiB de VRAM e 3 GiB de RAM. Isso protege a Nyx, não impõe limites a outros programas que usam o serviço Ollama.

## Ainda não implementado ou não validado

- Expansão dos microagentes para planejamento cooperativo de múltiplas etapas, síntese própria e cancelamento de tarefas já iniciadas.
- Atualizador no app para a instalação padrão: consulta a versão estável mais recente, baixa em blocos, confere o SHA-256 e bloqueia ZIPs com caminhos perigosos. A troca só ocorre após confirmação, num helper separado, com autoteste e rollback automático se a versão nova não iniciar corretamente. O workflow de publicação existe, mas nenhum release foi publicado nesta rodada; portanto, não há atualização remota disponível ainda. A assinatura Authenticode continua pendente.
- Treinamento ou ajuste fino de modelo. Não há dataset local nem pipeline de treino.
- Controle total de todos os carregamentos: o novo orçamento governa seleção/contexto/fila das requisições Ollama da Nyx, mas `ModelBroker` ainda não coordena cargas de llama.cpp e faster-whisper; e o processo Ollama que já estava aberto mantém suas configurações próprias para os outros clientes.
- A medição anterior em Ollama 0.32.5 usava CPU; a atualização para 0.40.6 ativou o backend CUDA do Ollama. O backend alternativo `llama-cpp-python` instalado segue CPU-only e sua wheel CUDA requer o CUDA Toolkit, ausente nesta máquina; não houve instalação do Toolkit.
- Validação prática de longas sessões, centenas de pedidos, uso intenso de memória/GPU e recuperação após falhas.
- AGI ou execução garantida de qualquer tarefa. Capacidades dependem do modelo, ferramentas, permissões e recursos da máquina.

## Próximas frentes

1. Integrar o orçamento central com cargas de llama.cpp e faster-whisper e testar contenção entre essas cargas; decidir como a Nyx deve administrar o serviço Ollama existente sem interromper outros clientes.
2. Desenhar ciclos e ações interativas para a coruja e permitir escolher voz, volume e preferências.
3. Publicar uma release Windows com os dois assets esperados e testar o fluxo de atualização entre duas versões instaladas.
4. Validar o fluxo completo no Windows alvo com um modelo local real, áudio, automação de UI e rollback da atualização.
