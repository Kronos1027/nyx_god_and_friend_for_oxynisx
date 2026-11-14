# Nyx Evolution — Lote 04: arquitetura híbrida e protótipo Rust nativo

## Evidência externa (novembro de 2026)

- Em **10/11/2026**, Elon Musk declarou que a xAI substituiu
  **JAX/SGLang** por uma pilha própria em **C/C++** para treinamento por
  reforço e inferência do **Grok 4.8**. Isso não comprova que toda a xAI
  aboliu Python. Declaração: https://x.com/elonmusk/status/2120088070443655190
- A inferência local eficiente pode usar o runtime **llama.cpp**, que
  já possui componentes C/C++, kernels CUDA e quantização:
  https://github.com/ggml-org/llama.cpp
- **PyO3 + Maturin** suportam extensões Python escritas em Rust, incluindo
  wheels Windows e Linux. Documentação:
  https://pyo3.rs/ e https://www.maturin.rs/
- **Tauri 2** oferece interface desktop Windows com núcleo Rust/WebView2,
  mas exige Microsoft C++ Build Tools e WebView2 e ainda precisaria de
  testes de voz, overlay, janela sempre visível e controle da UI:
  https://v2.tauri.app/concept/architecture/

## O que os dados locais da Nyx mostram

Na branch experimental atual, a Nyx usa:
- Python 3.11, PyQt6, SQLite, Ollama local, agentes e ferramentas;
- Qwen/LLM através do backend local (o peso dos modelos, KV cache e
  CUDA NÃO vivem primariamente no interpretador Python);
- fila de inferência serializada, limite de RAM, contexto limitado e
  execução verificável com aprovação explícita;
- a memória de longo prazo agrega fatos SQLite em um bloco contextual,
  percorrendo e ranqueando potencialmente milhares de entradas por chamada.

Portar as funções que apenas fazem algumas chamadas HTTP do Ollama
para C **não** acelera os kernels do modelo. Reescrever tudo de uma vez
também destruiria a cobertura de regressão acumulada.

## Matriz de decisão

| Camada | Linguagem preferida | Evidência a obter |
|---|---|---|
| Inferência e kernels GPU | C/C++/CUDA por um runtime existente | tokens/s, VRAM, TTFT e qualidade |
| Políticas, ferramentas, laboratório de IA | Python existente | sucesso de tarefa e bugs |
| Memória e processamento intenso de dados | Rust se benchmark + paridade aprovarem | latência e RSS |
| Supervisor de processos / tray / serviço Windows | Rust após protótipo separado | CPU ociosa, RSS, cancelamento |
| Interface | manter PyQt6 enquanto funciona; avaliar Tauri 2 em separado | inicialização, memória e integração |
| Pesquisa KRA-13 | Python/PyTorch para experimento; runtime Rust/C++ só depois | recall, taxa de colisão e generalização |

**Decisão:** arquitetura híbrida, com compilação seletiva e interfaces bem
definidas, mantendo a instalação Python/Windows atual até evidência.

## Módulo 04-A — seletor de memória Rust (experimento)

Arquivos:
- `native/nyx_memory/Cargo.toml`, `pyproject.toml` e `src/lib.rs`:
  extensão PyO3, sem I/O, rede, banco de dados ou permissões.
- `src/core/native_memory.py`: ponte opcional Rust; usa a referência
  Python se a extensão estiver ausente, falhar ou divergência ocorrer
  quando a comparação estiver habilitada.
- `src/core/memory.py`: ponto único de integração; padrão é Python.
- `tests/test_native_memory_adapter.py`: fallback e opt-in;
  `tests/test_native_memory_parity.py`: paridade com 10 mil fatos,
  Português, orçamentos e entradas inconsistentes.
- `.github/workflows/native-ci.yml`: compila no Linux e Windows,
  roda `cargo test`, gera wheel de release e compara com o seletor Python.

Para habilitar apenas após compilar e instalar um wheel adequado:

```powershell
$env:NYX_NATIVE_MEMORY="1"
$env:NYX_NATIVE_COMPARE="1"
py -3.11 -m pytest -q tests/test_native_memory_parity.py
```

A comparação usa **ambos** os implementos e é mais lenta;
servirá para confirmar igualdade antes de medir o desempenho nativo.
Para rollback imediato, remova `NYX_NATIVE_MEMORY`. A aplicação está
em modo Python por padrão. Não se instala automaticamente no PC.

## Pontos que exigem investigação antes de promover

1. Paridade de `str.casefold` Python com `to_lowercase` Rust,
   sobretudo Unicode especial (ß, sigma final, İ etc.). A versão
   nativa é experimental e NÃO garante paridade para toda a Unicode.
2. Benchmark de 10 mil e 100 mil fatos: latência, alocação de memória
   e overhead de atravessar a fronteira Python/Rust.
3. Desempenho no Windows Ryzen 7 5700X com Ollama/Qwen carregado
   simultaneamente; um benchmark isolado não substitui esse cenário.
4. Se a vantagem for pequena, manter Python e melhorar o algoritmo;
   não transformar complexidade de compilação em requisito sem benefício.
5. Migração do controlador de processos para Rust somente quando
   testes de crash/restart, política de consentimento e comunicação
   por protocolo fixo estiverem implementados e aprovados.

## Critério de aceitação do lote

Compilação real dos binários Windows/Linux, paridade funcional,
`cargo test`, testes de regressão Python existentes, sem novas
permissões e sem perda de memórias SQLite. Só então testar performance.
Um aplicativo Rust-only será avaliado separadamente, não imposto como
uma reescrita integral sem medições.

A meta de 1.800 módulos não foi atingida. Somente módulos com contrato,
teste e integração devem contar como implementados.
