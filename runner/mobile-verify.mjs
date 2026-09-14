// Actual Chromium touch input at phone dimensions; fixed test data is not model evidence.
export async function verifyMobile(browser, url, config, check, evidence, canvasV2) {
  if(config.mode!=='match3'&&!canvasV2) {
    evidence.mobile={status:'unverified',reason:'旧版固定入口保留原桌面验证；新建作品使用支持触屏的模板。'};
    return;
  }
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    page.on('pageerror', e => { if (evidence.console_errors.length < 100) evidence.console_errors.push(e.message); });
    await page.goto(url);
    await page.waitForFunction(() => window.__game && window.__config);
    check('移动端布局', await page.evaluate(() => {
      const canvas=document.querySelector('canvas'),r=canvas.getBoundingClientRect();
      return document.documentElement.scrollWidth<=390 && r.width>200 && r.right<=390 && r.left>=0 && getComputedStyle(canvas).touchAction==='none';
    }));
    await page.locator('#start').tap();
    await page.waitForFunction(() => window.__game.status==='playing');
    const client = await context.newCDPSession(page);
    const point=async(x,y)=>{const b=await page.locator('canvas').boundingBox();return {x:b.x+x*b.width/640,y:b.y+y*b.height/440,id:1};};
    const send=(type,p)=>client.send('Input.dispatchTouchEvent',{type,touchPoints:p?[p]:[]});
    if(config.mode==='match3') {
      await page.evaluate(()=>{
        const g=window.__game,n=window.__config.gemTypes;g.start();
        g.board=Array.from({length:64},(_,i)=>(Math.floor(i/8)*2+i%8)%n);
        g.board[0]=0;g.board[1]=1;g.board[2]=0;g.board[9]=0;
        g.board[56]=0;g.board[57]=1;g.board[58]=0;g.board[49]=0;
      });
      await send('touchStart',await point(200,52));
      await send('touchMove',await point(200,100));
      await send('touchEnd');
      await page.waitForFunction(()=>!window.__game.busy);
      check('触屏交换消除',await page.evaluate(()=>window.__game.score>=30&&window.__game.moves===window.__config.moves-1));
    } else if(config.mode==='clicker') {
      await page.evaluate(()=>window.__game.spawn('coin',180,150));
      const p=await point(180,150);await page.touchscreen.tap(p.x,p.y);
      await page.waitForFunction(()=>window.__game.score===10&&Number(document.querySelector('#score').textContent)===10);
      check('触屏点击得分',await page.evaluate(()=>window.__game.score===10&&Number(document.querySelector('#score').textContent)===10));
    } else if(canvasV2) {
      await send('touchStart',await point(320,300));
      await send('touchMove',await point(90,300));
      await page.waitForFunction(delta=>window.__game.x<320-delta,Math.min(20,config.speed*.1));
      await send('touchEnd');
      const stopped=await page.evaluate(()=>window.__game.x);
      await page.waitForTimeout(160);
      const still=await page.evaluate(x=>Math.abs(window.__game.x-x)<1,stopped);
      await send('touchStart',await point(540,300));
      await page.waitForFunction(({x,delta})=>window.__game.x>x+delta,{x:stopped,delta:Math.min(20,config.speed*.1)});
      await send('touchCancel');
      const cancelled=await page.evaluate(()=>window.__game.x);
      await page.waitForTimeout(160);
      check('触屏拖动与停止',still&&await page.evaluate(x=>Math.abs(window.__game.x-x)<1,cancelled));
    }
    if(canvasV2) {
      await page.evaluate(()=>{const g=window.__game;g.start();g.elapsed=window.__config.duration-2.2;});
      await page.waitForFunction(()=>Number(document.querySelector('#remaining').textContent)<=3);
      const remaining=await page.locator('#remaining').textContent();
      await page.evaluate(()=>window.__game.elapsed=window.__config.duration);
      await page.waitForFunction(()=>window.__game.status==='over'&&document.querySelector('#remaining').textContent==='0');
      await page.locator('#start').tap();
      await page.waitForFunction(()=>window.__game.status==='playing'&&Number(document.querySelector('#remaining').textContent)===Math.ceil(window.__config.duration));
      check('倒计时与重开',Number(remaining)>0&&Number(remaining)<=3&&await page.evaluate(()=>Number(document.querySelector('#remaining').textContent)===Math.ceil(window.__config.duration)&&window.__game.score===0));
    }
    evidence.mobile={status:'passed',viewport:{width:390,height:844},input:'Chromium touch events'};
  } finally { await context.close(); }
}
