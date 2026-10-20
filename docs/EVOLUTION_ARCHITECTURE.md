# Nyx adaptativa: arquitetura e evidências

## Princípio

A capacidade vem do modelo local, ferramentas observáveis, memória recuperável e avaliação de resultados. Adicionar memória e agentes não equivale a treinar pesos nem demonstra AGI. Não há evidência de paridade com Astra ou de controle perfeito de programas e jogos.

## Circuitos com frequências diferentes

1. **Interação:** UI e voz recebem pedidos; janela continua respondendo durante inferência em worker. Pet mostra estados observados, sem exibir raciocínio interno como prova de capacidade.
2. **Decisão:** modelo produz ação estruturada; registro, política, confirmação e verificador controlam execução. Microagentes compartilham a admissão de inferência; multiplicar agentes não multiplica modelos residentes.
3. **Conhecimento:** notas externas persistem com URL, data e SHA256; deduplicação e limites evitam crescimento irrestrito. Notas são conteúdo não verificado e não podem alterar políticas. Recuperação é explícita via ferramenta evolution/search.
4. **Laboratório:** propostas declarativas de até 12 passos; simulação verifica ferramentas existentes e requisitos de revisão. Nada é executado ou promovido por essa simulação. Código proposto deverá futuramente ser avaliado em VM/Windows Sandbox com limites e fixtures confiáveis; subprocesso comum não oferece isolamento suficiente.
5. **Evolução futura:** dataset de episódios verificáveis → avaliação externa ao candidato → comparação de taxa de sucesso, latência e memória → versão candidata → implantação gradual → rollback. Testes escritos pelo próprio candidato não bastam. Treino de pesos exige pipeline separado, dados permitidos e medição contra conjunto reservado.
6. **Recuperação:** snapshots consistentes SQLite, criptografia Fernet autenticada, limite 32 MiB local/5 MiB nuvem. GitHub recebe só latest.nyxbackup e README na branch nyx-backups. Chave separada em data/backup-recovery.key, exportável pela interface; não é enviada. Quem possui essa chave consegue ler o backup. Não há recuperação sem chave.

## O que existe nesta revisão

- EvolutionLab com notas de fonte declarada, busca literal, deduplicação, propostas limitadas e simulação estrutural. Está conectado ao schema, personalidade, registro de ferramentas e painel Aprendizado.
- BackupVault recupera cópia consistente dos quatro bancos permitidos, confere autenticação e integridade SQLite e restaura em pasta nova; não substitui bancos abertos. A UI cria backups e exporta a chave. Restauração ainda usa a API Python e precisa de uma experiência guiada.
- CloudBackup usa credenciais do Git já configuradas, sem extrair tokens, sem interação de login e sem force push. Branch separada preserva desenvolvimento. Falha remota deixa cópia local e aviso; divergências exigem reconciliação. Git deve estar instalado no computador de destino. Não há retenção automática do histórico remoto: versões anteriores permanecem no Git e consomem espaço.
- Timer de backup a cada 30 minutos enquanto a interface estiver aberta, adiado durante pedido ativo. Cópia remota pode ser desativada no painel. Não é serviço permanente do Windows nem sincronização de vários computadores.
- Pet Oxynisx integrado a partir do spritesheet local gerado para o usuário, 1536×1872, nove linhas. Manifesto original previa onze linhas; as dezesseis direções do olhar ainda não existem na imagem. Fallback procedural permanece para recurso ausente.

## Próximas etapas obrigatórias

- Fila persistente de objetivos e pesquisa ociosa com orçamento diário, fontes permitidas, cancelamento e proteção contra instruções em páginas.
- Diagnóstico por eventos e verificações específicas, evitando monitoramento de tela contínuo caro; consertos devem exigir pós-condições verificáveis.
- Ambiente isolado real para candidatos de código, benchmark de regressão independente, promoção atômica e reversão de habilidade.
- Visão e controle de tela em ciclo fechado com verificação entre ações; medir latência/precisão por aplicativo antes de anunciar capacidades.
- Coordenar STT, visão e modelos de linguagem no orçamento global; medir sessões prolongadas e concorrência real.
- Completar pet, efeitos ligados a eventos, prévias de artefatos e voz expressiva com testes de áudio reais.

## Referências de projeto

- Concorrência e consumo de contexto: https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests
- Persistência de dados sensíveis no histórico Git: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
