import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock


APP_DIR = Path(__file__).resolve().parents[1] / 'app'


def _ensure_test_package():
    app_pkg = sys.modules.get('app')
    if app_pkg is None:
        app_pkg = types.ModuleType('app')
        app_pkg.__path__ = [str(APP_DIR)]
        sys.modules['app'] = app_pkg
    
    utils_pkg = sys.modules.get('app.utils')
    if utils_pkg is None:
        utils_pkg = types.ModuleType('app.utils')
        utils_pkg.__path__ = [str(APP_DIR / 'utils')]
        sys.modules['app.utils'] = utils_pkg
    
    services_pkg = sys.modules.get('app.services')
    if services_pkg is None:
        services_pkg = types.ModuleType('app.services')
        services_pkg.__path__ = [str(APP_DIR / 'services')]
        sys.modules['app.services'] = services_pkg


def _load_module(module_name: str, file_path: Path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_ensure_test_package()
_load_module('app.config', APP_DIR / 'config.py')
_load_module('app.utils.logger', APP_DIR / 'utils' / 'logger.py')
codex_broker_module = _load_module('app.utils.codex_broker', APP_DIR / 'utils' / 'codex_broker.py')
llm_client_module = _load_module('app.utils.llm_client', APP_DIR / 'utils' / 'llm_client.py')

zep_cloud_pkg = types.ModuleType('zep_cloud')
zep_cloud_client_pkg = types.ModuleType('zep_cloud.client')
class _FakeZep:
    def __init__(self, *args, **kwargs):
        pass
zep_cloud_client_pkg.Zep = _FakeZep
sys.modules['zep_cloud'] = zep_cloud_pkg
sys.modules['zep_cloud.client'] = zep_cloud_client_pkg

zep_paging_module = types.ModuleType('app.utils.zep_paging')
zep_paging_module.fetch_all_nodes = lambda *args, **kwargs: []
zep_paging_module.fetch_all_edges = lambda *args, **kwargs: []
sys.modules['app.utils.zep_paging'] = zep_paging_module

zep_reader_stub = types.ModuleType('app.services.zep_entity_reader')
zep_reader_stub.EntityNode = type('EntityNode', (), {})
zep_reader_stub.ZepEntityReader = type('ZepEntityReader', (), {})
sys.modules['app.services.zep_entity_reader'] = zep_reader_stub
zep_tools_module = _load_module(
    'app.services.zep_tools',
    APP_DIR / 'services' / 'zep_tools.py',
)
simulation_config_module = _load_module(
    'app.services.simulation_config_generator',
    APP_DIR / 'services' / 'simulation_config_generator.py',
)
oasis_profile_module = _load_module(
    'app.services.oasis_profile_generator',
    APP_DIR / 'services' / 'oasis_profile_generator.py',
)
report_agent_module = _load_module(
    'app.services.report_agent',
    APP_DIR / 'services' / 'report_agent.py',
)

CodexBroker = codex_broker_module.CodexBroker
LLMClient = llm_client_module.LLMClient
SimulationConfigGenerator = simulation_config_module.SimulationConfigGenerator
OasisProfileGenerator = oasis_profile_module.OasisProfileGenerator
ZepToolsService = zep_tools_module.ZepToolsService
ReportAgent = report_agent_module.ReportAgent


def test_llm_client_chat_json_uses_codex_broker_when_provider_is_codex_cli():
    fake_broker = Mock(spec=CodexBroker)
    fake_broker.chat_json.return_value = {"ok": True}
    
    client = LLMClient(provider='codex_cli', codex_broker=fake_broker)
    result = client.chat_json([{"role": "user", "content": "hello"}])
    
    assert result == {"ok": True}
    fake_broker.chat_json.assert_called_once()


def test_simulation_config_generator_uses_codex_runtime_metadata():
    fake_llm_client = Mock()
    fake_llm_client.provider = 'codex_cli'
    
    generator = SimulationConfigGenerator(llm_client=fake_llm_client)
    
    assert generator._get_runtime_llm_model() == 'gpt-5.3-codex-spark'
    assert generator._get_runtime_llm_base() == 'codex_cli'


def test_oasis_profile_generator_accepts_shared_llm_client():
    fake_llm_client = Mock()
    fake_llm_client.provider = 'codex_cli'
    
    generator = OasisProfileGenerator(llm_client=fake_llm_client, zep_api_key=None)
    
    assert generator.llm_client is fake_llm_client


def test_report_agent_uses_explicit_json_and_reasoning_lanes():
    shared_llm = Mock()
    json_llm = Mock()
    reasoning_llm = Mock()
    fake_zep_tools = Mock()
    
    agent = ReportAgent(
        graph_id='g1',
        simulation_id='s1',
        simulation_requirement='req',
        llm_client=shared_llm,
        json_llm_client=json_llm,
        reasoning_llm_client=reasoning_llm,
        zep_tools=fake_zep_tools,
    )
    
    assert agent.json_llm is json_llm
    assert agent.reasoning_llm is reasoning_llm
    assert agent.llm is reasoning_llm


def test_zep_tools_uses_explicit_json_and_reasoning_lanes():
    shared_llm = Mock()
    json_llm = Mock()
    reasoning_llm = Mock()
    
    service = ZepToolsService(
        api_key='zep-key',
        llm_client=shared_llm,
        json_llm_client=json_llm,
        reasoning_llm_client=reasoning_llm,
    )
    
    assert service.json_llm is json_llm
    assert service.reasoning_llm is reasoning_llm
    assert service.llm is shared_llm
