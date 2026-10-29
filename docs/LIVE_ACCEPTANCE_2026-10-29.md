# Verificação na Nyx em execução — 29/10/2026

Aplicativo iniciado de `src/main.py` neste repositório, com dados normais do
usuário e modelo local `ollama:qwen3.5:4b`. Entradas enviadas pela interface
Windows; sem modelo roteirizado, injeção de respostas ou aprovação automática.
Não houve alteração do pet nem do modo assistido.

## Observado

1. `Bom dia, Nyx! Como você está?`
   - Resposta visível: `Bom dia! Tudo bem por aqui. Como posso ajudar?`
   - Tarefa `2327885415294414b519ece02244e0db`, encerrada sem ações às
     13:17:54 UTC. JSON válido na primeira tentativa, 101 tokens.
2. `Nyx, abre a Steam aqui pra mim.`
   - Tarefa `ea28649cb9c64d0595f008a62e062a02`, 13:22:53 UTC.
   - Proposta correta: `ui_action`, `open_app`, `app=Steam`.
   - Diálogo de autorização exibido. Nenhuma abertura confirmada até o momento
     deste registro; o operador precisa aceitar a solicitação na Nyx.
   - Verificação independente somente de leitura confirmou resolução de Steam
     para `C:\Program Files (x86)\Steam\steam.exe`, pelo registro Valve/Steam.
     Isso comprova descoberta do executável, não abertura da janela.

Registros originais locais: `logs/nyx_audit_main.jsonl` e
`build/sandbox-probes/nyx-live-29.stderr.log`. Esses arquivos podem conter dados
do usuário e não são adicionados ao repositório.

## Pendente na mesma interface

- Autorizar a abertura da Steam e observar a janela real, sem login.
- Pedir a leitura individual de `build/live-acceptance/numero-1.txt` até
  `numero-8.txt`, entregando os oito valores e a soma. Os arquivos foram
  preparados no volume E; a tarefa não foi enviada enquanto o diálogo modal
  estava aberto. Esperado: oito leituras reais, extensão do bloco em auditoria,
  valores 11, 22, 33, 44, 55, 66, 77, 88 e soma 396.
- Reexecutar os dois ensaios de clique físico depois que a janela deixar de
  cobrir os alvos, sem remover a proteção contra cliques fora da janela.

## Verificação complementar do código

`continuation-regression.log/.xml`: 799 aprovados, duas falhas de alvo coberto,
um pulado, 75,18 segundos, saída 1. Navegador, Windows e sandbox reais habilitados.
As duas falhas ocorreram antes do envio dos cliques nas escalas 1,0 e 1,5.
Ruff aprovado. Os testes de controle exercitam extensão, teto, cancelamento,
persistência e descoberta de aplicativos; não substituem o ensaio de oito
leituras solicitado pelo usuário.
