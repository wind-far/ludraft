import asyncio
from pathlib import Path
import pytest
from studio.runner import Runner

@pytest.mark.asyncio
async def test_runner_enforces_isolation_and_cleans_cancelled_container(tmp_path,monkeypatch):
    invocations=[];running=asyncio.Event();cleaned=asyncio.Event()
    class Process:
        def __init__(self,args):self.args=args;self.returncode=None
        async def communicate(self):
            running.set();await asyncio.Event().wait()
        async def wait(self):self.returncode=0;return 0
        def terminate(self):self.returncode=-15
    async def spawn(*args,**kwargs):
        invocations.append(args)
        if args[:3]==('docker','rm','-f'):cleaned.set()
        return Process(args)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
    task=asyncio.create_task(Runner().run(tmp_path,'test-run'))
    await running.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert cleaned.is_set()
    command=invocations[0]
    for option,value in [('--network','none'),('--cap-drop','ALL'),('--security-opt','no-new-privileges'),('--memory','768m'),('--pids-limit','128')]:
        assert command[command.index(option)+1]==value
    assert '--read-only' in command
    assert '--privileged' not in command
    assert len([x for x in command if x=='--mount'])==1
    assert not any('API_KEY' in x or 'docker.sock' in x for x in command)
