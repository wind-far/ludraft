"""Fixed configuration responses; only used by tests."""
import json
from studio.models import Changes,Match3Parameters,Parameters
from studio.team_models import ConfigProposal
from studio.parameters import read_config,update_config
from match3_fixture import Match3Gateway

class ConfigGateway(Match3Gateway):
    moves=30
    target=1500
    fault=None
    async def call(self,role,prompt,schema):
        context=json.loads(prompt.split('本步骤上下文：',1)[1].split('\n依赖交付物：',1)[0]) if '本步骤上下文：' in prompt else {}
        if schema is ConfigProposal:
            current=read_config(context['files']['src/config.ts'])
            cls=Match3Parameters if current['mode']=='match3' else Parameters
            params={k:current[k] for k in cls.model_fields}
            if cls is Match3Parameters:params.update(moves=self.moves,targetScore=self.target)
            else:params.update(speed=180)
            result=ConfigProposal(summary='调整关卡参数，保留原有游戏规则。',parameters=cls(**params),acceptance=['实际参数一致','有效消除规则保留','开始和重开正常'])
        elif schema is Changes and 'approved_parameters' in context:
            cls=Match3Parameters if 'moves' in context['approved_parameters'] else Parameters
            content,_=update_config(context['files']['src/config.ts'],cls(**context['approved_parameters']))
            if self.fault=='wrong_value':content=content.replace('"moves": 30','"moves": 40')
            if self.fault=='wrong_title':content=content.replace('"title":','"title": "Changed", "duplicate":')
            if self.fault=='dynamic':content=content.replace('"moves": 30','"moves": Math.random()')
            path='src/game.ts' if self.fault=='wrong_file' else 'src/config.ts'
            result=Changes(summary='固定配置响应，非真实模型',files=[{'path':path,'content':content}])
        else:return await super().call(role,prompt,schema)
        self.trace.append((role,schema,prompt))
        return result,{'model':'config-protocol-fixture','usage':{'total_tokens':10}}
