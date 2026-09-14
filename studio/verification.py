"""Shared tool-evidence gates for generation, configuration, tests and publication."""
from .runner import RunnerError

COMMON=['TypeScript 构建','开始游戏','重新开始','无浏览器异常']
MATCH3=['三消参数边界','棋盘初始可玩','无效交换回退','禁止跨格交换','结算期间禁止重复操作','真实交换消除与步数','下落补位与连锁','无解棋盘重排','目标达成与失败']
LEGACY=['参数边界','键盘移动','真实得分及界面更新','危险目标扣命','游戏结束']

def required_checks(mode,runtime=None):
    names=COMMON+(MATCH3 if mode=='match3' else LEGACY)
    if runtime=='match3-v1':names+=['移动端布局','触屏交换消除']
    if runtime=='canvas-input-v2':names+=['移动端布局','触屏点击得分' if mode=='clicker' else '触屏拖动与停止','倒计时与重开']
    return names


def evidence_errors(evidence,mode):
    if not isinstance(evidence,dict):return ['测试工具没有返回有效证据']
    checks=evidence.get('checks');errors=[]
    if mode not in ('collector','dodger','clicker','match3'):errors.append('未识别的游戏模式')
    if not isinstance(checks,list):checks=[]
    passed={c.get('name') for c in checks if isinstance(c,dict) and isinstance(c.get('name'),str) and c.get('passed') is True}
    missing=[name for name in required_checks(mode,evidence.get('runtime')) if name not in passed]
    if missing:errors.append('缺少通过的实际检查：'+'、'.join(missing))
    if any(not isinstance(c,dict) or c.get('passed') is not True for c in checks):errors.append('存在失败或无效的检查记录')
    if evidence.get('passed') is not True or evidence.get('build') is not True:errors.append('构建或工具执行未通过')
    if evidence.get('console_errors'):errors.append('存在浏览器异常')
    actual=evidence.get('config')
    if not isinstance(actual,dict) or actual.get('mode')!=mode:errors.append('实际游戏模式与待测版本不一致')
    if type(evidence.get('exit_code')) is not int or evidence['exit_code']!=0:errors.append('测试进程非正常退出')
    return errors



def checked(evidence,mode):
    result=dict(evidence) if isinstance(evidence,dict) else {'passed':False,'build':False,'checks':[],'error':'测试工具没有返回有效证据'}
    result['expected_mode']=mode
    errors=evidence_errors(result,mode)
    result['gate_errors']=errors
    result['passed']=not errors
    if errors and not result.get('error'):result['error']='；'.join(errors)
    return result


async def run_checked(runner,workspace,rid,mode):
    try:evidence=await runner.run(workspace,rid)
    except RunnerError as exc:
        evidence={'passed':False,'build':False,'checks':[],'error':str(exc),'execution_state':'failed'}
    return checked(evidence,mode)
