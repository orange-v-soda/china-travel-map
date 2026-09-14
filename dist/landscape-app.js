'use strict';
const NS='http://www.w3.org/2000/svg',svg=document.querySelector('#map'),status=document.querySelector('#status');
const referenceSvg=svg.cloneNode(true),regions=new Map(),labels=new Map(),references=new Map();
let mode='balanced',selected=null;
for(const el of [referenceSvg,...referenceSvg.querySelectorAll('[id]')])el.id='reference-'+el.id;
referenceSvg.setAttribute('aria-labelledby','reference-map-title reference-map-desc');
referenceSvg.querySelector('#reference-map-title').textContent='完整真实区划参考';
referenceSvg.querySelector('#reference-map-desc').textContent='原始行政区划轮廓，不包含示意地貌。';
referenceSvg.querySelector('#reference-map-subtitle').textContent='真实区划 / REFERENCE';
referenceSvg.querySelector('#reference-map-note').textContent='完整源边界 · 参考示意';
referenceSvg.querySelector('#reference-outline').remove();
document.querySelector('#reference-host').append(referenceSvg);
function el(tag,attrs={},parent){const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(parent)parent.append(n);return n;}
function describe(r){return r.id==='360100'?'南昌：西北侧梅岭山地、赣江与两岸城区、东部河湖；红色小图标为滕王阁。此图为人工地理概括。':(r.fullName||r.name)+'：本轮尚未绘制地貌。';}
function select(r){selected=r?.id||null;for(const map of [regions,references])for(const[id,p]of map)p.setAttribute('aria-pressed',String(id===selected));status.textContent=r?describe(r):'已清除选择，南昌地貌仍在总览中显示。';}
function makeRegion(r,path,parent,map){const n=el('path',{d:path,fill:'#fff','fill-rule':'evenodd',tabindex:0,role:'button','data-city':r.id,'aria-pressed':'false','aria-label':(r.fullName||r.name)+'，选择区划'},parent);n.addEventListener('click',()=>select(r));n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(r);}});n.addEventListener('pointerenter',()=>{regions.get(r.id)?.classList.add('linked');references.get(r.id)?.classList.add('linked');});n.addEventListener('pointerleave',()=>{regions.get(r.id)?.classList.remove('linked');references.get(r.id)?.classList.remove('linked');});map.set(r.id,n);}
for(const r of MAP_DATA.regions){
 makeRegion(r,r.variants[mode].path,svg.querySelector('#regions'),regions);
 const label=el('text',{x:r.variants[mode].label[0],y:r.variants[mode].label[1],fill:'#17263b','paint-order':'stroke',stroke:'#fff','stroke-width':2.3},svg.querySelector('#labels'));if(['厦门','澳门'].includes(r.name))label.setAttribute('font-size',16);label.textContent=r.name;labels.set(r.id,label);
 const ref=SOURCE_REFERENCE.regions.find(x=>x.id===r.id);makeRegion(r,ref.path,referenceSvg.querySelector('#reference-regions'),references);
 const t=el('text',{x:ref.label[0],y:ref.label[1],fill:'#17263b'},referenceSvg.querySelector('#reference-labels'));if(['厦门','澳门'].includes(r.name))t.setAttribute('font-size',16);t.textContent=r.name;
}
const defs=el('defs',{},svg),clip=el('clipPath',{id:'nanchang-landscape-clip',clipPathUnits:'userSpaceOnUse'},defs),clipPath=el('path',{},clip);
const terrain=el('g',{id:'nanchang-landscape','clip-path':'url(#nanchang-landscape-clip)','pointer-events':'none','aria-hidden':'true'});
svg.querySelector('#geography').insertBefore(terrain,svg.querySelector('#outline'));
const edge=el('path',{fill:'none',stroke:'#526a66','stroke-width':2,'pointer-events':'none'},terrain);
function render(){
 for(const r of MAP_DATA.regions){const v=r.variants[mode];regions.get(r.id).setAttribute('d',v.path);const l=labels.get(r.id);l.setAttribute('x',v.label[0]);l.setAttribute('y',v.label[1]);}
 svg.querySelector('#outline').setAttribute('d',MAP_DATA.variants[mode].outline);
 const v=NANCHANG_LANDSCAPE.variants[mode];clipPath.setAttribute('d',v.clip);terrain.replaceChildren();
 for(const layer of v.layers)el('path',{d:layer.path,fill:layer.fill,'fill-rule':'evenodd'},terrain);
 const mark=el('g',{transform:`translate(${v.landmark[0]} ${v.landmark[1]})`,fill:'#a84c33',stroke:'#a84c33','stroke-width':.7},terrain);
 el('path',{d:'M-3 0 L0-1.8 L3 0 Z M-2.2 1 L0-.2 L2.2 1 Z M-1.8 1.2 V3.3 H1.8 V1.2 Z'},mark);
 edge.setAttribute('d',v.clip);terrain.append(edge);
 const visible=document.querySelector('#landscape-toggle').checked;terrain.style.display=visible?'':'none';const label=labels.get('360100');label.setAttribute('font-size',visible?15:21);if(visible){label.setAttribute('x',v.label[0]);label.setAttribute('y',v.label[1]);}
 // Selection outline stays above the illustration, without hiding its layers.
 if(selected==='360100')edge.setAttribute('stroke','#c15d35');else edge.setAttribute('stroke','#526a66');
}
const originalSelect=select;select=function(r){originalSelect(r);edge.setAttribute('stroke',selected==='360100'?'#c15d35':'#526a66');edge.setAttribute('stroke-width',selected==='360100'?3:2);};
document.querySelector('#variant').addEventListener('change',e=>{mode=e.target.value;render();});
document.querySelector('#landscape-toggle').addEventListener('change',render);
document.querySelector('#reset').addEventListener('click',()=>select(null));render();
document.querySelector('#export').addEventListener('click',async()=>{
 const button=document.querySelector('#export');button.disabled=true;let sourceUrl;
 try{await document.fonts.ready;const copy=svg.cloneNode(true);copy.setAttribute('viewBox','0 0 1660 2040');copy.setAttribute('width','3320');copy.setAttribute('height','4080');copy.querySelectorAll('[tabindex]').forEach(n=>{n.removeAttribute('tabindex');n.removeAttribute('role');});
 sourceUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=sourceUrl;});const c=document.createElement('canvas');c.width=3320;c.height=4080;const ctx=c.getContext('2d');if(!ctx)throw Error('canvas unavailable');ctx.drawImage(img,0,0);const blob=await new Promise(resolve=>c.toBlob(resolve,'image/png'));if(!blob)throw Error('export failed');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='中国旅行地图-南昌山水.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status.textContent='已导出完整地图，包含当前显示的南昌地貌。';
 }catch(e){status.textContent='导出失败，请重试。';console.error(e);}finally{if(sourceUrl)URL.revokeObjectURL(sourceUrl);button.disabled=false;}
});
