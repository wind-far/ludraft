import asyncio
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.models import Match3Parameters,Parameters
from studio.files import MATCH3,game_source
from studio.parameters import read_config,update_config
from studio.workflow import Workflow
from test_team import setup,approve
from test_workbench import ParameterRunner,wait
from match3_fixture import Match3Gateway


def test_match3_parameters_are_separate_and_literal():
    source=(MATCH3/'src/config.ts').read_text();values=read_config(source)
    p=Match3Parameters(**{k:values[k] for k in Match3Parameters.model_fields}).model_copy(update={'moves':30})
    updated,before=update_config(source,p)
    assert before['moves']==20 and read_config(updated)['moves']==30
    with pytest.raises(ValueError):read_config(source.replace('moves: 20','moves: 2'))
    with pytest.raises(ValueError):read_config(source.replace('gemTypes: 6','gemTypes: 7'))
    with pytest.raises(ValueError):read_config(source.replace('moves: 20','moves: Math.random()'))


def test_match3_engine_seeded_behavior(tmp_path):
    compiler=Path(__file__).resolve().parents[1]/'frontend/node_modules/.bin/tsc'
    assert compiler.exists(),'Install frontend dependencies before testing'
    subprocess.run([str(compiler),'-p',str(MATCH3/'tsconfig.json'),'--outDir',str(tmp_path)],check=True,capture_output=True,text=True)
    result=subprocess.run([shutil.which('node'),str(Path(__file__).with_name('match3-engine.mjs')),str(tmp_path)],check=True,capture_output=True,text=True)
    assert '90 seeded games' in result.stdout


def test_match3_team_source_and_parameter_api(tmp_path):
    s,w,pid,rid=setup(tmp_path,Match3Gateway(),ParameterRunner());asyncio.run(approve(w,rid))
    assert s.run(rid)['status']=='succeeded',s.run(rid)
    version=s.one('SELECT * FROM versions');assert json.loads(version['evidence'])['config']['mode']=='match3'
    assert '三消棋盘' in (Path(version['path'])/'index.html').read_text()
    assert 'match3' in w.contract_for(s.run(rid))
    s.con.close()
    with TestClient(create_app(tmp_path,Match3Gateway(),ParameterRunner())) as c:
        values=c.get('/api/versions/'+version['id']).json()['parameters']
        params={k:values[k] for k in Match3Parameters.model_fields};params['moves']=30;params['targetScore']=1000
        r=c.post('/api/projects/'+pid+'/parameters',json={'base_version':version['id'],'parameters':params})
        assert r.status_code==201,r.text
        assert wait(c,r.json()['run_id'])['status']=='succeeded'
        p=c.get('/api/projects/'+pid).json();v=c.get('/api/versions/'+p['active_version']).json()
        assert v['parameters']['moves']==30 and v['evidence']['parameter_match']
        assert 'lives' not in v['parameters']
