"""Real disconnected CLI container, scoped relay, fixed replies and cancellation."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from scripts.verify_opengame_proxy import FixtureProvider
from studio.budget import BudgetLedger, connection_key
from studio.db import Store, uid
from studio.files import copy_source
from studio.opengame_executor import OpenGameExecutor, create_args, docker, verified_image
from studio.opengame_proxy import ModelProxy
from studio.opengame_tools import CandidateTools, TOOL_MODELS
from studio.project_files import source_digest
from studio.runner import Runner

CONFIG = {'provider':'openai','base_url':'https://fixture.invalid/v1','model':'ludraft-fixture',
          'api_key':'backend-fixture-key','max_tokens':12000}

PROBE = r"""
const fs=require('node:fs'),os=require('node:os'),net=require('node:net');
(async()=>{
 const checks={nonroot:process.getuid()===1000, noHostDirectories:!fs.existsSync('/Users')&&!fs.existsSync('/workspace'),
 noDockerSocket:!fs.existsSync('/var/run/docker.sock'), onlyLoopback:Object.keys(os.networkInterfaces()).every(k=>k==='lo'),
 capabilitiesDropped:/CapEff:\s+0000000000000000/.test(fs.readFileSync('/proc/self/status','utf8')),
 noNewPrivileges:/NoNewPrivs:\s+1/.test(fs.readFileSync('/proc/self/status','utf8')),
 rootReadOnly:fs.readFileSync('/proc/mounts','utf8').split('\n').some(line=>{const p=line.split(' ');return p[1]==='/'&&p[3].split(',').includes('ro')}),
 noProviderEnvironment:!process.env.OPENAI_API_KEY&&!process.env.STUDIO_API_KEY};
 fs.writeFileSync('/tmp/write-probe','ok');checks.temporaryDirectoryWritable=fs.readFileSync('/tmp/write-probe','utf8')==='ok';
 const connection=await new Promise(resolve=>{const s=new net.Socket();s.setTimeout(1000);s.once('connect',()=>{s.destroy();resolve('connected')});s.once('error',e=>{s.destroy();resolve(e.code)});s.once('timeout',()=>{s.destroy();resolve('timeout')});s.connect(443,'1.1.1.1')});
 checks.externalConnectionBlocked=connection!=='connected';
 console.log(JSON.stringify({checks,connection,node:process.version,arch:process.arch,passed:Object.values(checks).every(Boolean)}));
 process.exit(Object.values(checks).every(Boolean)?0:1);
})().catch(()=>process.exit(1));
"""


def resources(root, transport):
    session = CandidateTools(root, writable_paths={'src/config.ts'})
    ledger = BudgetLedger(root.parent / (root.name + '-fixture-budget'))
    ledger.configure('100')
    ledger.set_price(connection_key(CONFIG),'1','2','synthetic protocol rates; no paid provider')
    proxy = ModelProxy(CONFIG, ledger, allowed_tools=TOOL_MODELS, deadline=session.deadline,
                       active=session.active, transport=transport)
    return session, proxy


async def isolation_probe(image):
    name = 'gamedev-opengame-probe-' + uid()
    args = create_args(image,name)
    args[-1:-1] = ['--entrypoint','node']
    try:
        await docker(*args,'-e',PROBE)
        raw = json.loads(await docker('inspect',name))[0]
        host = raw['HostConfig']
        profile = {'network':host['NetworkMode'],'readonly':host['ReadonlyRootfs'],'privileged':host['Privileged'],
                   'cap_drop':host['CapDrop'],'security_options':host['SecurityOpt'],'mount_count':len(raw['Mounts']),
                   'memory':host['Memory'],'pids_limit':host['PidsLimit'],'user':raw['Config']['User']}
        value = json.loads(await docker('start','-a',name,timeout=20))
        value['container_profile']=profile
        assert profile['network']=='none' and profile['readonly'] and not profile['privileged'] and profile['mount_count']==0
        assert value['passed']
        return value
    finally:
        await docker('rm','-f',name)


async def cancellation_probe(root, *, during_build=False):
    started = asyncio.Event()
    async def stalled(request):
        started.set()
        await asyncio.Event().wait()
    def request_build(request):
        data=json.loads(request.content)
        chunks=[{'id':'build-cancel-fixture','object':'chat.completion.chunk','created':1,'model':data['model'],
                 'choices':[{'index':0,'delta':{'role':'assistant','tool_calls':[{'index':0,'id':'build-fixture',
                    'type':'function','function':{'name':'project_verify','arguments':json.dumps({'base_digest':source_digest(root)})}}]},'finish_reason':None}]},
                {'id':'build-cancel-fixture','object':'chat.completion.chunk','created':1,'model':data['model'],
                 'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls'}]},
                {'id':'build-cancel-fixture','object':'chat.completion.chunk','created':1,'model':data['model'],
                 'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        body=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
        return httpx.Response(200,content=body.encode(),headers={'Content-Type':'text/event-stream'})

    class ObservedRunner(Runner):
        async def _execute(self, staged, run_id):
            self.container_name='gamedev-'+run_id
            started.set()
            return await super()._execute(staged,run_id)

    session, proxy = resources(root,httpx.MockTransport(request_build if during_build else stalled))
    if during_build:session.runner=ObservedRunner()
    execution_store = Store(root.parent / (root.name + '-executions'))
    engine = OpenGameExecutor(execution_store)
    running = asyncio.create_task(engine.run(session,proxy,'Fixed cancellation protocol test.'))
    observed = asyncio.create_task(started.wait())
    try:
        done,_=await asyncio.wait({running,observed},timeout=60,return_when=asyncio.FIRST_COMPLETED)
        if observed not in done:
            if running in done:await running
            raise RuntimeError('CLI did not reach the held model request')
        name=engine.container_name
        info=json.loads(await docker('inspect',name))[0]
        assert info['State']['Running'] is True
        build_name=None
        if during_build:
            for _ in range(100):
                builds = engine.records.store.query("SELECT container_name FROM executor_attempts WHERE kind='build' ORDER BY created_at DESC LIMIT 1")
                build_name = builds[0]['container_name'] if builds else None
                if build_name and (await docker('ps','-q','--filter','name=^/'+build_name+'$')).strip():break
                if running.done():await running;raise RuntimeError('Build ended before cancellation probe')
                await asyncio.sleep(0.05)
            else:raise RuntimeError('Build container was not observed running')
        before=time.monotonic();running.cancel()
        try:
            await running
            raise AssertionError('Executor ignored cancellation')
        except asyncio.CancelledError:
            pass
        remaining=await docker('ps','-aq','--filter','name=^/'+name+'$')
        assert not remaining.strip() and session.closed and proxy.closed and not engine.cleanup_errors
        if build_name:
            assert not (await docker('ps','-aq','--filter','name=^/'+build_name+'$')).strip()
        ledger=proxy.ledger.summary()
        assert ledger['calls']==1 and ledger['unsettled_calls']==(0 if during_build else 1)
        if not during_build:assert ledger['held_cny']>0
        execution = engine.records.summary()
        assert execution['can_start'] and execution['attempts'][0]['state'] == 'cancelled'
        return {'passed':True,'running_container_observed':True,'removed':True,
                'build_container_observed_and_removed':bool(build_name),
                'seconds':round(time.monotonic()-before,3),'fixture_ledger':ledger,
                'durable_execution':execution}
    finally:
        observed.cancel()
        if not running.done():running.cancel()
        await asyncio.gather(running,observed,return_exceptions=True)
        execution_store.con.close()


async def verify(args):
    run=args.output.resolve()/uid();run.mkdir(parents=True)
    record={'passed':False,'scope':'disconnected-cli-fixed-response-integration','workspace':str(run),
            'live_model_verified':False,'gameplay_verified':False,'paid_model_calls':0,'image_calls':0}
    execution_store = Store(run / 'executions')
    try:
        image=await verified_image();record['image_id']=image
        record['isolation']=await isolation_probe(image)
        root=run/'candidate';copy_source(ROOT/'templates/phaser/tower_defense',root)
        fixture=FixtureProvider(root)
        session,proxy=resources(root,httpx.MockTransport(fixture.respond))
        engine=OpenGameExecutor(execution_store)
        record['execution']=await engine.run(session,proxy,'Run the fixed protocol exercise through the available project tools.')
        record.update(fixture_steps=fixture.steps,exposed_tools=fixture.tool_names,
                      diagnostics=fixture.diagnostics,fixture_ledger=proxy.ledger.summary())
        assert record['execution']['execution_completed'] and len(fixture.steps)==7 and session.diagnostics==2
        record['durable_execution'] = engine.records.summary()
        assert record['durable_execution']['can_start']
        assert record['durable_execution']['attempts'][0]['state'] == 'succeeded'
        assert not (await docker('ps','-aq','--filter','name=^/'+engine.last_container_name+'$')).strip()
        cancel_root=run/'cancel-candidate';copy_source(ROOT/'templates/phaser/tower_defense',cancel_root)
        record['cancellation']=await cancellation_probe(cancel_root)
        build_cancel_root=run/'build-cancel-candidate';copy_source(ROOT/'templates/phaser/tower_defense',build_cancel_root)
        record['build_cancellation']=await cancellation_probe(build_cancel_root,during_build=True)
        record['passed']=True
    except Exception as exc:
        record['error']=str(exc)[:1000]
    finally:
        (run/'container-integration.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        execution_store.con.close()
    print(json.dumps({k:v for k,v in record.items() if k!='diagnostics'},ensure_ascii=False,indent=2))
    return 0 if record['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.studio/opengame-container-integration')
    raise SystemExit(asyncio.run(verify(parser.parse_args())))
