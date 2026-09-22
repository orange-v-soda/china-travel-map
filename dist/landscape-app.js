'use strict';
const NS='http://www.w3.org/2000/svg',svg=document.querySelector('#map'),status=document.querySelector('#status');
const referenceSvg=svg.cloneNode(true),regions=new Map(),labels=new Map(),references=new Map();
let mode='balanced',selected=null,layer='art';
const jiangxiIds=new Set(JIANGXI_ART.cities.map(r=>r.id));
for(const n of [referenceSvg,...referenceSvg.querySelectorAll('[id]')])n.id='reference-'+n.id;
referenceSvg.setAttribute('aria-labelledby','reference-map-title reference-map-desc');
referenceSvg.querySelector('#reference-map-title').textContent='完整真实区划参考';
referenceSvg.querySelector('#reference-map-desc').textContent='原始行政区划轮廓。';
referenceSvg.querySelector('#reference-map-subtitle').textContent='真实区划 / REFERENCE';
referenceSvg.querySelector('#reference-map-note').textContent='完整源边界 · 参考示意';
referenceSvg.querySelector('#reference-outline').remove();document.querySelector('#reference-host').append(referenceSvg);
function el(tag,attrs={},parent){const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(parent)parent.append(n);return n;}
const descriptions={
 '360100':'南昌：赣江穿城，西北为梅岭，东北连接鄱阳湖平原；滕王阁位于赣江东岸。',
 '360200':'景德镇：昌江河谷中的瓷都；御窑以红砖窑拱和瓷器意象呈现。',
 '360300':'萍乡：赣西城镇与武功山高山草甸；山地延续至宜春、吉安。',
 '360400':'九江：长江南岸、鄱阳湖西北，庐山耸立于湖西；修水从西部汇入湖区。',
 '360500':'新余：袁河沿线城镇与西南仙女湖，周边为丘陵与田野。',
 '360600':'鹰潭：信江河谷与龙虎山丹霞，红色山崖沿河展开。',
 '360700':'赣州：章江、贡江汇成赣江，古城与浮桥点缀河岸；赣南丘陵连绵。',
 '360800':'吉安：赣江贯穿盆地，西南为井冈山，山林与河谷连续展开。',
 '360900':'宜春：袁河、锦江及赣西丘陵，南部明月山与武功山山系相接。',
 '361000':'抚州：抚河串起城镇与田野，文昌里在河岸，东部连接武夷山地。',
 '361100':'上饶：信江河谷、鄱阳湖东岸、三清山花岗岩峰与婺源村落。'
};
function select(r){selected=r?.id||null;for(const map of[regions,references])for(const[id,p]of map)p.setAttribute('aria-pressed',String(id===selected));status.textContent=r?(descriptions[r.id]||`${r.fullName||r.name}：已保留原区划，本轮艺术绘制范围为江西。`):'江西 11 市山川与城镇；点击区划查看说明。';}
function makeRegion(r,path,parent,map){const n=el('path',{d:path,fill:map===regions&&jiangxiIds.has(r.id)?'transparent':'#fff','fill-rule':'evenodd',tabindex:0,role:'button','data-city':r.id,'aria-pressed':'false','aria-label':`${r.fullName||r.name}，选择区划`},parent);n.addEventListener('click',()=>select(r));n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(r);}});for(const event of['pointerenter','focus'])n.addEventListener(event,()=>{regions.get(r.id)?.classList.add('linked');references.get(r.id)?.classList.add('linked');});for(const event of['pointerleave','blur'])n.addEventListener(event,()=>{regions.get(r.id)?.classList.remove('linked');references.get(r.id)?.classList.remove('linked');});map.set(r.id,n);}
for(const r of MAP_DATA.regions){
 makeRegion(r,r.variants[mode].path,svg.querySelector('#regions'),regions);
 const t=el('text',{x:r.variants[mode].label[0],y:r.variants[mode].label[1],fill:'#203832','paint-order':'stroke',stroke:'#fff','stroke-width':3,'stroke-opacity':.9},svg.querySelector('#labels'));t.textContent=r.name;if(['厦门','澳门'].includes(r.name))t.setAttribute('font-size',16);labels.set(r.id,t);
 const ref=SOURCE_REFERENCE.regions.find(x=>x.id===r.id);makeRegion(r,ref.path,referenceSvg.querySelector('#reference-regions'),references);const rt=el('text',{x:ref.label[0],y:ref.label[1],fill:'#17263b'},referenceSvg.querySelector('#reference-labels'));rt.textContent=r.name;
}
const defs=el('defs',{},svg),image=el('image',{id:'jiangxi-texture',x:JIANGXI_ART.bounds[0],y:JIANGXI_ART.bounds[1],width:JIANGXI_ART.bounds[2],height:JIANGXI_ART.bounds[3],preserveAspectRatio:'none'},defs);
const clip=el('clipPath',{id:'jiangxi-art-clip',clipPathUnits:'userSpaceOnUse'},defs);
const terrain=el('g',{id:'jiangxi-artwork','clip-path':'url(#jiangxi-art-clip)','pointer-events':'none','aria-hidden':'true'});
svg.querySelector('#geography').insertBefore(terrain,svg.querySelector('#regions'));
const meshClips=[],cityClips=new Map(),tileDefs=el('g',{},defs);
let cityTiles=[];
for(const city of JIANGXI_ART.cities){const cp=el('clipPath',{id:`jiangxi-city-${city.id}`,clipPathUnits:'userSpaceOnUse'},defs);cityClips.set(city.id,el('path',{d:city[mode]},cp));}
fetch('jiangxi-city-tiles.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('tile manifest');return r.json();}).then(tiles=>{cityTiles=tiles;render();}).catch(()=>{});
JIANGXI_ART.cells.forEach((cell,i)=>{const cp=el('clipPath',{id:`jiangxi-cell-${i}`,clipPathUnits:'userSpaceOnUse'},defs);el('path',{d:cell.clip},cp);meshClips.push(cp);});
const assetCache=new Map();
function loadAsset(url){if(!assetCache.has(url))assetCache.set(url,fetch(url,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(`Image ${r.status}`);return r.blob();}).then(blob=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);})).catch(e=>{assetCache.delete(url);throw e;}));return assetCache.get(url);}
function render(){
 for(const r of MAP_DATA.regions){const v=r.variants[mode];regions.get(r.id).setAttribute('d',v.path);regions.get(r.id).setAttribute('fill',jiangxiIds.has(r.id)&&layer!=='none'?'transparent':'#fff');const t=labels.get(r.id);t.setAttribute('x',v.label[0]);t.setAttribute('y',v.label[1]);t.setAttribute('font-size',jiangxiIds.has(r.id)?15:21);}
 svg.querySelector('#outline').setAttribute('d',MAP_DATA.variants[mode].outline);clip.replaceChildren();
 for(const city of JIANGXI_ART.cities)el('path',{d:city[mode]},clip);
 terrain.replaceChildren();terrain.style.display=layer==='none'?'none':'';
 image.setAttribute('href',JIANGXI_ART.images[layer==='geography'?'geography':'art']);
 tileDefs.replaceChildren();
 for(const city of JIANGXI_ART.cities){
  cityClips.get(city.id).setAttribute('d',city[mode]);
  const cityGroup=el('g',{'clip-path':`url(#jiangxi-city-${city.id})`},terrain);
  const tile=layer==='art'&&cityTiles.find(t=>t.id===city.id&&t.layout===mode&&t.status==='accepted'&&t.path===city[mode]);
  if(tile){
   const b=tile.bounds;el('image',{href:tile.image,x:b[0],y:b[1],width:b[2],height:b[3],preserveAspectRatio:'none'},cityGroup);
  }else if(mode==='east')el('use',{href:'#jiangxi-texture'},cityGroup);
  else JIANGXI_ART.cells.forEach((cell,i)=>{if(cell.id!==city.id)return;const group=el('g',{'clip-path':`url(#jiangxi-cell-${i})`},cityGroup);el('use',{href:'#jiangxi-texture',transform:`matrix(${cell.matrix.join(' ')})`},group);});
 }
 document.querySelector('#map-subtitle').textContent=layer==='geography'?'江西山川与城镇 · 地理依据 / GEOGRAPHIC GUIDE':'江西山河 · 艺术底图 / JIANGXI';
 document.querySelector('#map-note').textContent=layer==='geography'?'高程 · 河网 · 湖泊 · 历史城镇范围；沿既有区划作示意映射':'依据地理数据绘制 · 地标示意放大 · 保留既有区划';
 document.querySelector('#layer-caption').textContent=layer==='geography'?'地理依据：实际高程、河网、湖泊与历史城镇范围，按原区划示意映射。':layer==='none'?'原 98 区划边界与面积均衡结果。':(mode==='balanced'?'南昌与九江已采用统一比例、独立生成的手绘底图；其余江西城市正在逐区更新。':'原始布局参考；南昌、九江独立底图请切换至面积均衡布局查看。');
 svg.querySelector('#regions').setAttribute('stroke','#536b5e');svg.querySelector('#regions').setAttribute('stroke-width','1.15');svg.querySelector('#outline').setAttribute('stroke','#31483f');svg.querySelector('#outline').setAttribute('stroke-width','1.8');
 const current=image.getAttribute('href');loadAsset(current).catch(()=>{if(image.getAttribute('href')===current)status.textContent='图像加载失败，请刷新重试。';});
}
document.querySelector('#variant').addEventListener('change',e=>{mode=e.target.value;render();});
document.querySelector('#landscape-layer').addEventListener('change',e=>{layer=e.target.value;render();});
document.querySelector('#reset').addEventListener('click',()=>select(null));
document.querySelector('#zoom-jiangxi').addEventListener('click',()=>{const points=JIANGXI_ART.cells.flatMap(c=>mode==='balanced'?c.to:c.from),xs=points.map(p=>p[0]+500),ys=points.map(p=>p[1]+690);svg.dispatchEvent(new CustomEvent('map-focus',{detail:{x:Math.min(...xs)-28,y:Math.min(...ys)-28,width:Math.max(...xs)-Math.min(...xs)+56,height:Math.max(...ys)-Math.min(...ys)+56}}));});
render();
document.querySelector('#export').addEventListener('click',async()=>{
 const button=document.querySelector('#export');button.disabled=true;let sourceUrl;
 try{await document.fonts.ready;const copy=svg.cloneNode(true);copy.setAttribute('viewBox','0 0 1660 2040');copy.setAttribute('width','3320');copy.setAttribute('height','4080');copy.removeAttribute('tabindex');const exportLabels=copy.querySelector('#labels');exportLabels.setAttribute('opacity','1');exportLabels.setAttribute('aria-hidden','false');copy.querySelectorAll('[tabindex]').forEach(n=>{n.removeAttribute('tabindex');n.removeAttribute('role');});
 // Inline the cloned layer's exact image before serializing. External SVG images
 // otherwise disappear or taint canvas; later control changes cannot race the export.
 await Promise.all([...copy.querySelectorAll('image')].map(async copiedImage=>{const href=copiedImage.getAttribute('href');if(href&&!href.startsWith('data:'))copiedImage.setAttribute('href',await loadAsset(href));}));
 copy.querySelectorAll('.linked').forEach(n=>n.classList.remove('linked'));
 sourceUrl=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=sourceUrl;});const c=document.createElement('canvas');c.width=3320;c.height=4080;const ctx=c.getContext('2d');if(!ctx)throw Error('canvas unavailable');ctx.drawImage(img,0,0);const blob=await new Promise(resolve=>c.toBlob(resolve,'image/png'));if(!blob)throw Error('export failed');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='中国旅行地图-江西山河.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status.textContent='已导出完整 98 区划地图，包含当前江西图层。';
 }catch(e){status.textContent='导出失败，请重试。';console.error(e);}finally{if(sourceUrl)URL.revokeObjectURL(sourceUrl);button.disabled=false;}
});
