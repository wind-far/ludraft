import { config } from './config.js';
export class Game {
  board: number[] = [];
  score = 0;
  moves = config.moves;
  status: 'ready'|'playing'|'over' = 'ready';
  outcome: 'won'|'lost'|null = null;
  selected: number|null = null;
  cursor = 0;
  phase: 'idle'|'invalid'|'clearing'|'falling' = 'idle';
  phaseClock = 0;
  matches: number[] = [];
  cascade = 0;
  maxCascade = 0;
  shuffles = 0;
  message = '交换相邻宝石，连成三个或更多';
  private exchanged: [number,number]|null = null;
  random: ()=>number = Math.random;
  get busy() { return this.phase !== 'idle'; }
  gem() { return Math.min(config.gemTypes-1, Math.max(0,Math.floor(this.random()*config.gemTypes))); }
  adjacent(a:number,b:number) {
    return Number.isInteger(a)&&Number.isInteger(b)&&a>=0&&b>=0&&a<64&&b<64&&
      Math.abs(a%8-b%8)+Math.abs(Math.floor(a/8)-Math.floor(b/8))===1;
  }
  findMatches(board=this.board) {
    const found=new Set<number>();
    for(let r=0;r<8;r++)for(let c=0;c<8;c++) {
      const i=r*8+c,g=board[i];if(g<0)continue;
      if(c<=5&&g===board[i+1]&&g===board[i+2]) {
        let k=c;while(k<8&&board[r*8+k]===g)found.add(r*8+k++);
      }
      if(r<=5&&g===board[i+8]&&g===board[i+16]) {
        let k=r;while(k<8&&board[k*8+c]===g)found.add((k++)*8+c);
      }
    }
    return [...found];
  }
  legalMoves() {
    const result:[number,number][]=[];
    for(let a=0;a<64;a++)for(const b of [a+1,a+8]) {
      if(!this.adjacent(a,b))continue;
      const copy=[...this.board];[copy[a],copy[b]]=[copy[b],copy[a]];
      if(this.findMatches(copy).length)result.push([a,b]);
    }
    return result;
  }
  newBoard() {
    for(let attempt=0;attempt<60;attempt++) {
      this.board=[];
      for(let i=0;i<64;i++) {
        const banned=new Set<number>();
        if(i%8>=2&&this.board[i-1]===this.board[i-2])banned.add(this.board[i-1]);
        if(i>=16&&this.board[i-8]===this.board[i-16])banned.add(this.board[i-8]);
        const allowed=Array.from({length:config.gemTypes},(_,g)=>g).filter(g=>!banned.has(g));
        this.board.push(allowed[Math.min(allowed.length-1,Math.max(0,Math.floor(this.random()*allowed.length)))]);
      }
      if(this.legalMoves().length)return;
    }
    // Guaranteed stable board with a legal swap, also for a degenerate RNG.
    this.board=Array.from({length:64},(_,i)=>(Math.floor(i/8)*2+i%8)%config.gemTypes);
    this.board[0]=0;this.board[1]=1;this.board[2]=0;this.board[9]=0;
  }
  ensurePlayable() {
    if(this.legalMoves().length)return;
    this.newBoard();this.shuffles++;
    this.message='没有可用交换，棋盘已重新排列';
  }
  start() {
    this.score=0;this.moves=config.moves;this.status='playing';this.outcome=null;
    this.selected=null;this.cursor=0;this.phase='idle';this.phaseClock=0;
    this.matches=[];this.cascade=0;this.maxCascade=0;this.shuffles=0;this.exchanged=null;
    this.message='交换相邻宝石，连成三个或更多';this.newBoard();
  }
  select(index:number) {
    if(this.status!=='playing'||this.busy||!Number.isInteger(index)||index<0||index>=64)return;
    this.cursor=index;
    if(this.selected===null){this.selected=index;return;}
    const first=this.selected;
    if(first===index){this.selected=null;return;}
    if(!this.adjacent(first,index)){this.selected=index;return;}
    this.selected=null;this.swap(first,index);
  }
  swap(a:number,b:number) {
    if(this.status!=='playing'||this.busy||!this.adjacent(a,b))return false;
    this.selected=null;[this.board[a],this.board[b]]=[this.board[b],this.board[a]];
    this.matches=this.findMatches();this.phaseClock=0;
    if(!this.matches.length){this.exchanged=[a,b];this.phase='invalid';this.message='未形成三消，交换已退回';return false;}
    this.moves--;this.cascade=1;this.phase='clearing';this.message='消除 '+this.matches.length+' 颗宝石';return true;
  }
  tick(dt:number) {
    if(this.status!=='playing'||!this.busy)return;
    this.phaseClock+=Math.min(.1,Math.max(0,dt));if(this.phaseClock<.18)return;
    this.phaseClock=0;
    if(this.phase==='invalid') {
      if(this.exchanged){const [a,b]=this.exchanged;[this.board[a],this.board[b]]=[this.board[b],this.board[a]];}
      this.exchanged=null;this.phase='idle';return;
    }
    if(this.phase==='clearing') {
      this.score+=this.matches.length*10*this.cascade;this.maxCascade=Math.max(this.maxCascade,this.cascade);
      for(const i of this.matches)this.board[i]=-1;
      for(let c=0;c<8;c++) {
        const gems=[];for(let r=7;r>=0;r--)if(this.board[r*8+c]>=0)gems.push(this.board[r*8+c]);
        for(let r=7;r>=0;r--)this.board[r*8+c]=gems[7-r]??this.gem();
      }
      this.matches=[];this.phase='falling';return;
    }
    this.matches=this.findMatches();
    if(this.matches.length&&this.cascade<50){this.cascade++;this.phase='clearing';this.message=this.cascade+' 连锁！';return;}
    if(this.matches.length)this.newBoard();
    this.phase='idle';this.matches=[];
    if(this.score>=config.targetScore){this.outcome='won';this.status='over';this.message='目标达成！';}
    else if(this.moves<=0){this.outcome='lost';this.status='over';this.message='步数用完了，再试一次';}
    else this.ensurePlayable();
  }
}
