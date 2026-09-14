"""Fixed research protocol responses, never evidence of actual model research."""
import hashlib
import json
from studio.team_models import ResearchScope,ResearchResult,ResearchReview
from review_fixture import ReviewGateway

class ResearchGateway(ReviewGateway):
    async def call(self,role,prompt,schema):
        if schema not in (ResearchScope,ResearchResult,ResearchReview):return await super().call(role,prompt,schema)
        self.trace.append((role,schema,prompt));context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0])
        directions=[{'id':'classic','title':'经典三消','summary':'有限步数达成目标分数，突出易上手。'},{'id':'chain','title':'连锁挑战','summary':'更紧的步数目标，突出连锁规划。'}]
        if schema is ResearchScope:result=ResearchScope(title='三消方向调研',summary='比较经典三消与连锁挑战，形成下一步建议。',questions=[{'id':'goal','text':'现有需求支持哪些三消方向？'}],directions=directions,criteria=['可玩性','实现成本'],acceptance=['统一维度比较','区分事实与假设','给出待验证清单'])
        elif schema is ResearchResult:
            key=next((k for k in context['sources'] if k.startswith('web:')),'requirement')
            first=context['sources'][key]['text'].splitlines()[0];n,quote=first.split(': ',1)
            statement={'kind':'fact','text':'已读取来源表述：'+quote,'citations':[{'source_id':key,'start':int(n),'end':int(n),'quote':quote}]}
            hypothesis={'kind':'hypothesis','text':'预计经典方向更容易上手，需人工试玩验证。','citations':[]}
            result=ResearchResult(summary='固定协议比较演示，非真实市场调研结论。',answers=[{'question_id':'goal','statement':statement}],directions=[{**d,'assessments':[{'criterion':c,'statement':hypothesis} for c in ['可玩性','实现成本']],'next_steps':['先验证基础交互再调整难度']} for d in directions],recommendation='classic',rationale=hypothesis,backlog=[{'title':'验证基础规则','priority':'must','rationale':'先确保可玩','validation':'测试交换、连锁与胜负'}],unknowns=['真实玩家对难度的接受度'])
        else:result=ResearchReview(summary='已区分来源表述与待验证假设。',accepted=True,issues=[],limitations=['固定响应不代表真实调研质量'])
        return result,{'model':'research-protocol-fixture','usage':{'total_tokens':10}}

class FixturePages:
    def __init__(self):self.calls=[];self.fail=False
    async def fetch(self,url):
        self.calls.append(url)
        if self.fail:raise ValueError('固定协议：网页读取失败')
        text='三消设计参考：通过相邻交换形成三个同色目标。\n这是固定网页响应，仅用于协议测试。'
        return {'label':'三消来源协议','url':url,'final_url':url,'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'fetched_at':'2026-09-13T00:00:00Z','truncated':False}
