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
