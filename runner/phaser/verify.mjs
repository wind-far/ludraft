import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root='/workspace';
const evidence={passed:false,build:false,scope:'phaser-integration-smoke',gameplay_verified:false,checks:[],console_errors:[],resource_failures:[],started_at:new Date().toISOString()};
let server,browser;
function check(name,ok){evidence.checks.push({name,passed:!!ok});if(!ok)throw new Error('检查失败: '+name);}
try{
  const built=spawnSync(process.execPath,[fileURLToPath(new URL('./build.mjs',import.meta.url)),root],{timeout:75000,encoding:'utf8',maxBuffer:2*1024*1024});
  evidence.build_log=((built.stdout||'')+(built.stderr||'')+(built.error?.message||'')).slice(-18000);
  evidence.build=built.status===0;check('固定 Phaser TypeScript/Vite 构建',evidence.build);
  const types={'.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.html':'text/html'};
  server=http.createServer((req,res)=>{
    try{
      const pathname=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);
      const target=path.resolve(root+'/dist','.'+(pathname==='/'?'/index.html':pathname));
      if(!target.startsWith(root+'/dist/')||!fs.existsSync(target)||!fs.statSync(target).isFile())throw new Error('missing');
      res.setHeader('Content-Type',types[path.extname(target)]||'application/octet-stream');fs.createReadStream(target).pipe(res);
    }catch{res.writeHead(404);res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:1152,height:768}});page.setDefaultTimeout(10000);
  page.on('pageerror',error=>{if(evidence.console_errors.length<50)evidence.console_errors.push(error.message);});
  page.on('response',response=>{if(response.status()>=400&&evidence.resource_failures.length<50)evidence.resource_failures.push({url:new URL(response.url()).pathname,status:response.status()});});
  page.on('requestfailed',request=>{if(evidence.resource_failures.length<50)evidence.resource_failures.push({url:request.url(),error:request.failure()?.errorText});});
  const origin=`http://127.0.0.1:${server.address().port}`;
  await page.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  await page.goto(origin);
  await page.locator('#title-screen-container').waitFor();
  check('开始画面显示',await page.locator('canvas').isVisible());
  await page.keyboard.press('Enter');
  await page.locator('[data-tower-id="arrow"]').waitFor();
  await page.waitForFunction(()=>document.querySelector('#gold-text')?.textContent==='100');
  // Actual pointer input and visible HUD evidence, not a generated passed flag.
  await page.locator('[data-tower-id="arrow"]').click();
  await page.mouse.click(352,288);
  await page.waitForFunction(()=>document.querySelector('#gold-text')?.textContent==='60');
  check('点击建塔扣除 40 金币',true);
  await page.mouse.click(352,288);
  await page.waitForFunction(()=>document.querySelector('#gold-text')?.textContent==='30');
  check('点击升级扣除 30 金币',true);
  check('Phaser 图片资源已加载',await page.evaluate(()=>['tower_basic','tower_cannon','enemy_basic'].every(key=>window.__phaserGame.textures.exists(key))));
  check('地图场景渲染',await page.evaluate(()=>window.__phaserGame.scene.isActive('Level1Scene')));
  await page.locator('#pause-btn').click();
  await page.locator('#menu-btn').click();
  await page.locator('#title-screen-container').waitFor();
  await page.keyboard.press('Enter');
  await page.waitForFunction(()=>document.querySelector('#gold-text')?.textContent==='100');
  check('返回标题后重新开始恢复初始金币',true);
  check('重开后波次与监听器重置',await page.evaluate(()=>{
    const scene=window.__phaserGame.scene.getScene('Level1Scene');
    return document.querySelector('#wave-text')?.textContent==='1/5' && scene.events.listenerCount('enemyKilled')===1 && scene.events.listenerCount('spawnEnemy')===1;
  }));
  await page.locator('[data-tower-id="arrow"]').click();
  await page.mouse.click(352,288);
  await page.waitForFunction(()=>document.querySelector('#gold-text')?.textContent==='60');
  check('重开后同位置可重新建塔',true);
  check('资源加载无错误',evidence.resource_failures.length===0);
  check('页面无未处理异常',evidence.console_errors.length===0);
  await page.screenshot({path:root+'/phaser-smoke.png'});
  evidence.passed=true;
}catch(error){evidence.error=error.message;}
finally{
  if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));
  evidence.finished_at=new Date().toISOString();
  fs.writeFileSync(root+'/evidence.json',JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));process.exitCode=evidence.passed?0:1;
}
