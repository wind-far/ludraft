"""Fixed protocol responses for match3 integration; never real model evidence."""
import json
from studio.models import Plan,Changes
from studio.team_models import CodingPlan
from team_fixture import TeamGateway

class Match3Gateway(TeamGateway):
    async def call(self,role,prompt,schema):
        meta={'model':'match3-protocol-fixture','usage':{'total_tokens':10}}
        if schema is Plan:
            return Plan(title='三消协议测试',summary='交换相邻宝石消除三连，在有限步数内达到目标，支持连锁和重开。',mode='match3',controls='点击或滑动交换相邻宝石',acceptance=['无效交换回退且不扣步','消除后下落补位与连锁','步数耗尽或目标达成后结束']),meta
        if schema is CodingPlan:
            return CodingPlan(summary='主程拆分参数和视觉任务',tasks=[{'id':'parameters','goal':'实现三消关卡参数','files':['src/config.ts'],'depends_on':[],'acceptance':['符合确认目标']},{'id':'visual','goal':'实现三消主题','files':['style.css'],'depends_on':[],'acceptance':['主题可见']}]),meta
        if schema is Changes:
            context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0]);task=context['coding_task']
            files=[{'path':p,'content':context['files'][p]} for p in task['files']]
            if self.phase==1:
                for f in files:
                    if f['path']=='src/config.ts':f['content']=f['content'].replace('moves: 20','moves: 25')
            return Changes(summary='固定三消文件响应，非模型生成',files=files),meta
        return await super().call(role,prompt,schema)
