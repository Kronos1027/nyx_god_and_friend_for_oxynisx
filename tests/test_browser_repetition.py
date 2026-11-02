from core.task_runner import TaskRunner


def test_ignored_browser_decorations_cannot_bypass_repetition_guard():
    base={'action':'type','ref':'e1','snapshot':'a'*32,'text':'Nyx'}
    assert TaskRunner._signature('browser',base)==TaskRunner._signature('browser',{
        **base,'confirm':True,'tool':'browser','submit':False,'selector':None})


def test_fresh_inspection_after_successful_browser_mutation_is_new_observation():
    runner=object.__new__(TaskRunner)
    runner.steps=[]
    initial=runner._execution_signature('browser',{'action':'inspect'})
    runner.steps=[{'tool':'browser','ok':True,'params':{'action':'type'}}]
    fresh=runner._execution_signature('browser',{'action':'inspect'})
    assert initial!=fresh
    runner.steps.append({'tool':'browser','ok':True,'params':{'action':'inspect'}})
    assert runner._execution_signature('browser',{'action':'inspect'})==fresh


def test_failed_mutation_and_successful_observation_do_not_reset_loop_guard():
    runner=object.__new__(TaskRunner)
    runner.steps=[]
    initial=runner._execution_signature('browser',{'action':'inspect'})
    runner.steps=[{'tool':'browser','ok':False,'params':{'action':'type'}},
                  {'tool':'browser','ok':True,'params':{'action':'read'}}]
    assert runner._execution_signature('browser',{'action':'inspect'})==initial
