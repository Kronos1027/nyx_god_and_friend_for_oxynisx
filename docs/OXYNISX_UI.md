# Oxynisx e interface nativa

## Material integrado

Origem autorizada: `C:/Users/darlan/Documents/Codex/2026-10-20/pets-plugin-work-pets-openai-curated-4/work/oxynisx/final/spritesheet-extended.png`.

O arquivo copiado é idêntico à origem (SHA256 `a140dcfabff911bc2cceae323f63e32c16af721119a9870e13acf3927631c8a9`). Nenhum desenho da origem foi alterado. O atlas possui 1536 × 2288 pixels e transparência. As direções seguem `qa/direction-semantics.json`: zero para cima, 90 para a direita, 180 para baixo e 270 para a esquerda. Avisos visuais da origem: 135, 157.5, 202.5 e 337.5 graus.

## Uso

- Abra **Mascote na área de trabalho** no painel Companhia e sistema.
- Arraste a Oxynisx para movê-la. Clique com o botão direito para abrir as ações.
- Duplo clique mostra ou recolhe o campo de conversa. Enter envia a mensagem.
- O menu oferece voz, Estúdio, abertura da janela principal, modo de permissão, cancelamento, atualização e recolhimento.
- O olhar acompanha o cursor durante repouso; os demais estados conservam as animações de atividade.
- **Personalizar → Aparência e voz** muda tema, cor, fonte, movimento e leitura das respostas. Sem movimento, os timers do pet e das áreas animadas param.
- **Foco** recolhe e restaura os painéis da janela principal.
- **Aprendizado** separa Estudos, Conhecimento e Backups. **Personalizar** separa aparência de configuração do modelo.

## Evidências e limites

`tools/preview_desktop.py` renderiza as telas com dados temporários, sem ler conversas pessoais. Os previews do pet são PNGs RGBA com alfa de 0 a 255, em 360 × 204 (recolhido) e 360 × 384 (conversa demonstrativa). Capturas são estáticas e offscreen; não comprovam composição Windows em diferentes GPUs ou DPI. A suíte testa direções, cache limitado, transparência, desligamento dos timers, modo Foco e controles existentes. Voz depende dos componentes locais; a reformulação visual não muda a inteligência do modelo nem reproduz todas as funções do pet do ChatGPT.
