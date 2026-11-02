# Checkpoint externo e CI

Envio solicitado explicitamente pelo usuário. Branch `nyx-2` criada no GitHub,
35commits além de main, SHA confirmado por Git e API:
[58693f6](https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx/commit/58693f66c4b18bdd712522c1bed6102ab4c6a2dc).
Main e branch de backups preservadas, sem force-push. Working tree limpo no envio.

Revisão anterior ao envio:319blobs textuais novos analisados,39candidatos
do scanner conferidos como digests/fingerprints/metadados de hashes do baseline.
Nenhum valor de credencial utilizado ou validado na rede. Caminhos locais em
21blobs históricos de três documentos sanitizados apenas na cadeia ainda local;
autores/mensagens e todos os estados de código mantidos. Árvore final idêntica
antes/depois dessa operação. Referência original e mapa preservados localmente,
fora do envio; não foram alterados dados, backups ou credenciais.

Pre-commit em todos os arquivos passou. Windows:última suíte completa970passes,
27skips,0falhas/49,845s; gate Apps continua reprovado, conforme apps_expansion.

Primeiro [CI Linux real](https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx/actions/runs/41379618983)
instalou requisitos e passou Ruff; encontrou três problemas de isolamento dos
testes: os.startfile ausente, PowerShell Windows ausente e fixture Spotify
dependendo do catálogo real. Correção mantém os asserts: stub de startfile,
catálogo explicitamente NOT_FOUND e separação de rollback multiplataforma da
análise real pelo parser do Windows PowerShell.67testes focados passaram no
Windows, incluindo a análise real. Novo CI será verificado após o envio seguinte.

Publicação do progresso não é release nem conclusão dos marcos M0–M8.
