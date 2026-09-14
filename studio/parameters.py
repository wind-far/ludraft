"""A deliberately restricted literal parser; never evaluate generated TypeScript."""
import ast
import json
import re
from .models import Parameters, Match3Parameters

ERROR = '当前 config.ts 含动态表达式或自定义结构，无法安全调参。请通过自然语言修改。'
FIELD = re.compile(r'''\s*(?:([A-Za-z]\w*)|"([A-Za-z]\w*)")\s*:\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|-?\d+(?:\.\d+)?)(?:\s+as\s+(?:const|"collector"\s*\|\s*"dodger"\s*\|\s*"clicker"))?\s*(?:,|$)''')


def read_config(source):
    match = re.fullmatch(r'\s*export\s+const\s+config\s*=\s*\{(.*)\}\s*(?:as\s+const\s*)?;?\s*', source, re.S)
    if not match:
        raise ValueError(ERROR)
    content, cursor, values = match[1].strip(), 0, {}
    while cursor < len(content):
        field = FIELD.match(content, cursor)
        if not field:
            raise ValueError(ERROR)
        key = field[1] or field[2]
        if key in values:
            raise ValueError(ERROR)
        values[key] = ast.literal_eval(field[3])
        cursor = field.end()
    model = Match3Parameters if values.get('mode')=='match3' else Parameters
    if set(values) != set(model.model_fields) | {'title', 'mode'}:
        raise ValueError(ERROR)
    if not isinstance(values['title'], str) or values['mode'] not in ('collector', 'dodger', 'clicker', 'match3'):
        raise ValueError(ERROR)
    model.model_validate({k: values[k] for k in model.model_fields})
    return values


def update_config(source, parameters):
    config = read_config(source)
    model = Match3Parameters if config['mode']=='match3' else Parameters
    if not isinstance(parameters,model):raise ValueError('参数结构与游戏模式不匹配')
    before = {k: config[k] for k in model.model_fields}
    config.update(parameters.model_dump())
    body = json.dumps(config, ensure_ascii=False, indent=2)
    body = body.replace('"mode": ' + json.dumps(config['mode']),
                        '"mode": ' + json.dumps(config['mode']) + (' as const' if config['mode']=='match3' else ' as "collector" | "dodger" | "clicker"'))
    return 'export const config = ' + body + ';\n', before
