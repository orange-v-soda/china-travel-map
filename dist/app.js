'use strict';
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
referenceSvg.querySelector('#reference-map-title').textContent='江西省真实区划参考图';
referenceSvg.querySelector('#reference-map-desc').textContent='根据市级边界数据生成的 SVG，同步高亮并标记对应城市。';
referenceSvg.querySelector('#reference-map-subtitle').textContent='真实区划 / GEOGRAPHIC REFERENCE';
referenceSvg.querySelector('#reference-map-note').textContent='边界数据：DataV.GeoAtlas · 参考示意';
referenceSvg.querySelector('#reference-outline').remove();
referenceSvg.querySelector('#reference-regions').setAttribute('stroke-width','1.4');
document.querySelector('#reference-host').append(referenceSvg);
function ink(hex){const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]>.179?'#17263b':'#ffffff';}
function count(){document.querySelector('#count').textContent=Object.values(colors).filter(c=>c!=='#ffffff').length;}
function setColor(region,color){
 colors[region.id]=color;
 for(const elements of [regionElements,referenceElements]){const p=elements.get(region.id);p.setAttribute('fill',color);p.setAttribute('aria-label',region.name+'市，'+(color==='#ffffff'?'未填色':'已填色')+'，按回车填色');}
 labelElements.get(region.id).setAttribute('fill',ink(color));labelElements.get(region.id).setAttribute('stroke',color);referenceLabels.get(region.id).setAttribute('fill',ink(color));referenceLabels.get(region.id).setAttribute('stroke',color);count();
}
function paint(region){setColor(region,active);status.textContent=region.name+'：两图'+(active==='#ffffff'?'已擦除':'已同步填色');}
function highlight(region,on){for(const elements of [regionElements,referenceElements])elements.get(region.id).classList.toggle('linked',on);if(on)status.textContent='正在对照：'+region.name+'市';}
function makeRegion(region,d,parent,elements){
 const p=document.createElementNS(NS,'path');p.setAttribute('d',d);p.setAttribute('fill','#ffffff');p.setAttribute('fill-rule','evenodd');p.setAttribute('tabindex','0');p.setAttribute('role','button');p.dataset.city=region.id;p.setAttribute('aria-label',region.name+'市，未填色，按回车填色');
 p.addEventListener('click',()=>paint(region));p.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();paint(region);}});
 p.addEventListener('pointerenter',()=>highlight(region,true));p.addEventListener('pointerleave',()=>highlight(region,false));p.addEventListener('focus',()=>highlight(region,true));p.addEventListener('blur',()=>highlight(region,false));parent.append(p);elements.set(region.id,p);
}
function makeLabel(region,xy,parent,elements,halo=false){const t=document.createElementNS(NS,'text');t.setAttribute('x',xy[0]);t.setAttribute('y',xy[1]);t.setAttribute('fill','#17263b');if(halo){t.setAttribute('paint-order','stroke');t.setAttribute('stroke','#ffffff');t.setAttribute('stroke-width','3');t.setAttribute('stroke-linejoin','round');}t.textContent=region.name;parent.append(t);elements.set(region.id,t);}
for(const region of MAP_DATA.regions){
 makeRegion(region,region.variants[mode].path,document.querySelector('#regions'),regionElements);
 makeLabel(region,region.variants[mode].label,document.querySelector('#labels'),labelElements,true);
 const real=REFERENCE_MAP.regions.find(r=>r.id===region.id);
 makeRegion(region,real.path,referenceSvg.querySelector('#reference-regions'),referenceElements);
 makeLabel(region,real.label,referenceSvg.querySelector('#reference-labels'),referenceLabels,true);
}
const iterationSelect=document.querySelector('#iteration');
const stopLabels={fixed_point:'已收敛',topology_blocked:'拓扑约束停止',cycle_detected:'检测到循环',iteration_limit:'达到迭代上限'};
const softenedOption=document.createElement('option');softenedOption.value='softened';softenedOption.textContent='去尖角 · 新版';iterationSelect.append(softenedOption);
const shortcutOption=document.createElement('option');shortcutOption.value='shortcuts';shortcutOption.textContent='长线合并 · 上一版';iterationSelect.append(shortcutOption);
for(const log of MAP_DATA.iterations){const option=document.createElement('option');option.value='iteration_'+log.iteration;option.textContent=log.iteration===0?'首次贴合':('第 '+log.iteration+' 轮'+(option.value===MAP_DATA.defaultVariant?' · '+stopLabels[MAP_DATA.convergence.status]:''));iterationSelect.append(option);}
function setMode(value){
 mode=value;
 for(const region of MAP_DATA.regions){const variant=region.variants[mode];regionElements.get(region.id).setAttribute('d',variant.path);labelElements.get(region.id).setAttribute('x',variant.label[0]);labelElements.get(region.id).setAttribute('y',variant.label[1]);}
 const softened=mode==='softened';const compact=softened||mode==='shortcuts';const iteration=Number(mode.split('_')[1]);const record=softened?MAP_DATA.angleReport:(compact?MAP_DATA.shortcutReport:MAP_DATA.iterations[iteration]);
 document.querySelector('#outline').setAttribute('d',MAP_DATA.variants[mode].outline);
 document.querySelector('#map-subtitle').textContent=softened?'45°去尖角 / SOFTENED MAP':compact?'45°长线合并 / SIMPLIFIED MAP':'45°迭代规整 / PASS '+iteration;
 document.querySelector('#iteration-caption').textContent=softened?('全图 '+record.afterScore[1]+' 个转角 · '+record.afterScore[0]+' 个锐角 · 忽略极小离散地块'):compact?'全图 '+record.afterTurns.reduce((a,b)=>a+b,0)+' 个转角 · 共享边界统一合并 · 19 对市际邻接':('第 '+iteration+' 轮 · 路径坐标点 '+record.vertices+' · 19 对市际邻接');
 iterationSelect.value=mode;
}
iterationSelect.addEventListener('change',()=>{setMode(iterationSelect.value);status.textContent='已切换地图版本，颜色保留';});
setMode(mode);
function select(color){active=color.toLowerCase();for(const b of document.querySelectorAll('.swatch'))b.setAttribute('aria-pressed',String(b.dataset.color===active));document.querySelector('#custom-color').value=active;}
for(const [color,name]of palette){const b=document.createElement('button');b.type='button';b.className='swatch';b.dataset.color=color;b.style.backgroundColor=color;b.style.setProperty('--check',ink(color));b.setAttribute('aria-label',name);b.title=name;b.addEventListener('click',()=>select(color));document.querySelector('#palette').append(b);}
select(active);
document.querySelector('#custom-color').addEventListener('input',e=>select(e.target.value));
document.querySelector('#reset').addEventListener('click',()=>{for(const r of MAP_DATA.regions)setColor(r,'#ffffff');status.textContent='已清空全部颜色';});
document.querySelector('#export').addEventListener('click',async()=>{
 const button=document.querySelector('#export');button.disabled=true;status.textContent='正在生成完整图片…';let sourceUrl;
 try{
  await document.fonts.ready;
  const exportMode=mode;const copy=svg.cloneNode(true);copy.setAttribute('width','1520');copy.setAttribute('height','1720');copy.querySelectorAll('[tabindex]').forEach(el=>{el.removeAttribute('tabindex');el.removeAttribute('role');});
  sourceUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));
  const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('图片渲染失败'));img.src=sourceUrl;});
  const canvas=document.createElement('canvas');canvas.width=1520;canvas.height=1720;const ctx=canvas.getContext('2d');if(!ctx)throw new Error('浏览器不支持图片导出');ctx.drawImage(img,0,0,1520,1720);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('无法生成 PNG');
  const downloadUrl=URL.createObjectURL(blob);const a=document.createElement('a');a.href=downloadUrl;a.download='中国旅行地图-江西-'+(exportMode==='softened'?'45度去尖角':exportMode==='shortcuts'?'45度长线合并':('45度规整-第'+exportMode.split('_')[1]+'轮'))+'.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(downloadUrl),60000);status.textContent='已生成完整图片（1520 × 1720）';
 }catch(e){status.textContent='导出失败，请重试或更换浏览器。';console.error(e);}finally{if(sourceUrl)URL.revokeObjectURL(sourceUrl);button.disabled=false;}
});
