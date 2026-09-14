"""Exercise the real ASGI SSE endpoint, including middleware and disconnect cleanup."""
import asyncio
import json
import pytest
from studio.app import create_app
from test_studio import FakeGateway,FakeRunner,create_run

class Stream:
    def __init__(self,app,rid,headers=(),query=b''):
        self.app=app;self.rid=rid;self.headers=headers;self.query=query
        self.closed=asyncio.Event();self.messages=asyncio.Queue();self.initial=True
    async def __aenter__(self):
        async def receive():
            if self.initial:self.initial=False;return {'type':'http.request','body':b'','more_body':False}
            await self.closed.wait();return {'type':'http.disconnect'}
        async def send(message):await self.messages.put(message)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET','scheme':'http',
            'path':f'/api/runs/{self.rid}/events','raw_path':f'/api/runs/{self.rid}/events'.encode(),
            'query_string':self.query,'root_path':'','headers':[(b'host',b'testserver'),*self.headers],
            'client':('127.0.0.1',1234),'server':('testserver',80)}
        self.task=asyncio.create_task(self.app(scope,receive,send))
        self.start=await asyncio.wait_for(self.messages.get(),3)
        return self
    async def event(self):
        while True:
            message=await asyncio.wait_for(self.messages.get(),3)
            body=message.get('body',b'').decode()
            if body.startswith('id:'):
                lines=body.strip().splitlines()
                return int(lines[0][4:]),json.loads(lines[1][6:])
    async def heartbeat(self):
        while True:
            message=await asyncio.wait_for(self.messages.get(),3)
            if message.get('body',b'').startswith(b': heartbeat'):return
    async def __aexit__(self,*args):
        self.closed.set()
        try:await asyncio.wait_for(self.task,3)
        finally:
            if not self.task.done():self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)

@pytest.mark.asyncio
async def test_reconnect_live_events_scope_and_restart(tmp_path):
    app=create_app(tmp_path,FakeGateway(),FakeRunner());s=app.state.store
    _,rid=create_run(s);_,other=create_run(s)
    for r in (rid,other):s.execute("UPDATE runs SET status='succeeded' WHERE id=?",(r,))
    s.event(rid,'制作人','first',message='第一条')
    first=s.one('SELECT MAX(id) AS id FROM events')['id']
    s.event(other,'QA','foreign',message='不应串入另一任务')
    s.event(rid,'PM','second',message='第二条')
    second=s.one('SELECT MAX(id) AS id FROM events')['id']
    async with Stream(app,rid) as stream:
        assert stream.start['status']==200
        assert b'text/event-stream' in dict(stream.start['headers'])[b'content-type']
        assert (await stream.event())[0]==first
        assert (await stream.event())[0]==second
        await stream.heartbeat()
        s.event(rid,'QA','third',message='订阅之后实时产生')
        third,data=await stream.event();assert data['kind']=='third' and data['run_id']==rid
    async with Stream(app,rid,headers=[(b'last-event-id',str(second).encode())]) as stream:
        ident,data=await stream.event();assert ident==third and data['kind']=='third'
        await stream.heartbeat()
    # Store is closed and reopened: event IDs and cursor semantics remain stable.
    s.con.close();app=create_app(tmp_path,FakeGateway(),FakeRunner());s=app.state.store
    s.event(rid,'user','fourth',message='重启之后')
    async with Stream(app,rid,headers=[(b'last-event-id',str(first).encode())],query=f'after={third}'.encode()) as stream:
        ident,data=await stream.event();assert ident>third and data['kind']=='fourth'
    s.con.close()

@pytest.mark.asyncio
async def test_bad_cursor_and_unknown_run_fail_without_hanging(tmp_path):
    app=create_app(tmp_path,FakeGateway(),FakeRunner());_,rid=create_run(app.state.store)
    async with Stream(app,rid,headers=[(b'last-event-id',b'not-an-integer')]) as stream:assert stream.start['status']==400
    async with Stream(app,'missing') as stream:assert stream.start['status']==404
    app.state.store.con.close()
