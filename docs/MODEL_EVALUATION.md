# Avaliação local do modelo — 2026-10-21

## Máquina observada

Windows, 15,93 GiB de RAM, RTX 3060 com 12 GiB de VRAM, 16 processadores lógicos. A RAM disponível variou de menos de 2 GiB nos diagnósticos anteriores para aproximadamente 5,8 GiB antes da troca. Portanto, os ensaios antigos e novos não são uma comparação controlada exclusivamente de pesos.

## Pesquisa e escolha

- Qwen3.5 4B: distribuição oficial do Qwen, licença Apache 2.0, recursos de visão, ferramentas e controle de thinking. Fonte: https://huggingface.co/Qwen/Qwen3.5-4B e https://ollama.com/library/qwen3.5:4b .
- Granite 4 3B: alternativa Apache 2.0, aproximadamente 2,1 GB, suporte a português e ferramentas. Pesquisado, não baixado nem comparado localmente. Fonte: https://ollama.com/library/granite4:3b .
- Metadados locais de thinking foram consultados conforme https://docs.ollama.com/capabilities/thinking . A Nyx envia think=false somente quando o runtime declara suporte a false; outros modelos preservam o padrão. Isso evita consumir o orçamento curto de saída exclusivamente em thinking na interação cotidiana.

Qwen3.5:4b foi baixado para o armazenamento Ollama configurado. Inventário real: 3.324.173.934 bytes, 4,2B parâmetros, Q4_K_M, digest d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04. O tamanho observado no runtime prevalece sobre o tamanho variável do tag na página da biblioteca. A seleção automática já prioriza esse modelo quando cabe nas reservas existentes.

## Evidências

1. Qwen2.5 3B leu dois arquivos, tentou um terceiro inexistente e não calculou a soma: falha em 29,86 s.
2. Qwen3.5 4B leu 81 e 20, respondeu 101 em 47,36 s; o avaliador rejeitou incorretamente o ponto final. A tentativa original foi preservada. Corrigida a expressão regular e adicionados casos de regressão para pontuação, decimais e números parciais.
3. Qwen3.5 4B leu 67 e 65, respondeu 132: aprovado em 11,67 s.
4. Qwen3.5 4B leu 36 e 85, respondeu 121: aprovado em 12,02 s.
5. Conversa pela UI nativa: resposta correta em português em 2,58 s, 127 eventos de interface processados, nenhuma ação/ferramenta ou confirmação indevida.

Nos casos 3 e 4, o diagnóstico manteve o modelo por 30 segundos entre etapas; a configuração anterior descarregava após cada chamada. Portanto, não atribuir a redução de tempo apenas à troca do modelo. A aplicação normalmente mantém o modelo por cinco minutos, com uma inferência ativa por vez.

Telemetria durante o ensaio: size == size_vram == 3.071.289.588 bytes (aproximadamente 2,86 GiB), contexto efetivo 2048; aproximadamente 3,97 GiB de RAM livres. É uma amostra pontual, não pico de memória de longa duração.

## Executor e avaliação

O planejador recebe as ferramentas realmente registradas e um schema limitado a elas. Um registro compacto mantém todas as etapas, incluindo falhas antigas; campos cortados têm indicação explícita. O registro é limitado a doze ações e o texto de contexto permanece limitado. Isso não garante caber em toda janela/tokenização de modelo.

O diagnóstico usa valores aleatórios, exige as duas leituras verificadas, reconhece números completos e salva tentativas separadas em build/previews/task-attempts. A presença dos números corretos é uma checagem limitada, não um verificador semântico universal.

Suite: 279 passed, 1 skipped, 1 warning; Ruff aprovado. Ainda faltam tarefas variadas de arquivos, navegação, código, visão e voz, benchmarks controlados por modelo, testes prolongados e seleção baseada em capacidade comprovada. Não há evidência de AGI ou equivalência ao Astra.
