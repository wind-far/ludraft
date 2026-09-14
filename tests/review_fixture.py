"""Deterministic audit responses; findings are fixture scenarios, not real defects."""
import json
from studio.team_models import ReviewScope,CodeAudit,AuditResponse,AuditVerdict
from document_fixture import DocumentGateway

class ReviewGateway(DocumentGateway):
    include_finding=True
    decision='confirmed'
    async def call(self,role,prompt,schema):
        if schema not in (ReviewScope,CodeAudit,AuditResponse,AuditVerdict):return await super().call(role,prompt,schema)
        self.trace.append((role,schema,prompt))
        context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0])
        source=context['sources']['file:src/game.ts']['text'];line=next(line for line in source.splitlines() if line.split(': ',1)[1].strip())
        n,quote=line.split(': ',1);citation={'source_id':'file:src/game.ts','start':int(n),'end':int(n),'quote':quote}
        if schema is ReviewScope:result=ReviewScope(summary='静态审查三消逻辑，核对边界与状态。',files=['src/game.ts'],focus=['相邻交换与结算状态'],acceptance=['逐文件记录审查覆盖','问题均有可定位引用','程序回应并由主程复核'])
        elif schema is CodeAudit:result=CodeAudit(summary='固定审查协议演示，不代表真实缺陷。',coverage=[{'path':'src/game.ts','summary':'检查三消逻辑的固定响应','citations':[citation]}],findings=[{'id':'fixture-issue','title':'三消边界复核演示','severity':'blocking','description':'固定协议场景：需人工复核边界；非真实缺陷结论。','impact':'用于验证发现问题后的回应和修复交接','recommendation':'根据实际需求复核规则，不凭此固定记录改代码','citations':[citation]}] if self.include_finding else [],limitations=['本测试使用固定响应，需真实模型与人工复核'])
        elif schema is AuditResponse:result=AuditResponse(summary='程序逐项回应',responses=[{'finding_id':'fixture-issue','position':'agree','reason':'固定协议回应，保留待核对项','suggestion':'交由后续任务核对，不在本轮修改','citations':[citation]}] if self.include_finding else [])
        else:result=AuditVerdict(summary='审查报告结构完整，问题尚未修复。',accepted=True,decisions=[{'finding_id':'fixture-issue','decision':self.decision,'reason':'保留固定协议场景的结论','citations':[citation]}] if self.include_finding else [],limitations=['报告完成不代表代码通过测试'])
        return result,{'model':'review-protocol-fixture','usage':{'total_tokens':10}}
