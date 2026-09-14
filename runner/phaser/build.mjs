/** Trusted build recipe. Never load project npm scripts, Vite or PostCSS configs. */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {build} from 'vite';
import tailwind from 'tailwindcss';
const recipeDir=path.dirname(fileURLToPath(import.meta.url));
const source=path.resolve(process.argv[2]||'/workspace');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'phaser-build-'));
function copy(from,to){
  const stat=fs.lstatSync(from);
  if(stat.isSymbolicLink())throw new Error('Source symlinks are forbidden');
  if(stat.isDirectory()){
    fs.mkdirSync(to,{recursive:true});
    for(const name of fs.readdirSync(from))copy(path.join(from,name),path.join(to,name));
  }else if(stat.isFile())fs.copyFileSync(from,to);
  else throw new Error('Special source files are forbidden');
}
try{
  for(const name of ['src','public','index.html','style.css']){
    if(fs.existsSync(path.join(source,name)))copy(path.join(source,name),path.join(root,name));
  }
  fs.symlinkSync(path.join(recipeDir,'node_modules'),path.join(root,'node_modules'),'dir');
  fs.writeFileSync(path.join(root,'package.json'),JSON.stringify({type:'module'}));
  fs.writeFileSync(path.join(root,'tsconfig.json'),JSON.stringify({compilerOptions:{target:'ES2022',module:'ESNext',moduleResolution:'bundler',lib:['ES2022','DOM'],skipLibCheck:true,resolveJsonModule:true,allowSyntheticDefaultImports:true,noEmit:true,strict:false},include:['src']}));
  const checked=spawnSync(process.execPath,[path.join(recipeDir,'node_modules/typescript/bin/tsc'),'-p',path.join(root,'tsconfig.json')],{timeout:45000,encoding:'utf8',maxBuffer:2*1024*1024});
  if(checked.status!==0)throw new Error((checked.stdout||'')+(checked.stderr||'')+(checked.error?.message||''));
  await build({configFile:false,root,base:'./',publicDir:'public',
    css:{postcss:{plugins:[tailwind({content:[path.join(root,'src/**/*.ts')],theme:{extend:{fontFamily:{retro:['system-ui','sans-serif']}}}})]}},
    build:{outDir:path.join(root,'dist'),assetsInlineLimit:0,sourcemap:false,emptyOutDir:true}});
  fs.rmSync(path.join(source,'dist'),{recursive:true,force:true});
  copy(path.join(root,'dist'),path.join(source,'dist'));
}finally{fs.rmSync(root,{recursive:true,force:true});}
