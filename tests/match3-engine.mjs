import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const {Game}=await import(pathToFileURL(process.argv[2]+'/game.js'));
const {config}=await import(pathToFileURL(process.argv[2]+'/config.js'));
function seeded(seed){return ()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};}
function settle(g){for(let i=0;i<500&&g.busy;i++)g.tick(.1);assert.equal(g.busy,false);}
function independentMatches(b){const m=new Set();for(let i=0;i<64;i++){if(i%8<6&&b[i]===b[i+1]&&b[i]===b[i+2])[i,i+1,i+2].forEach(x=>m.add(x));if(i<48&&b[i]===b[i+8]&&b[i]===b[i+16])[i,i+8,i+16].forEach(x=>m.add(x));}return m;}
for(const types of [4,5,6]){
 config.gemTypes=types;
 for(let seed=1;seed<=30;seed++){
  const g=new Game();g.random=seeded(seed);g.start();
  for(let turn=0;turn<30&&g.status==='playing';turn++){
   assert.equal(independentMatches(g.board).size,0);assert.equal(g.board.length,64);assert.ok(g.board.every(x=>x>=0&&x<types));
   const legal=g.legalMoves();assert.ok(legal.length);
   const pair=legal[turn%legal.length],before=g.moves;
   assert.ok(g.swap(...pair));settle(g);assert.equal(g.moves,before-1);
  }
 }
 const g=new Game();g.random=()=>0;g.start();assert.equal(independentMatches(g.board).size,0);assert.ok(g.legalMoves().length);
 assert.equal(g.swap(-1,0),false);assert.equal(g.swap(7,8),false);assert.equal(g.swap(0,1.5),false);
 g.select(0);g.select(63);assert.equal(g.selected,63);assert.equal(g.moves,config.moves);
 g.start();assert.equal(g.selected,null);assert.equal(g.score,0);assert.equal(g.outcome,null);
}
console.log('PASS: 90 seeded games across 4/5/6 gems, independent stable-board checks, legal moves, one-step charging, degenerate RNG, invalid positions and restart.');

for(const n of [4,5,6]){
 config.gemTypes=n;const g=new Game();g.start();g.board=Array.from({length:64},(_,i)=>(Math.floor(i/8)*2+i%8)%n);
 g.board[0]=0;g.board[1]=1;g.board[2]=0;g.board[9]=0;g.board[56]=0;g.board[57]=1;g.board[58]=0;g.board[49]=0;
 assert.equal(independentMatches(g.board).size,0);
 const invalid=[...g.board];[invalid[6],invalid[7]]=[invalid[7],invalid[6]];assert.equal(independentMatches(invalid).size,0);
 const values=[0,0,0,2,3,1];let index=0;g.random=()=>((values[index++]??(index%n))+.1)/n;
 assert.equal(g.swap(1,9),true);settle(g);assert.equal(g.score,90);assert.equal(g.maxCascade,2);assert.equal(g.shuffles,0);
}
console.log('PASS: fixed runner invalid-swap and exact two-cascade fixtures independently verified for all gem counts.');
