# Conversa em fluxo — 31/10/2026

## Escopo e método

Windows/RTX 3060, Ollama local e Qwen3.5:4b existentes, perfil Conservador.
Nenhuma dependência ou peso baixado. O modelo real passa pelo TaskRunner e
registro de produção; a guarda do ensaio impede qualquer execução de ferramenta.
Aquecimento medido à parte. O comparativo executa três respostas JSON e depois
três respostas em fluxo, sem randomização; cache, comprimento da saída e carga
do PC influenciam o tempo. Não é um benchmark controlado de todas as conversas.

A rota nova reconhece somente saudações inequívocas e a pergunta exata de
identidade, por regras ancoradas. Pedidos mistos, inclusive com texto não latino,
continuam no planejador. O Ollama recebe texto livre, sem schema nem ferramentas.
O adaptador cria action=none internamente para o contrato existente do executor;
nenhum JSON produzido pelo modelo nessa rota vira ação.

## Comparação real

`conversation_stream_2026-10-31.json`, mesmo cumprimento nas três rodadas:

| Caminho | Rodada 1 | Rodada 2 | Rodada 3 |
|---|---:|---:|---:|
| JSON completo (s) | 1,813 | 1,859 | 1,797 |
| Fluxo completo (s) | 0,656 | 0,469 | 0,359 |
| Primeiro trecho entregue ao executor (s) | 0,281 | 0,172 | 0,125 |

Todos retornaram texto não vazio, sem ação e com concatenação dos trechos igual
à resposta final. O aquecimento de 15,968 s está excluído dessas linhas.
Esses resultados atendem a meta de 1,5 s nesse caso aquecido; não comprovam voz,
modelo frio, perfil Jogo ou tarefa complexa.

Rodada final com persona e instruções compactadas, em
`conversation_persona_final_2026-10-31.json`:

| Pedido | JSON completo (s) | Fluxo completo (s) | Primeiro trecho entregue (s) |
|---|---:|---:|---:|
| Bom dia, Nyx! Como você está? | 1,781 | 0,422 | 0,203 |
| Boa noite, Nyx! | 1,640 | 0,297 | 0,156 |
| Quem é você? | 1,844 | 0,703 | 0,703 |

Na pergunta de identidade o primeiro token do provedor veio em 0,172 s, mas
o texto foi retido para conferência antes da exibição. Não confundir esse
tempo interno com a entrega à pessoa.

## Interface de produção isolada

`tools/verify_conversation_ui.py` instancia controlador Qt, TaskRunner, histórico
SQLite temporário e TTS real desativado pela configuração. Não opera a sessão
pessoal do usuário. Mede entrega à thread Qt e atualização de QLabel; a janela
é renderizada fora da tela, portanto não mede apresentação física no monitor.

- `conversation_card_ui_2026-10-31.json`: primeiro trecho no cartão em 0,219 s,
  resposta completa em 0,453 s, zero ações.
- `conversation_identity_ui_2026-10-31.json`: identidade exibida após conferência
  em 0,734 s, fluxo de UI completo em 0,797 s, zero ações. A resposta informa ser
  IA local, sem consciência nem sentimentos reais.
- Cartão parcial usa texto simples, sem interpretar HTML do modelo, e é removido
  antes da resposta final. Somente a resposta final é persistida no histórico.
  Capturas locais em build/previews foram inspecionadas; pet e overlay preservados.

## Falhas encontradas, preservadas e tratadas

1. `conversation_varied_2026-10-31.json`: o modelo disse ser humano e ter
   sentimentos reais. **Falha semântica crítica**, apesar de o critério técnico
   antigo do driver marcar passed=true. Esse campo antigo não comprova persona.
   Acrescentadas instruções factuais compactas; identidade agora é retida,
   conferida para padrões conhecidos e regenerada no máximo uma vez dentro do
   mesmo prazo. Se ambas as tentativas falham, o texto é descartado com erro;
   nenhuma identidade falsa é substituída por resposta fabricada. O driver novo
   também reprova os padrões conhecidos. Não é detector universal de falsidade.
2. `conversation_identity_guard_2026-10-31.json`: instruções extensas não cabiam
   em 1K (419 tokens estimados para 416 disponíveis). Compactadas as instruções,
   preservando fatos e reservas. Teste de contexto 1K e ensaios reais posteriores
   passaram; não aumentado contexto à força sob pressão.
3. A suíte detectou prompt estruturado acima do limite de concisão existente
   (1129 caracteres para limite 1000). Compactado o texto sem ampliar o limite
   do teste; regressão focada aprovada.
4. Um processo de teste Qt terminou com access violation após as asserções.
   A fixture agora fecha janelas, aguarda pools e processa DeferredDelete antes
   de destruir QApplication. Isso trata o ciclo do teste; não prova encerramento
   de toda sessão pessoal de produção.
5. `conversation_planner_regression_2026-10-31.json`: sete leituras corretas,
   depois recusa por RAM livre de 0,86 GiB, abaixo do piso de 1 GiB. Não houve
   geração posterior nem entrega de soma. Falha preservada, sem reduzir reservas.
   A repetição sequencial (`conversation_planner_retry_2026-10-31.json`) foi
   interrompida após uma leitura por RAM0,90GiB. O fluxo completo de arquivos
   não foi requalificado após a compactação mais recente do prompt; os passes
   anteriores permanecem históricos, não substituem essa lacuna.

Regressão final da fase: **906 aprovados, 27 pulados, zero falhas em 50,337 s**,
saída 0, Windows/navegador reais habilitados, LPAC opt-in pulado; Ruff limpo.
Fonte local: build/diagnostic/conversation-final-regression.xml. O aviso de
pynvml é de depreciação da biblioteca existente; nenhuma troca de pacote feita.

## Limites e reprodução

Não há roteamento geral de conversa, tool calling nativo, streaming llama.cpp,
TTS por frase ou latência de áudio comprovada. As regras de identidade cobrem
frases específicas; respostas diferentes ainda podem conter erros. O stream
tem limites de linha, tamanho total, texto, prazo e cancelamento cooperativo;
uma leitura HTTP bloqueada pode aguardar o timeout antes de observar cancelamento.
Saída incompleta não vira resposta final bem-sucedida. Memória local continua
sendo dado de contexto; a mudança não implementa aprendizado de pesos.

```powershell
.venv\Scripts\python.exe tools/benchmark_conversation.py --varied --output build/diagnostic/conversation-repeat.json
.venv\Scripts\python.exe tools/verify_conversation_ui.py --output build/diagnostic/conversation-ui-repeat.json
```

Referências primárias: [streaming NDJSON do Ollama](https://docs.ollama.com/api/streaming),
[contrato de chat](https://docs.ollama.com/api/chat),
[ciclo de objetos Qt](https://doc.qt.io/qt-6/qobject.html#deleteLater).
