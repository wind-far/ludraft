"""Deterministic document protocol, not real model generation."""
import json
from studio.team_models import DocumentScope,DocumentBundle,DocumentReview
from testing_fixture import ReportGateway


class DocumentGateway(ReportGateway):
    async def call(self,role,prompt,schema):
        if schema not in (DocumentScope,DocumentBundle,DocumentReview):return await super().call(role,prompt,schema)
        self.trace.append((role,schema,prompt))
        context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0])
        if schema is DocumentScope:
            result=DocumentScope(title='三消玩法设计说明',summary='记录三消需求、规则方案与待验证内容。',documents=[{'id':'match3-design','title':'三消玩法与验收','sections':['需求依据','规则建议']}],acceptance=['区分需求与实现','引用可定位到来源','给出人工复核限制'])
        elif schema is DocumentBundle:
            source=context['sources']['requirement']['text'];quote=source.splitlines()[0].split(': ',1)[1]
            result=DocumentBundle(summary='根据需求编写三消文档',documents=[{'id':'match3-design','title':'三消玩法与验收','sections':[
                {'heading':'需求依据','kind':'fact','body':'用户本轮需求：'+quote,'citations':[{'source_id':'requirement','start':1,'end':1,'quote':quote}]},
                {'heading':'规则建议','kind':'proposal','body':'建议采用相邻交换、三连消除、下落补位与连锁。步数和目标分数需经试玩调整。','citations':[]}]}])
        else:result=DocumentReview(summary='陈述引用需求，建议明确标记；本例不声称规则已经实现。',accepted=True,issues=[],limitations=['人工复核规则完整性与表述准确性'])
        return result,{'model':'document-protocol-fixture','usage':{'total_tokens':10}}
