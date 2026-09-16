// Deterministic SVG geometry owns each tile; ImageGen only supplies interior paint.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const sharp=require('/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'dist');
const data=JSON.parse(fs.readFileSync(path.join(dist,'jiangxi-art-data.js'),'utf8').split(' = ')[1].replace(/;\s*$/,''));
const [action,id,layout='balanced',input]=process.argv.slice(2);
const shared=JSON.parse(fs.readFileSync(path.join(root,'data/jiangxi-shared-labels.json'))).features;
const sharedLabelPolicy={allowed:shared.filter(f=>f.ownerCity===id).map(f=>f.name),doNotRepeat:shared.filter(f=>f.ownerCity!==id).map(f=>f.name)};
if(!['east','balanced'].includes(layout))throw Error('Unknown layout');
const city=data.cities.find(c=>c.id===id);if(!city)throw Error('Unknown city');
const dir=path.join(dist,'assets/jiangxi/city-jobs',id,layout);fs.mkdirSync(dir,{recursive:true});
const digest=s=>crypto.createHash('sha256').update(s).digest('hex');
const coords=[...city[layout].matchAll(/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g)].map(m=>[+m[1],+m[2]]);
const xs=coords.map(p=>p[0]),ys=coords.map(p=>p[1]);
const side=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys))*1.25;
const bounds=[(Math.max(...xs)+Math.min(...xs)-side)/2,(Math.max(...ys)+Math.min(...ys)-side)/2,side,side];
const href=p=>'data:image/png;base64,'+fs.readFileSync(p).toString('base64');
const image=(h,b)=>`<image href="${h}" x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}" preserveAspectRatio="none"/>`;
const wrap=body=>`<svg xmlns="http://www.w3.org/2000/svg" width="1536" height="1536" viewBox="${bounds.join(' ')}">${body}</svg>`;
const target=`<clipPath id="target" clipPathUnits="userSpaceOnUse"><path d="${city[layout]}"/></clipPath>`;
(async()=>{
 if(action==='prepare'){
  let defs=target+`<g id="source">${image(href(path.join(dist,'assets/jiangxi/geographic-guide.png')),data.bounds)}</g>`,geo='';
  for(const c of data.cities){
   defs+=`<clipPath id="city${c.id}" clipPathUnits="userSpaceOnUse"><path d="${c[layout]}"/></clipPath>`;
   let interior='';
   if(layout==='east')interior='<use href="#source"/>';
   else data.cells.forEach((t,i)=>{if(t.id!==c.id)return;defs+=`<clipPath id="tri${i}" clipPathUnits="userSpaceOnUse"><path d="${t.clip}"/></clipPath>`;interior+=`<g clip-path="url(#tri${i})"><use href="#source" transform="matrix(${t.matrix.join(' ')})"/></g>`;});
   geo+=`<g clip-path="url(#city${c.id})">${interior}</g>`;
  }
  // Only explicitly accepted, same-layout outputs may provide painted neighbors.
  const manifestPath=path.join(dist,'jiangxi-city-tiles.json');
  const manifest=fs.existsSync(manifestPath)?JSON.parse(fs.readFileSync(manifestPath)):[];
  const neighbors=[];
  for(const t of manifest){if(t.id===id||t.layout!==layout||t.status!=='accepted')continue;
   const c=data.cities.find(c=>c.id===t.id);if(!c||t.pathSha256!==digest(c[layout]))throw Error('Stale neighbor geometry');
   if(t.bounds[0]>bounds[0]+side||t.bounds[1]>bounds[1]+side||t.bounds[0]+t.bounds[2]<bounds[0]||t.bounds[1]+t.bounds[3]<bounds[1])continue;
   geo+=`<g clip-path="url(#city${t.id})">${image(href(path.join(dist,t.image)),t.bounds)}</g>`;neighbors.push(t.id);
  }
  const mask=wrap(`<path d="${city[layout]}" fill="white"/>`);
  const context=wrap(`<defs>${defs}</defs><rect x="${bounds[0]}" y="${bounds[1]}" width="${side}" height="${side}" fill="#eeeae0"/>${geo}<path d="${city[layout]}" fill="none" stroke="#cf4935" stroke-width=".6" stroke-dasharray="2 1"/>`);
  const proof=wrap(`<defs>${defs}</defs><g clip-path="url(#target)">${geo}</g>`);
  fs.writeFileSync(path.join(dir,'context.svg'),context);fs.writeFileSync(path.join(dir,'boundary-proof.svg'),proof);
  await sharp(Buffer.from(mask)).png().toFile(path.join(dir,'mask.png'));
  await sharp(Buffer.from(context)).png().toFile(path.join(dir,'context.png'));
  await sharp(Buffer.from(proof)).png().toFile(path.join(dir,'boundary-proof.png'));
  fs.writeFileSync(path.join(dir,'job.json'),JSON.stringify({id,layout,bounds,sharedLabelPolicy,width:1536,height:1536,path:city[layout],pathSha256:digest(city[layout]),neighbors,status:'prepared',requirement:'Generate using context.png without recropping. Final output is clipped by the stored exact SVG path. No cross-layout reuse.'},null,2));
 }else if(action==='finalize'){
  if(!input)throw Error('Input PNG required');
  const job=JSON.parse(fs.readFileSync(path.join(dir,'job.json')));
  if(job.pathSha256!==digest(city[layout])||JSON.stringify(job.bounds)!==JSON.stringify(bounds))throw Error('Stale geometry; prepare again');
  const info=await sharp(input).metadata();if(info.width!==info.height)throw Error('Changed canvas aspect ratio');
  // This SVG is authoritative for display and export; outside is truly transparent.
  const svg=wrap(`<defs>${target}</defs><g clip-path="url(#target)">${image(href(input),bounds)}</g>`);
  fs.writeFileSync(path.join(dir,'tile.svg'),svg);
  await sharp(Buffer.from(svg)).png().toFile(path.join(dir,'tile.png'));
  const mask=await sharp(path.join(dir,'mask.png')).ensureAlpha().raw().toBuffer();
  const pixels=await sharp(path.join(dir,'tile.png')).ensureAlpha().raw().toBuffer();
  let outside=0,interior=0,uncovered=0;for(let i=3;i<pixels.length;i+=4){if(mask[i]===0&&pixels[i]!==0)outside++;if(mask[i]===255){interior++;if(pixels[i]<250)uncovered++;}}
  if(outside)throw Error(`Outside-mask pixels: ${outside}`);
  fs.writeFileSync(path.join(dir,'validation.json'),JSON.stringify({outsideMaskPixels:outside,interiorPixels:interior,uncoveredInteriorPixels:uncovered,uncoveredInteriorFraction:uncovered/interior,pathSha256:job.pathSha256,layout,status:'geometry-validated-content-review-required',note:'Clipping verifies containment, not geographic accuracy of generated content.'},null,2));
 }else throw Error('Use prepare or finalize');
 console.log(dir);
})().catch(e=>{console.error(e);process.exit(1)});
