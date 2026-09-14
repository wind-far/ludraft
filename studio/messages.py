"""Durable run-scoped communication. Receipts prove inclusion, not resolution."""
import asyncio
from fastapi import HTTPException
from .db import ACTIVE, now, uid
from .models import UserMessage


class NeedsInput(Exception):
    pass


def revision(store,rid):
    return store.one("SELECT COALESCE(MAX(id),0) AS revision FROM events WHERE run_id=? AND kind IN ('replanning','input_required')",(rid,))['revision']


def check_revision(store,rid,expected):
    current=revision(store,rid)
    if current and expected!=current:raise HTTPException(409,'需求已更新，请刷新后确认最新玩法')


def pending(store, rid):
    return store.query("""SELECT m.* FROM messages m WHERE m.run_id=? AND m.kind='question'
        AND NOT EXISTS (SELECT 1 FROM messages a WHERE a.reply_to=m.id) ORDER BY m.rowid""", (rid,))


def add(store, rid, sender, recipient, kind, content, reply_to=None, source_step=None, slot=None):
    content=content.strip()
    if not content:raise ValueError('消息内容不能为空')
    if source_step:
        existing=store.one('SELECT id FROM messages WHERE source_step=? AND slot=?',(source_step,slot))
        if existing:return existing['id']
    if kind!='answer' and store.one("SELECT COUNT(*) AS n FROM messages WHERE run_id=? AND kind!='answer'",(rid,))['n']>=100:
        raise ValueError('单次任务消息已达 100 条，请结束本轮后新建修改任务')
    mid=uid()
    store.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)',
        (mid,rid,sender,recipient,kind,content,reply_to,source_step,slot,now()))
    store.event(rid,sender,'message_sent',message=content,message_id=mid,recipient=recipient,message_kind=kind)
    return mid


def inbox(store,rid,role,sid):
    # Read only when the model slot is acquired: queued calls see intervening messages.
    rows=store.query("SELECT * FROM messages WHERE run_id=? AND (recipient=? OR recipient='all') ORDER BY rowid",(rid,role))
    for row in rows:
        store.execute('INSERT OR IGNORE INTO message_receipts VALUES(?,?,?)',(row['id'],sid,now()))
    if rows:store.event(rid,role,'messages_included',message=f'{len(rows)} 条消息已送入本次模型上下文',
        step_id=sid,message_ids=[r['id'] for r in rows])
    result=[{k:r[k] for k in ('id','sender','recipient','kind','content','reply_to')} for r in rows]
    for item in result:
        if item['reply_to']:
            item['question']=store.one('SELECT sender,content FROM messages WHERE id=? AND run_id=?',(item['reply_to'],rid))
    return result


def history(store,rid):
    rows=store.query('SELECT * FROM messages WHERE run_id=? ORDER BY rowid',(rid,))
    for row in rows:
        row['receipts']=store.query('''SELECT r.step_id,r.created_at,s.role,s.task_key,s.status
            FROM message_receipts r JOIN agent_steps s ON s.id=r.step_id WHERE r.message_id=? ORDER BY r.created_at''',(row['id'],))
        row['answered']=any(m['reply_to']==row['id'] for m in rows)
    return rows


def register(app,store,workflow,run,writable):
    @app.get('/api/runs/{rid}/messages')
    async def messages(rid:str):
        r=run(rid)
        return {'messages':history(store,rid),'status':r['status'],'pending_questions':[m['id'] for m in pending(store,rid)]}

    @app.post('/api/runs/{rid}/messages',status_code=201)
    async def send(rid:str,req:UserMessage):
        async with workflow.control(rid):
            r=run(rid);writable(r['project_id'])
            if r['status'] not in ACTIVE:raise HTTPException(409,'任务已结束，请新建修改任务')
            mode=store.one('SELECT kind FROM run_options WHERE run_id=?',(rid,))
            if not mode or mode['kind']!='team8':raise HTTPException(409,'只有八角色任务支持中途消息')
            questions=pending(store,rid)
            if req.reply_to:
                if r['status']!='waiting_confirmation' or not any(q['id']==req.reply_to for q in questions):
                    raise HTTPException(409,'问题不属于本轮待答复列表，或已被答复')
            elif questions:raise HTTPException(409,'请先答复待澄清的问题')
            try:
                mid=add(store,rid,'user','all','answer' if req.reply_to else 'feedback',req.content,req.reply_to)
            except ValueError as exc:raise HTTPException(400,str(exc)) from None
            # Immediately invalidate approval; interruption joins every sibling and runner.
            store.execute("UPDATE runs SET status='waiting_confirmation',plan=NULL,error=NULL WHERE id=?",(rid,))
            workflow.paused.add(rid)
            try:
                task=workflow.tasks.get(rid)
                if task and not task.done():
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
            finally:workflow.paused.discard(rid)
            if not pending(store,rid):
                store.execute("UPDATE runs SET status='queued',finished_at=NULL WHERE id=?",(rid,))
                store.event(rid,'user','replanning',message='已收到补充内容，旧审批失效；重新策划后需要再次确认')
                workflow.launch(rid,'plan')
            return {'message_id':mid,'status':store.run(rid)['status']}
