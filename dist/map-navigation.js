'use strict';
// Navigate the existing SVG; its geometry and full-map export stay unchanged.
(() => {
 const map=document.querySelector('#map'),out=document.querySelector('#zoom-level');
 const plus=document.querySelector('#zoom-in'),minus=document.querySelector('#zoom-out');
 const W=1660,H=2040,MAX=12,pointers=new Map();
 let view={x:0,y:0,k:1},gesture=null,suppressUntil=0;
 map.setAttribute('tabindex','0');map.setAttribute('aria-describedby','zoom-help');
 function apply(){
  view.k=Math.max(1,Math.min(MAX,view.k));
  view.x=Math.max(0,Math.min(W-W/view.k,view.x));
  view.y=Math.max(0,Math.min(H-H/view.k,view.y));
  map.setAttribute('viewBox',`${view.x} ${view.y} ${W/view.k} ${H/view.k}`);
  out.textContent=Math.round(view.k*100)+'%';minus.disabled=view.k<=1;plus.disabled=view.k>=MAX;
 }
 function point(e){
  const r=map.getBoundingClientRect(),scale=Math.min(r.width/W,r.height/H);
  return {x:(e.clientX-r.left-(r.width-W*scale)/2)/scale,y:(e.clientY-r.top-(r.height-H*scale)/2)/scale};
 }
 function zoom(f,p={x:W/2,y:H/2}){
  const k=Math.max(1,Math.min(MAX,view.k*f));
  view.x+=p.x/view.k-p.x/k;view.y+=p.y/view.k-p.y/k;view.k=k;apply();
 }
 function reset(){view={x:0,y:0,k:1};apply();}
 plus.addEventListener('click',()=>zoom(1.5));minus.addEventListener('click',()=>zoom(1/1.5));
 document.querySelector('#zoom-reset').addEventListener('click',reset);
 map.addEventListener('wheel',e=>{
  // At the full-map lower limit, allow scrolling down the page.
  if(view.k===1&&e.deltaY>=0)return;
  e.preventDefault();const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?500:1);
  zoom(Math.exp(-Math.max(-200,Math.min(200,delta))*.0025),point(e));
 },{passive:false});
 map.addEventListener('keydown',e=>{
  if(e.altKey||e.ctrlKey||e.metaKey)return;
  if(e.key==='+'||e.key==='=')zoom(1.5);
  else if(e.key==='-')zoom(1/1.5);
  else if(e.key==='0'||e.key==='Home')reset();
  else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
   view.x+=({ArrowLeft:-100,ArrowRight:100}[e.key]||0)/view.k;
   view.y+=({ArrowUp:-100,ArrowDown:100}[e.key]||0)/view.k;apply();
  }else return;
  e.preventDefault();
 });
 function metrics(){
  const p=[...pointers.values()];
  return p.length>1?{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2,d:Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y)}:{...p[0],d:0};
 }
 function begin(){gesture=pointers.size?{...metrics(),view:{...view},moved:pointers.size>1}:null;}
 map.addEventListener('pointerdown',e=>{
  if(e.button!==0||pointers.size>=2)return;
  pointers.set(e.pointerId,{...point(e),cx:e.clientX,cy:e.clientY});begin();
  if(pointers.size>1){suppressUntil=Date.now()+500;for(const id of pointers.keys())map.setPointerCapture?.(id);}
 });
 map.addEventListener('pointermove',e=>{
  if(!pointers.has(e.pointerId)||!gesture)return;
  const old=pointers.get(e.pointerId),p=point(e);
  pointers.set(e.pointerId,{...p,cx:old.cx,cy:old.cy});
  if(!gesture.moved&&Math.hypot(e.clientX-old.cx,e.clientY-old.cy)<5)return;
  gesture.moved=true;suppressUntil=Date.now()+500;map.setPointerCapture?.(e.pointerId);
  map.classList.add('is-dragging');const m=metrics(),v=gesture.view;
  const k=gesture.d>0?Math.max(1,Math.min(MAX,v.k*m.d/gesture.d)):v.k;
  view={x:v.x+gesture.x/v.k-m.x/k,y:v.y+gesture.y/v.k-m.y/k,k};apply();
 });
 function end(e){
  if(!pointers.has(e.pointerId))return;
  if(gesture?.moved)suppressUntil=Date.now()+500;
  pointers.delete(e.pointerId);if(map.hasPointerCapture?.(e.pointerId))map.releasePointerCapture(e.pointerId);
  begin();if(!pointers.size)map.classList.remove('is-dragging');
 }
 for(const event of ['pointerup','pointercancel','lostpointercapture'])map.addEventListener(event,end);
 map.addEventListener('pointerleave',e=>{if(!map.hasPointerCapture?.(e.pointerId))end(e);});
 map.addEventListener('click',e=>{if(e.detail!==0&&Date.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}},true);
 apply();
})();
