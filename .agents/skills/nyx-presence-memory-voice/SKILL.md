---
name: nyx-presence-memory-voice
description: Implementar o motor de Presença (contexto do PC com consentimento), a memória híbrida de longo prazo e o pipeline de voz de baixa latência da Nyx.
---

# Presença, memória e voz

Arquivos: `src/core/context_awareness.py`, `src/core/initiative.py`, `src/core/memory.py`, `src/core/backend.py` (embed), `src/audio/stt.py`, `src/audio/tts.py`, `src/main.py`.

**Presença (opt-in, transparente)**: consentimento por sensor na primeira execução + perfil "Companheira". Sensores locais: janela ativa por evento (`SetWinEventHook`), mídia (SMTC/`winsdk`), processos (diff), jogo (Steam/processo), abas da sessão do navegador da Nyx, pastas de projeto escolhidas (watchdog), clipboard (opt-in separado), tela sob demanda/periódica de baixa resolução → OCR/VLM → **texto** (imagem não é guardada). Redação com `safe_excerpt`; lista de apps/domínios nunca observados (gerenciadores de senha, bancos, janelas anônimas); **Modo Privado** (atalho) e **Modo Live** (não falar nem exibir conteúdo sensível). Linha do tempo SQLite com TTL e resumos; UI para ver/apagar/exportar. Bloco "Contexto agora" ≤ 300 tokens por turno.

**Memória**: FTS5 + embeddings em CPU (sem VRAM) com busca vetorial; tipos fatos/preferências, episódios, projetos, procedimentos aprendidos ("como abrir X nesta máquina funcionou assim"); consolidação quando ociosa; recuperação ≤ 600 tokens e só se relevante; UI para ver/editar/esquecer; nunca guardar segredos.

**Voz**: VAD contínuo barato → wake word leve ("Ei Nyx") → STT só após ativação (ou push-to-talk) → LLM em streaming → TTS por frase → **barge-in** e cancelamento de eco (a voz da Nyx não pode disparar o STT). Meta: wake → 1ª palavra falada < 2,5 s (Normal). Persona curta e natural; nunca afirmar que executou algo sem verificação.

Verifique com `nyx-windows-live-verify` (Presença/memória, Conversa). Modo Privado e Live precisam de teste que prove "nada gravado/falado".
