"""Resolve inherited design records without fabricating execution or usage."""
import json


def decoded_steps(store, rid):
    steps = store.query('SELECT * FROM agent_steps WHERE run_id=? ORDER BY rowid', (rid,))
    sources={}
    for event in store.query("SELECT payload FROM events WHERE run_id=? AND kind IN ('model_result','model_error','agent_cancelled') ORDER BY id",(rid,)):
        payload=json.loads(event['payload'])
        if payload.get('step_id'):sources[payload['step_id']]={key:payload.get(key) for key in ('provider','base_url')}
    for step in steps:
        step['connection']=sources.get(step['id'])
        rules=store.one('SELECT snapshot_id FROM step_rules WHERE step_id=?',(step['id'],))
        step['rules_snapshot']=rules['snapshot_id'] if rules else None
        for key in ('inputs', 'output', 'usage'):
            step[key] = json.loads(step[key]) if step[key] else None
    return steps


def resolve(store, version_id):
    chain, seen = [], set()
    plan, steps, designs = None, [], {}
    fallback_plan = None
    while version_id and version_id not in seen:
        seen.add(version_id)
        version = store.one('SELECT * FROM versions WHERE id=?', (version_id,))
        if not version:
            break
        run = store.run(version['run_id'])
        if not run:
            break
        option = store.one('SELECT kind FROM run_options WHERE run_id=?', (run['id'],))
        duplicate = store.one("SELECT payload FROM events WHERE run_id=? AND kind='duplicated' ORDER BY id LIMIT 1", (run['id'],))
        kind = 'duplicate' if duplicate else option['kind'] if option else 'legacy'
        chain.append({'version_id': version_id, 'run_id': run['id'], 'project_id': version['project_id'], 'kind': kind})
        if run['plan']:
            fallback_plan = json.loads(run['plan'])
        if kind not in ('parameters', 'duplicate'):
            if plan is None:
                plan = fallback_plan
            current = decoded_steps(store, run['id'])
            for step in current:
                step['source_version'] = version_id
            steps.extend(current)
            for step in reversed(current):
                key = step['task_key']
                if step['status'] == 'succeeded' and key in ('tech', 'art', 'ux') and key not in designs:
                    designs[key] = {'id':step['id'],'role':step['role'],'task':key,'output':step['output'],
                                   'source_version':version_id,'source_run':step['run_id']}
            if len(designs)==3 or kind!='team8':
                break
        version_id = run['base_version'] or (json.loads(duplicate['payload']).get('source_version') if duplicate else None)
    # Earlier attempts can reference a design later replaced in this same run.
    # Include the transitive input closure even once all latest designs are found.
    included={step['id'] for step in steps}
    cursor=0
    while cursor<len(steps):
        for sid in steps[cursor]['inputs'] or []:
            if sid in included:
                continue
            included.add(sid)
            row=store.one('SELECT * FROM agent_steps WHERE id=?',(sid,))
            if not row:
                continue
            for key in ('inputs','output','usage'):
                row[key]=json.loads(row[key]) if row[key] else None
            source=store.one('SELECT id,project_id FROM versions WHERE run_id=?',(row['run_id'],))
            row['source_version']=source['id'] if source else None
            steps.append(row)
            if source and source['id'] not in seen:
                seen.add(source['id'])
                chain.append({'version_id':source['id'],'run_id':row['run_id'],'project_id':source['project_id'],'kind':'artifact_source'})
        cursor+=1
    return {'plan': plan or fallback_plan, 'designs': list(designs.values()), 'steps': steps, 'chain': chain}
