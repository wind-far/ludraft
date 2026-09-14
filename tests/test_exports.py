import io
import json
import zipfile
from fastapi.testclient import TestClient
from studio.app import create_app
from test_studio import FakeGateway
from test_workbench import seed,ParameterRunner


def test_every_game_export_has_standalone_instructions_and_license(tmp_path):
    with TestClient(create_app(tmp_path,FakeGateway(),ParameterRunner())) as c:
        _,_,vid,_=seed(c.app.state.store)
        result=c.get('/api/versions/'+vid+'/export')
        assert result.status_code==200
        with zipfile.ZipFile(io.BytesIO(result.content)) as z:
            assert {'RUN_GAME.md','licenses/upstream-MIT.txt','dist/main.js','index.html','verification.json'}<=set(z.namelist())
            assert len(z.namelist())==len(set(z.namelist()))
            guide=z.read('RUN_GAME.md').decode()
            assert '--bind 127.0.0.1' in guide and '不需要启动游芽工作台' in guide
            assert 'LinHao-city' in z.read('licenses/upstream-MIT.txt').decode()
