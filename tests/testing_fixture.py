"""Fixed report protocol for tests; never claims real model output."""
from studio.team_models import TestScope as Scope
from match3_fixture import Match3Gateway
from test_workbench import ParameterRunner
from studio.test_flow import required_checks

class ReportGateway(Match3Gateway):
    async def call(self,role,prompt,schema):
        if schema is Scope:
            self.trace.append((role,schema,prompt))
            return Scope(summary='验证三消现有版本的核心交互并保留报告。',focus=['无效交换和连锁','胜负和重开'],
                acceptance=['完整运行固定检查','报告逐项记录证据','不改变可玩版本'],manual_checks=['人工体验关卡难度']),{'model':'report-protocol-fixture','usage':{'total_tokens':10}}
        return await super().call(role,prompt,schema)

class EvidenceRunner(ParameterRunner):
    async def run(self,path,rid):
        e=await super().run(path,rid)
        e['checks']=[{'name':name,'passed':self.passed} for name in required_checks(e['config']['mode'])]
        return e
