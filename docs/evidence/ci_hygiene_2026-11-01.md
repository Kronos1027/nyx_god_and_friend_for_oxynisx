# M0 parcial — CI e scanner offline

Ambiente mínimo em `.local-deps/ci-core-env`, sem Qt/modelos/áudio/GPU:
coleção antes com11erros; depois820aprovados,13pulados,zero falhas,
17,245s. Requisitos CPU separados e imports GUI opcionais somente nos testes;
APIs Windows falsas limitadas aos testes unitários. Linux/WSL não disponível:
workflow Ubuntu atualizado, ainda não executado remotamente.

Scanner detect-secrets1.5.0 e pre-commit4.7.0 isolados no volume do projeto,
fora do runtime. Hook local instalado sem sobrescrever hook existente, cache
local, execução serial para evitar dezenas de processos em16GiB RAM.
`--no-verify` impede verificação de credenciais contra serviços externos;
instalação inicial das dependências usa rede. Nenhum segredo real enviado.

Scan do working tree: nove candidatos auditados como falsos positivos:
quatro fingerprints de código, três digests de modelos conferidos com Ollama,
um literal de teste de redação e um nome de variável de ambiente. Baseline
contém hashes, sem valores secretos; nenhum plugin ou diretório excluído.
Hook completo passou; fixture sintética bloqueada3/3 e fixture limpa aceita3/3.
Não comprova ausência de segredos em todo histórico Git, refs ou backups.

Medições de inicialização em `dev_scanner_2026-11-01.json`:
detect-secrets0,651–0,721s e49,49–50,23MiB RSS; pre-commit0,705–0,779s e
49,87–54,85MiB. RSS soma launcher/filhos e pode duplicar páginas compartilhadas.
Nenhum PID dessas CLIs observado na GPU; isso não mede alocação exata de VRAM.
Wheels120341/226261bytes; ambiente após inicialização17.969.751bytes e cache
pre-commit21.201.551bytes, ambos fora do C. Isso não é custo do scanner durante
scan completo nem memória adicionada à Nyx.

Regressão Windows completa de956casos:923aprovados,27pulados,6falhas de foco,
70,008s. Logs/XML privados `build/diagnostic/ci-hygiene-windows.*`.
Execução isolada posterior dos mesmos testes de desktop:12/12 em Windows real.
Instabilidade preservada e gate aberto; não substituir a execução com falhas
por passes isolados. Ruff limpo incluindo bench.

Fontes: [detect-secrets](https://github.com/Yelp/detect-secrets),
[pre-commit](https://pre-commit.com/). Nenhum push ou release realizado.
