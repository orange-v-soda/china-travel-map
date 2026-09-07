'use strict';
const NS='http://www.w3.org/2000/svg';
const palette=[['#2864dc','蓝色'],['#e65b4e','红色'],['#f4bf45','黄色'],['#299b7d','绿色'],['#9870c8','紫色'],['#ffffff','白色（擦除）']];
const colors=Object.fromEntries(MAP_DATA.regions.map(r=>[r.id,'#ffffff']));
let active=palette[0][0];
const svg=document.querySelector('#map');
const status=document.querySelector('#status');
const regionElements=new Map(),labelElements=new Map();
function ink(hex){const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]>.179?'#17263b':'#ffffff';}
function path(points){return points.map(([x,y],i)=>(i?'L':'M')+(124+x*32)+' '+(152+y*32)).join(' ')+' Z';}
function count(){document.querySelector('#count').textContent=Object.values(colors).filter(c=>c!=='#ffffff').length;}
function setColor(region,color){colors[region.id]=color;regionElements.get(region.id).setAttribute('fill',color);regionElements.get(region.id).setAttribute('aria-label',region.name+'市，'+(color==='#ffffff'?'未填色':'已填色')+'，按回车填色');labelElements.get(region.id).setAttribute('fill',ink(color));count();}
function paint(region){setColor(region,active);status.textContent=region.name+'：'+(active==='#ffffff'?'已擦除':'已填色');}
for(const region of MAP_DATA.regions){
 const p=document.createElementNS(NS,'path');p.setAttribute('d',path(region.points));p.setAttribute('fill','#ffffff');p.setAttribute('tabindex','0');p.setAttribute('role','button');p.dataset.city=region.id;p.setAttribute('aria-label',region.name+'市，未填色，按回车填色');p.addEventListener('click',()=>paint(region));p.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();paint(region);}});document.querySelector('#regions').append(p);regionElements.set(region.id,p);
 const t=document.createElementNS(NS,'text');t.setAttribute('x',124+region.label[0]*32);t.setAttribute('y',152+region.label[1]*32);t.setAttribute('fill','#17263b');t.textContent=region.name;document.querySelector('#labels').append(t);labelElements.set(region.id,t);
}
document.querySelector('#outline').setAttribute('d',path(MAP_DATA.outline));
function select(color){active=color.toLowerCase();for(const b of document.querySelectorAll('.swatch'))b.setAttribute('aria-pressed',String(b.dataset.color===active));document.querySelector('#custom-color').value=active;}
for(const [color,name]of palette){const b=document.createElement('button');b.type='button';b.className='swatch';b.dataset.color=color;b.style.backgroundColor=color;b.style.setProperty('--check',ink(color));b.setAttribute('aria-label',name);b.title=name;b.addEventListener('click',()=>select(color));document.querySelector('#palette').append(b);}
select(active);
document.querySelector('#custom-color').addEventListener('input',e=>select(e.target.value));
document.querySelector('#reset').addEventListener('click',()=>{for(const r of MAP_DATA.regions)setColor(r,'#ffffff');status.textContent='已清空全部颜色';});
document.querySelector('#export').addEventListener('click',async()=>{
 const button=document.querySelector('#export');button.disabled=true;status.textContent='正在生成完整图片…';let sourceUrl;
 try{
  await document.fonts.ready;
  const copy=svg.cloneNode(true);copy.setAttribute('width','1520');copy.setAttribute('height','1720');copy.querySelectorAll('[tabindex]').forEach(el=>{el.removeAttribute('tabindex');el.removeAttribute('role');});
  sourceUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));
  const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('图片渲染失败'));img.src=sourceUrl;});
  const canvas=document.createElement('canvas');canvas.width=1520;canvas.height=1720;const ctx=canvas.getContext('2d');if(!ctx)throw new Error('浏览器不支持图片导出');ctx.drawImage(img,0,0,1520,1720);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('无法生成 PNG');
  const downloadUrl=URL.createObjectURL(blob);const a=document.createElement('a');a.href=downloadUrl;a.download='中国旅行地图-江西.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(downloadUrl),60000);status.textContent='已生成完整图片（1520 × 1720）';
 }catch(e){status.textContent='导出失败，请重试或更换浏览器。';console.error(e);}finally{if(sourceUrl)URL.revokeObjectURL(sourceUrl);button.disabled=false;}
});
