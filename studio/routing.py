"""Conservative routing: profiles can save design work, never remove tool gates."""
import json

LABELS = {'feature':'功能开发','bugfix':'修复问题','visual':'视觉调整','optimize':'性能优化','config':'配置调整','test':'独立测试','doc':'文档编写','review':'代码审查','research':'方向调研'}
DESIGNS = ('tech','art','ux')
MINIMUM = {'feature':set(DESIGNS),'bugfix':{'tech'},'visual':{'art','ux'},'optimize':{'tech'}}


def options(store,rid):
    row=store.one('SELECT payload FROM run_options WHERE run_id=?',(rid,))
    return json.loads(row['payload']) if row and row['payload'] else {}


def save(store,rid,data):
    store.execute('UPDATE run_options SET payload=? WHERE run_id=?',(json.dumps(data,ensure_ascii=False),rid))


def select_route(run,context,kind,reason,board=None,edited=False):
    if kind=='research':
        return {'task_type':kind,'label':LABELS[kind],'reason':reason,'update':[],
                'reuse':[], 'scope':'research_only','roles':['制作人','策划'],'files':[]}
    if kind=='review':
        return {'task_type':kind,'label':LABELS[kind],'reason':reason,'update':[],
                'reuse':[], 'scope':'review_only','roles':['制作人','PM','主程','程序'],'files':[]}
    if kind=='doc':
        return {'task_type':kind,'label':LABELS[kind],'reason':reason,'update':[],
                'reuse':[], 'scope':'documents_only','roles':['制作人','PM','主程'],'files':[]}
    if kind=='test':
        return {'task_type':kind,'label':LABELS[kind],'reason':reason,'update':[],
                'reuse':[], 'scope':'report_only','roles':['制作人','PM','QA','策划'],'files':[]}
    if kind=='config':
        return {'task_type':kind,'label':LABELS[kind],'reason':reason,'update':[],
                'reuse':[], 'scope':'config_only','roles':['制作人','PM','程序','QA'],
                'files':['src/config.ts']}
    update=set(MINIMUM[kind])
    existing={d['task'] for d in context['previous_designs']}
    mode_changed=bool(context.get('confirmed_plan') and context.get('previous_plan') and context['confirmed_plan']['mode']!=context['previous_plan']['mode'])
    if not run['base_version'] or edited or mode_changed:
        update=set(DESIGNS)
        reason += '；'+('新作品执行完整设计' if not run['base_version'] else '游戏模式改变，重新执行完整设计' if mode_changed else '确认玩法已编辑，重新执行完整设计')
    update.update(set(DESIGNS)-existing)
    if board:
        update.update(board.design_updates)
        # A changed upstream design invalidates dependent design artifacts.
        while True:
            expanded=update | {t.key for t in board.tasks if t.key in DESIGNS and set(t.depends_on)&update}
            if expanded==update:break
            update=expanded
    return {'task_type':kind,'label':LABELS[kind],'reason':reason,
            'update':[k for k in DESIGNS if k in update], 'reuse':[k for k in DESIGNS if k not in update]}
