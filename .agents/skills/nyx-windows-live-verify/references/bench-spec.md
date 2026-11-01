# Especificação da bateria real (`bench/` + `tools/run_bench.py`)

Cada tarefa = `{id, categoria, pedido_em_pt_br, setup, verificador_independente, timeout_s, risco}`. O **verificador não usa o código da Nyx**: confere o estado do mundo (janela existe via Win32/UIA, arquivo com conteúdo, URL final no CDP, texto na página, processo vivo).

Execução: 3× por tarefa; taxa = mediana; guardar variância. Reiniciar o estado entre execuções (fechar apps abertos pela tarefa). Tarefas R2/R3 usam fixtures e confirmam via harness (simulando o clique humano **somente** no diálogo, jamais na ação).

Resultado JSON por tarefa: `{id, run, ok, tempo_s, verificador, falso_sucesso(bool), erro_tipado, trace_path, vram_pico_mib, ram_pico_mib}`.

## Tarefas mínimas (40)
- **Abrir apps (15)**: Calculadora, Bloco de notas, Chrome ("o navegador"), Edge, Explorador, Configurações, Discord, Spotify, Steam, OBS, VS Code/Antigravity, Paint, Gerenciador de Tarefas, Terminal, WhatsApp. Pedidos com nomes informais ("abre o zap", "o navegador").
- **Desktop (8)**: focar janela, digitar no Bloco de notas, hotkey, colar texto longo com acentos, rolar, minimizar/maximizar, fechar sem salvar (R3 confirma), alternar janelas.
- **Navegador (10)**: abrir URL, pesquisar e abrir 2º resultado, ler tabela, formulário local, iframe, shadow DOM, trocar aba, baixar arquivo para pasta permitida, play/pause de mídia, sessão logada que persiste após reiniciar.
- **Multi-etapa (5)**: abrir Bloco de notas e escrever resumo de página; pesquisar e salvar 3 fontes em arquivo; abrir Spotify e tocar algo; dois apps lado a lado; ler 8 arquivos e somar.
- **Pesquisa (4)**: factual com fonte, comparação, notícia recente, pergunta sem resposta (deve dizer que não achou).
- **Presença/memória (6)**: "o que estou fazendo", "o que toca", jogo atual, lembrar preferência após reiniciar, esquecer sob pedido, modo privado (nada gravado/falado).
- **Conversa (2)**: latência 1º token; consistência de persona.

## Limiares (todos medidos em 3 execuções)
Apps ≥ 95% · Desktop ≥ 90% · Navegador ≥ 85% · Multi-etapa ≥ 80% · Pesquisa ≥ 85% (com ≥ 3 fontes citadas) · Presença/memória ≥ 90% · **Falso sucesso = 0** · 1º token < 1,5 s (modelo residente) · VRAM pico Normal ≤ 9,5 GiB.

## Soak (M8)
2 h de uso simulado (conversa + tarefas + presença ligada): sem vazamento (RAM do processo estável ±10%), sem crash, VRAM estável, breaker não preso aberto.
