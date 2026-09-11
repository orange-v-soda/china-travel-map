'use strict';
const REFERENCE_MAP=SOURCE_REFERENCE;
const NS='http://www.w3.org/2000/svg';
const palette=[['#2864dc','蓝色'],['#e65b4e','红色'],['#f4bf45','黄色'],['#299b7d','绿色'],['#9870c8','紫色'],['#ffffff','白色（擦除）']];
const colors=Object.fromEntries(MAP_DATA.regions.map(r=>[r.id,'#ffffff']));
let active=palette[0][0];
const svg=document.querySelector('#map');
const status=document.querySelector('#status');
const regionElements=new Map(),labelElements=new Map();
const referenceElements=new Map(),referenceLabels=new Map();
let mode=MAP_DATA.defaultVariant;
// Clone the empty SVG frame; each map has its own accessible identifiers.
const referenceSvg=svg.cloneNode(true);
for(const el of [referenceSvg,...referenceSvg.querySelectorAll('[id]')])el.id='reference-'+el.id;
referenceSvg.setAttribute('aria-labelledby','reference-map-title reference-map-desc');
referenceSvg.querySelector('#reference-map-title').textContent='六省与香港、澳门、上海真实参考图';
referenceSvg.querySelector('#reference-map-desc').textContent='完整真实区划边界，与右侧同步高亮和填色。';
referenceSvg.querySelector('#reference-map-subtitle').textContent='真实区划 / REFERENCE';
referenceSvg.querySelector('#reference-map-note').textContent='完整源边界 · 参考示意';
referenceSvg.querySelector('#reference-outline').remove();
referenceSvg.querySelector('#reference-regions').setAttribute('stroke-width','2');
document.querySelector('#reference-host').append(referenceSvg);
function ink(hex){const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]>.179?'#17263b':'#ffffff';}
function count(){document.querySelector('#count').textContent=Object.values(colors).filter(c=>c!=='#ffffff').length;}
function setColor(region,color){
 colors[region.id]=color;
 for(const elements of [regionElements,referenceElements]){const p=elements.get(region.id);p.setAttribute('fill',color);p.setAttribute('aria-label',(region.fullName||region.name+'市')+'，'+(color==='#ffffff'?'未填色':'已填色')+'，按回车填色');}
 labelElements.get(region.id).setAttribute('fill',ink(color));labelElements.get(region.id).setAttribute('stroke',color);referenceLabels.get(region.id).setAttribute('fill',ink(color));referenceLabels.get(region.id).setAttribute('stroke',color);count();
}
function paint(region){setColor(region,active);status.textContent=region.name+'：两图'+(active==='#ffffff'?'已擦除':'已同步填色');}
function highlight(region,on){for(const elements of [regionElements,referenceElements])elements.get(region.id).classList.toggle('linked',on);if(on)status.textContent='正在对照：'+(region.fullName||region.name+'市');}
function makeRegion(region,d,parent,elements){
 const p=document.createElementNS(NS,'path');p.setAttribute('d',d);p.setAttribute('fill','#ffffff');p.setAttribute('fill-rule','evenodd');p.setAttribute('tabindex','0');p.setAttribute('role','button');p.dataset.city=region.id;p.setAttribute('aria-label',(region.fullName||region.name+'市')+'，未填色，按回车填色');
 p.addEventListener('click',()=>paint(region));p.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();paint(region);}});
 p.addEventListener('pointerenter',()=>highlight(region,true));p.addEventListener('pointerleave',()=>highlight(region,false));p.addEventListener('focus',()=>highlight(region,true));p.addEventListener('blur',()=>highlight(region,false));parent.append(p);elements.set(region.id,p);
}
function makeLabel(region,xy,parent,elements,halo=false){const t=document.createElementNS(NS,'text');t.setAttribute('x',xy[0]);t.setAttribute('y',xy[1]);t.setAttribute('fill','#17263b');if(halo){t.setAttribute('paint-order','stroke');t.setAttribute('stroke','#ffffff');t.setAttribute('stroke-width','3');t.setAttribute('stroke-linejoin','round');}if(['厦门','澳门'].includes(region.name))t.setAttribute('font-size','16');t.textContent=region.name;parent.append(t);elements.set(region.id,t);}
for(const region of MAP_DATA.regions){
 makeRegion(region,region.variants[mode].path,document.querySelector('#regions'),regionElements);
 makeLabel(region,region.variants[mode].label,document.querySelector('#labels'),labelElements,true);
 const real=REFERENCE_MAP.regions.find(r=>r.id===region.id);
 makeRegion(region,real.path,referenceSvg.querySelector('#reference-regions'),referenceElements);
 makeLabel(region,real.label,referenceSvg.querySelector('#reference-labels'),referenceLabels,true);
}
document.querySelector('#outline').setAttribute('d',MAP_DATA.variants[mode].outline);
function select(color){active=color.toLowerCase();for(const b of document.querySelectorAll('.swatch'))b.setAttribute('aria-pressed',String(b.dataset.color===active));document.querySelector('#custom-color').value=active;}
for(const [color,name]of palette){const b=document.createElement('button');b.type='button';b.className='swatch';b.dataset.color=color;b.style.backgroundColor=color;b.style.setProperty('--check',ink(color));b.setAttribute('aria-label',name);b.title=name;b.addEventListener('click',()=>select(color));document.querySelector('#palette').append(b);}
select(active);
document.querySelector('#custom-color').addEventListener('input',e=>select(e.target.value));
document.querySelector('#reset').addEventListener('click',()=>{for(const r of MAP_DATA.regions)setColor(r,'#ffffff');status.textContent='已清空全部颜色';});
document.querySelector('#export').addEventListener('click',async()=>{
 const button=document.querySelector('#export');button.disabled=true;status.textContent='正在生成完整图片…';let sourceUrl;
 try{
  await document.fonts.ready;
  const copy=svg.cloneNode(true);copy.setAttribute('viewBox','0 0 1660 1880');copy.setAttribute('width','3320');copy.setAttribute('height','3760');copy.querySelectorAll('[tabindex]').forEach(el=>{el.removeAttribute('tabindex');el.removeAttribute('role');});
  sourceUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));
  const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('图片渲染失败'));img.src=sourceUrl;});
  const canvas=document.createElement('canvas');canvas.width=3320;canvas.height=3760;const ctx=canvas.getContext('2d');if(!ctx)throw new Error('浏览器不支持图片导出');ctx.drawImage(img,0,0,3320,3760);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('无法生成 PNG');
  const downloadUrl=URL.createObjectURL(blob);const a=document.createElement('a');a.href=downloadUrl;a.download='中国旅行地图-港澳沪.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(downloadUrl),60000);status.textContent='已生成完整图片（3320 × 3760）';
 }catch(e){status.textContent='导出失败，请重试或更换浏览器。';console.error(e);}finally{if(sourceUrl)URL.revokeObjectURL(sourceUrl);button.disabled=false;}
});

