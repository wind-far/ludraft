import type { TowerTypeConfig } from './towers/BaseTower';
import type { WaveDefinition } from './systems/WaveManager';

export const towers: TowerTypeConfig[] = [
  {id:'arrow',name:'箭塔',textureKey:'tower_basic',cost:40,damage:16,range:170,fireRate:1.5,projectileSpeed:340,targetingMode:'first',
    upgrades:[{level:2,cost:30,damage:28,range:190,fireRate:1.8}]},
  {id:'cannon',name:'重炮',textureKey:'tower_cannon',cost:65,damage:42,range:200,fireRate:0.65,projectileSpeed:260,targetingMode:'strongest',
    upgrades:[{level:2,cost:45,damage:68,range:215,fireRate:0.8}]},
];
export const waves: WaveDefinition[] = Array.from({length:5},(_,index)=>({
  preDelay:index===0?5000:1000,
  groups:[{enemyType:'basic',count:4+index,interval:1000}],reward:20+index*5,
}));
export const enemy = {maxHealth:65,speed:75,reward:12,damage:1};
