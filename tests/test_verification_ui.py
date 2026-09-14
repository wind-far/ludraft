"""Render the actual React report against malformed and contradictory tool output."""
import subprocess
from pathlib import Path


def test_results_component_reports_failures_without_crashing(tmp_path):
    root=Path(__file__).resolve().parents[1]
    script=tmp_path/'check.cjs'
    script.write_text(r'''
const assert = require('node:assert/strict');
const path = require('node:path');
const root = process.argv[2];
const esbuild = require(path.join(root, 'frontend/node_modules/esbuild'));
const React = require(path.join(root, 'frontend/node_modules/react'));
const { renderToStaticMarkup } = require(path.join(root, 'frontend/node_modules/react-dom/server'));
const result = esbuild.buildSync({entryPoints:[path.join(root,'frontend/src/WorkbenchPanels.tsx')],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime']});
const output = {exports:{}};
new Function('require','module','exports',result.outputFiles[0].text)(id=>require(path.join(root,'frontend/node_modules',id)),output,output.exports);
const render = evidence => renderToStaticMarkup(React.createElement(output.exports.TestResults,{evidence,pending:false,label:'回归测试'}));
const names=['TypeScript 构建','三消参数边界','开始游戏','棋盘初始可玩','无效交换回退','禁止跨格交换','结算期间禁止重复操作','真实交换消除与步数','下落补位与连锁','无解棋盘重排','目标达成与失败','重新开始','无浏览器异常'];
const complete={passed:true,build:true,exit_code:0,expected_mode:'match3',config:{mode:'match3'},checks:names.map(name=>({name,passed:true}))};
assert.match(render(complete),/核心验证通过/);
assert.match(render(complete),/13 \/ 13/);
assert.match(render({...complete,checks:complete.checks.slice(0,1)}),/验证未通过/);
const broken={...complete,checks:[null,{name:[],passed:true},{name:'TypeScript 构建',passed:true},{name:'TypeScript 构建',passed:false}],error:{reason:'格式异常'},console_errors:'浏览器报错',gate_errors:['缺少交互证据'],log:{output:'中断'}};
const html=render(broken);
assert.match(html,/验证门禁未通过/);
assert.match(html,/缺少交互证据/);
assert.match(html,/0 \/ 13/);
assert.match(html,/格式异常/);
assert.doesNotMatch(html,/核心验证通过/);
assert.match(render({...complete,exit_code:2}),/验证未通过/);
assert.match(render({...complete,checks:complete.checks.map(c=>({...c,passed:'true'}))}),/0 \/ 13/);
console.log('actual React report: complete, missing, malformed, duplicate, exit and boolean cases passed');
''')
    result=subprocess.run(['node',str(script),str(root)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
