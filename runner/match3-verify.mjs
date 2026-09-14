export async function verifyMatch3(page,config,check) {
  check('三消参数边界',Number.isInteger(config.moves)&&config.moves>=5&&config.moves<=100&&Number.isInteger(config.targetScore)&&config.targetScore>=100&&config.targetScore<=20000&&Number.isInteger(config.gemTypes)&&config.gemTypes>=4&&config.gemTypes<=6);
  await page.locator('#start').click();
  check('开始游戏',await page.evaluate(()=>window.__game.status==='playing'));
  const stable=()=>page.evaluate(()=>{
    const a=window.__game.board,n=window.__config.gemTypes;
    if(a.length!==64||!a.every(x=>Number.isInteger(x)&&x>=0&&x<n))return false;
    for(let i=0;i<64;i++)if(i%8<6&&a[i]===a[i+1]&&a[i]===a[i+2]||i<48&&a[i]===a[i+8]&&a[i]===a[i+16])return false;
    return true;
  });
  check('棋盘初始可玩',await stable() && await page.evaluate(()=>window.__game.legalMoves().length>0));
  const fixture=async(chain=false)=>page.evaluate(chain=>{
    const g=window.__game,n=window.__config.gemTypes;g.start();
    g.board=Array.from({length:64},(_,i)=>(Math.floor(i/8)*2+i%8)%n);
    g.board[0]=0;g.board[1]=1;g.board[2]=0;g.board[9]=0;
    // Keep a second legal swap so this cascade fixture does not also trigger a reshuffle.
    g.board[56]=0;g.board[57]=1;g.board[58]=0;g.board[49]=0;
    const values=chain?[0,0,0,2,3,1]:[2,3,1];let i=0;
    g.random=()=>((values[i++]??(i%n))+.1)/n;
  },chain);
  const click=async index=>{
    const b=await page.locator('canvas').boundingBox();
    await page.mouse.click(b.x+(128+(index%8)*48+24)*b.width/640,b.y+(28+Math.floor(index/8)*48+24)*b.height/440);
  };
  const settle=()=>page.waitForFunction(()=>!window.__game.busy,{},{timeout:8000});
  await fixture();const before=await page.evaluate(()=>({board:[...window.__game.board],moves:window.__game.moves}));
  await click(6);await click(7);await settle();
  check('无效交换回退',await page.evaluate(before=>JSON.stringify(window.__game.board)===JSON.stringify(before.board)&&window.__game.moves===before.moves&&window.__game.score===0,before));
  check('禁止跨格交换',await page.evaluate(()=>{const g=window.__game,a=JSON.stringify(g.board);return g.swap(0,63)===false&&JSON.stringify(g.board)===a;}));
  await fixture(true);await click(1);await click(9);
  check('结算期间禁止重复操作',await page.evaluate(()=>window.__game.busy&&window.__game.swap(3,4)===false));
  await settle();
  check('真实交换消除与步数',await page.evaluate(()=>window.__game.score===90&&window.__game.moves===window.__config.moves-1&&Number(document.querySelector('#score').textContent)===90));
  check('下落补位与连锁',await stable() && await page.evaluate(()=>window.__game.maxCascade===2&&window.__game.board[0]===2&&window.__game.board[1]===3&&window.__game.board[2]===1));
  const dead=await page.evaluate(()=>{
    const g=window.__game;g.start();g.board=Array.from({length:64},(_,i)=>(Math.floor(i/8)+i%8)%window.__config.gemTypes);
    const before=g.legalMoves().length;g.random=Math.random;g.ensurePlayable();
    return before===0&&g.shuffles===1&&g.moves===window.__config.moves&&g.score===0&&g.legalMoves().length>0;
  });
  check('无解棋盘重排',dead&&await stable());
  await fixture();await page.evaluate(()=>{window.__game.score=window.__config.targetScore-10;window.__game.moves=1;});
  await click(1);await click(9);await settle();
  const won=await page.evaluate(()=>window.__game.status==='over'&&window.__game.outcome==='won');
  await fixture();await page.evaluate(()=>{window.__game.moves=1;});await click(1);await click(9);await settle();
  check('目标达成与失败',won&&await page.evaluate(()=>window.__game.status==='over'&&window.__game.outcome==='lost'));
  await page.locator('#start').click();
  check('重新开始',await page.evaluate(()=>{const g=window.__game;return g.status==='playing'&&g.score===0&&g.moves===window.__config.moves&&!g.busy&&g.outcome===null;}));
}
