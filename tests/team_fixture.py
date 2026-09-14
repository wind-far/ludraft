"""Deterministic protocol responses for tests only, never used by production."""
from studio.models import Plan, Changes
from studio.team_models import Brief, TaskBoard, Design, Review, TestStrategy, QAReport, Delivery, CodingPlan
from studio.files import TEMPLATE

BOARD={'summary':'固定测试任务板','tasks':[
    {'key':key,'goal':'完成'+key,'depends_on':deps,'acceptance':['交付可检查成果']}
    for key,deps in [('tech',[]),('art',[]),('ux',[]),('code',['tech','art','ux']),('qa',['code'])]
]}

class TeamGateway:
    def __init__(self):self.trace=[];self.phase=0
    def public(self):return {'model':'team-protocol-fixture','has_key':False,'base_url':'http://localhost'}
    async def call(self,role,prompt,schema):
        self.trace.append((role,schema,prompt))
        if schema is Brief:result=Brief(summary='明确固定模板范围',scope=['接金币躲炸弹'],constraints=['固定 Canvas 模板'],risks=['人工验收玩法'])
        elif schema is TaskBoard:result=TaskBoard.model_validate(BOARD)
        elif schema is Plan:result=Plan(title='八角色测试作品',summary='接金币躲炸弹，验证协作交付。',mode='collector',controls='方向键移动',acceptance=['开始与移动','金币加分','炸弹扣命'])
        elif schema is Design:result=Design(summary=role+'设计交付',decisions=['保留固定模板接口，明确职责'],acceptance=['与已确认玩法一致'])
        elif schema is CodingPlan:result=CodingPlan(summary='固定测试编码任务',tasks=[{'id':'implementation','goal':'实现确认玩法','files':['src/config.ts','src/game.ts','style.css'],'depends_on':[],'acceptance':['满足确认玩法']}])
        elif schema is Changes:
            content=(TEMPLATE/'src/config.ts').read_text()
            if self.phase==1:content=content.replace('speed: 320','speed: 180').replace('lives: 3','lives: 5')
            if self.phase==2:content='export const config = ; // failure fixture'
            result=Changes(summary='固定响应代码交付，非模型生成',files=[{'path':'src/config.ts','content':content}])
        elif schema is Review:result=Review(summary='固定审查响应',issues=[])
        elif schema is TestStrategy:result=TestStrategy(summary='关注核心交互',focus=['移动与计分'],manual_checks=['人工评价趣味性'])
        elif schema is QAReport:result=QAReport(summary='固定证据分析响应',issues=[],manual_checks=['人工评价趣味性'])
        elif schema is Delivery:result=Delivery(summary='固定交付摘要',ready=True,limitations=['测试固定响应，不代表模型质量'])
        else:raise AssertionError(schema)
        return result,{'model':'team-protocol-fixture','usage':{'total_tokens':12}}
