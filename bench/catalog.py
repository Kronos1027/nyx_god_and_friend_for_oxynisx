"""Complete required inventory. Unsupported harness routes remain explicit."""
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    prompt: str
    setup: str
    verifier: str
    timeout_s: int
    risk: str
    route: str = ''

    def to_dict(self):
        return asdict(self)


def cases():
    result = []
    def add(category, prompts, setup, verifier, risk, timeout=120):
        for index, prompt in enumerate(prompts, 1):
            result.append(Case(f'{category}-{index:02}', category, prompt, setup, verifier, timeout, risk))
    add('apps', ['Abre a Calculadora', 'Abre o Bloco de notas', 'Abre o navegador Chrome', 'Abre o Edge',
                 'Abre o Explorador de Arquivos', 'Abre as Configurações do Windows', 'Abre o Discord',
                 'Abre o Spotify', 'Abre a Steam', 'Abre o OBS', 'Abre o VS Code ou o Antigravity',
                 'Abre o Paint', 'Abre o Gerenciador de Tarefas', 'Abre o Terminal', 'Abre o zap'],
        'catalogued_app_owned_window', 'independent_win32_window', 'R1')
    add('desktop', ['Foque a janela de teste', 'Digite um texto no Bloco de notas de teste',
                    'Selecione tudo com o atalho', 'Cole um texto longo com acentos', 'Role a janela de teste',
                    'Minimize e maximize a janela de teste', 'Feche a janela sem salvar após confirmação',
                    'Alterne entre as duas janelas de teste'], 'owned_desktop_fixture', 'independent_win32_uia', 'R1-R3')
    add('browser', ['Abra a URL de teste', 'Pesquise e abra o segundo resultado', 'Leia a tabela da página',
                    'Preencha o formulário local', 'Preencha o campo no iframe', 'Preencha o componente Shadow DOM',
                    'Troque de aba', 'Baixe o arquivo para a pasta permitida', 'Reproduza e pause a mídia de teste',
                    'Confira que a sessão persiste após reiniciar o navegador'],
        'owned_http_fixture_and_public_sites', 'independent_cdp_observer', 'R0-R2')
    add('multi_step', ['Abra o Bloco de notas e escreva o resumo da página de teste',
                       'Pesquise e salve três fontes em arquivo', 'Abra o Spotify e toque a mídia de teste',
                       'Organize as duas janelas lado a lado'], 'owned_apps_and_pages', 'independent_world_state', 'R1-R2', 300)
    result.append(Case('multi_step-05', 'multi_step',
        'Leia individualmente numero-1.txt até numero-8.txt na pasta atual; liste os oito valores e a soma. '
        'Faça oito chamadas read_file e use calculator; não delegue.',
        'eight_numeric_files', 'independent_file_values_and_total', 300, 'R0', 'file_sum'))
    add('research', ['Pesquise uma pergunta factual e cite três fontes', 'Compare dois itens com três fontes',
                     'Pesquise uma notícia recente e cite três fontes', 'Responda uma pergunta sem resposta documentada'],
        'public_queries_with_expected_facts', 'independent_sources_and_facts', 'R0', 300)
    add('presence_memory', ['O que estou fazendo agora?', 'O que está tocando?', 'Qual jogo está aberto?',
                            'Lembre a preferência após reiniciar', 'Esqueça a preferência de teste',
                            'Ative Modo Privado e confira que nada foi coletado ou falado'],
        'consented_sensors_and_disposable_memory', 'independent_sensor_and_storage_state', 'R0-R2')
    result.extend([Case('conversation-01', 'conversation', 'Bom dia, Nyx! Como você está?',
                        'resident_local_model', 'independent_first_delta_and_no_action', 120, 'R0', 'greeting'),
                   Case('conversation-02', 'conversation', 'Quem é você?',
                        'resident_local_model', 'independent_identity_text', 120, 'R0', 'identity')])
    return [replace(case,route='native_app_ui') if case.id in NATIVE_CASES else case for case in result]


THRESHOLDS = {'apps': .95, 'desktop': .90, 'browser': .85, 'multi_step': .80,
              'research': .85, 'presence_memory': .90, 'conversation': 1.0}

NATIVE_CASES = {'apps-01':'calculator', 'apps-02':'notepad', 'apps-12':'paint'}
