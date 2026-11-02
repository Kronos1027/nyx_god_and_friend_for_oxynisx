import pytest

from tools.browser_locators import clean_locator


def test_scope_chains_remain_explicit_bounded_data():
    value = {'shadow':['#panel','#nested'], 'frame':['iframe'], 'role':'textbox', 'name':'Nome'}
    assert clean_locator(value) == value
    for bad in [dict(css='input',shadow=[]), dict(css='input',shadow=['x']*9),
                dict(css='input',frame='iframe'), dict(css='input',shadow=[None]),
                dict(css='x',code='alert(1)'), dict(ref=1,snapshot='a'*32,css='button')]:
        with pytest.raises(ValueError):
            clean_locator(bad)


def test_accessibility_refs_require_snapshot_and_never_mix_locator_types():
    assert clean_locator({'ref':3,'snapshot':'a'*32}) == {'ref':'e3','snapshot':'a'*32}
    for bad in [{'ref':0,'snapshot':'a'*32},{'ref':'e1','snapshot':''},{'ref':'e1'},{'snapshot':'a'*32},
                {'ref':'e1','snapshot':'a'*32,'shadow':['x']}]:
        with pytest.raises(ValueError):
            clean_locator(bad)


def test_new_external_effect_actions_always_require_confirmation():
    from tools.browser_tool import requires_external_confirmation, is_sensitive_action
    from tools.registry import ToolSpec
    spec = ToolSpec('browser','fixture',destructive_probe=requires_external_confirmation)
    for params in ({'action':'press','key':'Enter'},{'action':'select','value':'a'},
                   {'action':'type','text':'exact','submit':True}):
        assert spec.is_destructive_for(params)
    assert not spec.is_destructive_for({'action':'type','submit':False})
    assert not spec.is_destructive_for({'action':'hover'})
    assert all(is_sensitive_action(action) for action in ('select','hover','press'))


def test_press_and_hover_do_not_gain_success_from_nonempty_dispatch_text():
    from core.verifier import ActionVerifier
    from tools.registry import ToolResult
    for action in ('press','hover','select'):
        assert not ActionVerifier().verify('browser',{'action':action},ToolResult(True,'sent',meta={'verified':False})).verified
