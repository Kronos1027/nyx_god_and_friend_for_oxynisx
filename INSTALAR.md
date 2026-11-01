# Como instalar este pacote no repositório da Nyx
1. Extraia o conteúdo **na raiz** do repositório (ficam `AGENTS.md`, `.agents/skills/…`, `docs/…`).
2. `git switch -c nyx-2`
3. `git add AGENTS.md .agents docs INSTALAR.md && git commit -m "docs(agents): AGENTS.md, skills e especificações para a evolução da Nyx"`
4. Abra o Codex **na pasta do repositório**, escolha raciocínio **Extra High**, comece em **modo plano** e cole o conteúdo de `PROMPT_MESTRE_CODEX.md`.
5. Quando ele pedir, rode `powershell -File tools\run_live.ps1` (bateria real) e deixe o resultado na pasta `docs\evidence\`.