const groups={shangrao:['上饶','景德镇','鹰潭','抚州','衢州','黄山','南平'],macau:['澳门','珠海','中山'],hongkong:['香港','深圳','东莞'],shanghai:['上海','嘉兴','宁波','舟山'],delta:['香港','澳门','广州','佛山','中山','珠海','深圳','东莞','惠州','江门'],minnan:['厦门','漳州','泉州'],chaoshan:['汕头','潮州','揭阳'],islands:['舟山','宁波']};
function focusMap(){
 const key=document.querySelector('#focus').value;let box='0 0 1660 1880';
 if(key!=='all'){
  const pts=MAP_DATA.regions.filter(r=>groups[key].includes(r.name)).flatMap(r=>Object.values(r.variants).flatMap(v=>Array.from(v.path.matchAll(/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g),m=>[Number(m[1])+500,Number(m[2])+530])));
  const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);const x=Math.min(...xs)-35,y=Math.min(...ys)-35;box=[x,y,Math.max(...xs)-x+35,Math.max(...ys)-y+35].join(' ');
 }
 for(const el of [svg,referenceSvg])el.setAttribute('viewBox',box);
}
document.querySelector('#focus').addEventListener('change',focusMap);
document.querySelector('#variant').addEventListener('change',e=>{
 mode=e.target.value;
 for(const r of MAP_DATA.regions){const v=r.variants[mode];regionElements.get(r.id).setAttribute('d',v.path);const label=labelElements.get(r.id);label.setAttribute('x',v.label[0]);label.setAttribute('y',v.label[1]);}
 document.querySelector('#outline').setAttribute('d',MAP_DATA.variants[mode].outline);
 document.querySelector('#map-subtitle').textContent=mode==='balanced'?'面积均衡试验 / AREA BALANCE':'当前版本 / BASELINE';
 document.querySelector('#map-note').textContent=mode==='balanced'?'轮廓结构保持 · 区划面积均衡示意':'当前抽象版 · 几何保持原样';
});
let balanceMetrics=new Map();
fetch('special-balanced-report.json').then(r=>{if(!r.ok)throw new Error('report unavailable');return r.json();}).then(report=>{
 balanceMetrics=new Map(report.cities.map(r=>[r.id,r]));
 document.querySelector('#balance-summary').textContent=`最大／最小图面面积：${report.beforeRatio.toFixed(2)} 倍 → ${report.afterRatio.toFixed(2)} 倍。保留全部区划连接关系与原有转角，α＝0.75，极小区划设可读面积下限。`;
}).catch(()=>{document.querySelector('#balance-summary').textContent='α＝0.75，极小区划设可读面积下限。选择局部范围，比较小区划与周围轮廓的变化。';});
const originalHighlight=highlight;
highlight=function(region,on){
 originalHighlight(region,on);const m=balanceMetrics.get(region.id);
 if(on&&m){const percent=(m.areaFactor-1)*100;status.textContent=`${region.name}：均衡后图面面积${percent>=0?'增加':'减少'} ${Math.abs(percent).toFixed(1)}%`;}
};
