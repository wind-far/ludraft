import { config } from './config.js';
import { Game } from './game.js';
const game=new Game();
const canvas=document.querySelector<HTMLCanvasElement>('#game')!;
const ctx=canvas.getContext('2d')!;
const start=document.querySelector<HTMLButtonElement>('#start')!;
const palette=[config.playerColor,config.targetColor,config.hazardColor,'#8c91db','#6caed5','#bd87c0'];
const symbols=['◆','✦','♥','●','✿','■'];
const originX=128,originY=28,tile=48;
document.querySelector('#title')!.textContent=config.title;document.title=config.title;
document.querySelector('#target')!.textContent=String(config.targetScore);
start.onclick=()=>{game.start();canvas.focus();};
function position(e:PointerEvent) {
  const b=canvas.getBoundingClientRect(),x=(e.clientX-b.left)*640/b.width,y=(e.clientY-b.top)*440/b.height;
  const c=Math.floor((x-originX)/tile),r=Math.floor((y-originY)/tile);
  return c<0||r<0||c>=8||r>=8?-1:r*8+c;
}
let down=-1;
canvas.onpointerdown=e=>{down=position(e);canvas.setPointerCapture(e.pointerId);};
canvas.onpointerup=e=>{const up=position(e);if(down>=0&&up>=0){if(down!==up&&game.adjacent(down,up))game.swap(down,up);else game.select(up);}down=-1;};
canvas.onpointercancel=()=>{down=-1;};
canvas.onkeydown=e=>{
  const deltas:Record<string,number>={ArrowLeft:-1,ArrowRight:1,ArrowUp:-8,ArrowDown:8};
  if(e.key in deltas){e.preventDefault();const next=game.cursor+deltas[e.key];if(game.adjacent(game.cursor,next))game.cursor=next;}
  if(e.key===' '||e.key==='Enter'){e.preventDefault();game.select(game.cursor);}
};
if(new URLSearchParams(location.search).has('test'))Object.assign(window,{__game:game,__config:config});
let last=performance.now();
function draw(time:number) {
  game.tick((time-last)/1000);last=time;
  ctx.fillStyle=config.background;ctx.fillRect(0,0,640,440);
  ctx.fillStyle='#ffffffb0';ctx.beginPath();ctx.roundRect(originX-8,originY-8,400,400,20);ctx.fill();
  for(let i=0;i<game.board.length;i++) {
    const x=originX+(i%8)*tile,y=originY+Math.floor(i/8)*tile,g=game.board[i];
    ctx.fillStyle=(Math.floor(i/8)+i%8)%2?'#e9eef7':'#eff3fa';ctx.fillRect(x+2,y+2,44,44);
    ctx.save();ctx.globalAlpha=game.matches.includes(i)?Math.max(.2,1-game.phaseClock*3):1;
    ctx.fillStyle=palette[g];ctx.shadowColor=palette[g]+'55';ctx.shadowBlur=8;
    ctx.beginPath();ctx.roundRect(x+7,y+7+(game.phase==='falling'?-6*(1-game.phaseClock/.18):0),34,34,10);ctx.fill();
    ctx.shadowBlur=0;ctx.fillStyle='#ffffffed';ctx.font='bold 23px system-ui';ctx.textAlign='center';ctx.fillText(symbols[g],x+24,y+32);ctx.restore();
    if(game.selected===i||game.cursor===i&&document.activeElement===canvas){ctx.strokeStyle=game.selected===i?'#3478f6':'#3478f680';ctx.lineWidth=3;ctx.strokeRect(x+3,y+3,42,42);}
  }
  if(game.status!=='playing') {
    ctx.fillStyle='#f5f8f1e8';ctx.fillRect(72,142,496,146);ctx.textAlign='center';ctx.fillStyle='#263348';ctx.font='600 27px system-ui';
    ctx.fillText(game.status==='ready'?'欢迎来到宝石花园':game.outcome==='won'?'目标达成，花园绽放！':'差一点，再挑战一次',320,204);
    ctx.font='15px system-ui';ctx.fillText(game.status==='ready'?'在有限步数内，交换宝石完成消除目标':'本局得分 '+game.score+' · 最高 '+game.maxCascade+' 连锁',320,242);
  }
  document.querySelector('#score')!.textContent=String(game.score);
  document.querySelector('#moves')!.textContent=String(game.moves);
  if(document.querySelector('#status')!.textContent!==game.message)document.querySelector('#status')!.textContent=game.message;
  start.textContent=game.status==='ready'?'开始游戏':'重新开始';
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
