import { BaseTDScene } from './BaseTDScene';
import { BaseTDEnemy } from '../enemies/BaseTDEnemy';
import type { BaseTower } from '../towers/BaseTower';
import { CellType, drawPathLine, drawTowerSlots } from '../utils';
import { towers, waves, enemy } from '../config';

/** Local fixed-route implementation using the upstream extension methods. */
export class Level1Scene extends BaseTDScene {
  constructor(){super({key:'Level1Scene'});}
  protected getGridConfig(){
    const cells:CellType[][]=Array.from({length:8},()=>Array(12).fill(CellType.BUILDABLE));
    for(let x=0;x<12;x++)cells[3][x]=CellType.PATH;
    cells[3][0]=CellType.SPAWN;cells[3][11]=CellType.EXIT;
    return {cols:12,rows:8,cellSize:64,cells,offsetX:192,offsetY:128};
  }
  protected getPathWaypoints(){return [{gridX:0,gridY:3},{gridX:11,gridY:3}];}
  protected getTowerTypes(){return towers;}
  protected getWaveDefinitions(){return waves;}
  protected createEnemy(type:string){
    return type==='basic'?new BaseTDEnemy(this,0,0,{textureKey:'enemy_basic',displayHeight:36,stats:enemy}):null;
  }
  protected createEnvironment():void {
    const g=this.add.graphics().setDepth(-10);
    g.fillStyle(0x173e30);g.fillRect(0,0,1152,768);
    for(let y=0;y<8;y++)for(let x=0;x<12;x++){
      g.fillStyle(y===3?0x9a8056:((x+y)%2?0x2c5740:0x315e46));
      g.fillRoundedRect(192+x*64+2,128+y*64+2,60,60,6);
    }
    drawPathLine(this,this.pathWaypoints);
    this.towerSlotGroup=drawTowerSlots(this,this.cells,this.cellSize,this.gridOffsetX,this.gridOffsetY);
    this.add.text(192,94,'林间守卫 · 守住五波敌人',{fontSize:'23px',color:'#e6f3dc'});
    this.add.text(192,649,'选塔后点击草地建造 · 点击已有塔升级',{fontSize:'17px',color:'#c7dcbf'});
    this.add.text(168,347,'入口',{fontSize:'15px',color:'#fbdca1'}).setOrigin(1,0.5);
    this.add.text(974,347,'基地',{fontSize:'15px',color:'#fbdca1'}).setOrigin(0,0.5);
  }
  protected onTowerClicked(tower:BaseTower):void {this.upgradeTower(tower);}
}
