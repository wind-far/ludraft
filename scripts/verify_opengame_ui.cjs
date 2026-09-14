// Real local UI/API checks. Start an isolated workbench; never use paid test buttons.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
  const scenario=process.argv[2]||'empty',out=path.resolve(process.argv[3]);
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
  const errors=[],calls=[],checks={};
  try{
    const page=await browser.newPage({viewport:{width:1280,height:900}});
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',req=>{if(req.url().includes('/api/'))calls.push({url:new URL(req.url()).pathname,method:req.method()});});
    await page.goto('http://127.0.0.1:8080');
    await page.getByRole('dialog',{name:'给创意，做好准备。'}).waitFor();
    await page.getByText('OpenGame 执行与预算',{exact:true}).click();
    const panel=page.getByRole('region',{name:'OpenGame 执行状态'});
    await panel.getByText('费用记录',{exact:true}).waitFor();
    assert.match(await panel.innerText(),/塔防创作流程仍在接入/);
    if(scenario==='empty'){
      assert.match(await panel.innerText(),/还没有 OpenGame 执行记录/);
      assert.match(await panel.innerText(),/预算尚未启用或无法读取/);
      assert.equal(await panel.getByRole('button',{name:'核查并清理所属资源'}).isDisabled(),true);
      checks.empty_and_unconfigured=true;
    }else{
      assert.match(await panel.innerText(),/诊断构建/);
      assert.match(await panel.innerText(),/关联编码/);
      assert.match(await panel.innerText(),/已知预留金额/);
      await panel.getByRole('button',{name:'核查并清理所属资源'}).click();
      await panel.getByText('所属资源核查完成，没有待清理记录。',{exact:true}).waitFor();
      assert.match(await panel.innerText(),/已中断 · 已清理/);
      assert.equal(await panel.getByRole('button',{name:'核查并清理所属资源'}).isDisabled(),true);
      checks.explicit_recovery_and_history=true;
    }
    await panel.getByRole('button',{name:'刷新执行状态'}).click();
    await panel.getByRole('button',{name:'刷新执行状态'}).waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('.opengame-status')?.getAttribute('aria-busy')||document.querySelector('.opengame-status').getAttribute('aria-busy')==='false');
    await panel.getByText('费用记录',{exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(out,scenario+'-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    await panel.getByText('费用记录',{exact:true}).scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.equal(await page.locator('.setup-modal').evaluate(el=>el.scrollWidth>el.clientWidth),false);
    await page.screenshot({path:path.join(out,scenario+'-mobile.png')});
    if(scenario!=='empty'){
      await panel.locator('.opengame-executions').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(out,scenario+'-records-mobile.png')});
    }
    checks.mobile_no_horizontal_overflow=true;
    await page.keyboard.press('Escape');
    await page.getByRole('dialog',{name:'给创意，做好准备。'}).waitFor({state:'hidden'});
    checks.keyboard_close=true;
    await page.setViewportSize({width:1280,height:900});
    await page.getByRole('button',{name:'模型与连接',exact:true}).click();
    await page.getByText('OpenGame 执行与预算',{exact:true}).click();
    await page.getByRole('region',{name:'OpenGame 执行状态'}).getByText('费用记录',{exact:true}).waitFor();
    checks.model_settings_entry=true;
    await page.route('**/api/settings/opengame/diagnostics',route=>route.fulfill({status:503,body:'unavailable'}));
    await page.getByRole('button',{name:'刷新执行状态'}).click();
    await page.getByRole('alert').filter({hasText:'下方保留上次结果'}).waitFor();
    assert.match(await page.getByRole('region',{name:'OpenGame 执行状态'}).innerText(),/本次检查未完成/);
    await page.unroute('**/api/settings/opengame/diagnostics');
    await page.getByRole('button',{name:'刷新执行状态'}).click();
    await page.getByRole('alert').filter({hasText:'下方保留上次结果'}).waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.querySelector('.opengame-status')?.getAttribute('aria-busy')==='false');
    assert.equal(await page.getByRole('alert').filter({hasText:'下方保留上次结果'}).count(),0);
    checks.failed_refresh_preserves_previous_result=true;
    assert.equal(calls.filter(call=>call.url.endsWith('/test')).length,0);
    assert.equal(calls.filter(call=>call.method!=='GET'&&call.url!=='/api/settings/opengame/recover').length,0);
    assert.equal(errors.length,0);
    checks.no_model_test_calls_or_page_errors=true;
    fs.writeFileSync(path.join(out,scenario+'-ui.json'),JSON.stringify({passed:true,scenario,checks,calls,errors},null,2));
    console.log(JSON.stringify({passed:true,scenario,checks,output:out}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
