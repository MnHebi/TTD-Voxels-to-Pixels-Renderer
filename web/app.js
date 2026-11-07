// SPDX-License-Identifier: GPL-2.0-only
"use strict";
const $ = id => document.getElementById(id);
const clone = value => structuredClone(value);
let project, token, palettes, reserved, result, spriteImage, referenceImage;
let view = "sprite", tool = "raise", paint = "#648b39", paintTag = 0;
let undo = [], redo = [], tiles = [], libraries = [], activeLibrary = "", page = 0, libraryTotal = 0;
let version = 0, renderedVersion = -1, rendering = false, renderTimer, toastTimer, searchTimer;
let hitRect, stageScale = 1, stroke = null, pendingSave, fitFactor = 1;
let spriteTargets=[], sampleIndicesImage, sampling=false;
const pixelCache=new WeakMap();
let selectedReferenceKey = null;
let selectedPart=0;
let buildingPending=0;
const isBuilding=()=>project && ["building","house"].includes(project.profile);
let shapeBrush="wedge", shapeRotation=0, shapeRise=.5, shapeLabels={}, slopeNames={}, slopeOffsets={};
const canvas = $("stage"), ctx = canvas.getContext("2d");
const map = $("heightmap"), mctx = map.getContext("2d");

async function api(path, body, raw = false) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"X-Workshop-Token": token, "Content-Type": raw ? "application/octet-stream" : "application/json"},
    body: raw ? body : JSON.stringify(body)
  });
  if (!response.ok) {
    let message = `Operation failed (${response.status})`;
    try { message = (await response.json()).error || message; } catch (_) {}
    throw new Error(message);
  }
  return response;
}
async function json(path, body) { return (await api(path, body)).json(); }
function toast(message, error = false) {
  $("toast").textContent = message; $("toast").classList.toggle("error", error); $("toast").hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, error ? 9500 : 3500);
}
function busy(show, title = "Working…", message = "") {
  $("busy").hidden = !show; $("busy-title").textContent = title; $("busy-message").textContent = message;
}
function checkpoint() { undo.push(clone(project)); if (undo.length > 60) undo.shift(); redo = []; updateUndo(); }
function updateUndo() { $("undo").disabled = !undo.length; $("redo").disabled = !redo.length; }
function changed() {
  version++; drawMap(); scheduleRender();
  $("status").textContent = "Unsaved changes · autosaved locally";
  clearTimeout(pendingSave); pendingSave = setTimeout(() => {
    try { localStorage.setItem("voxel-terrain-project", JSON.stringify({current: project, tiles})); }
    catch (_) { $("status").textContent = "Local storage full · save your project to a file"; }
  }, 700);
}
function scheduleRender() { clearTimeout(renderTimer); renderTimer = setTimeout(refreshRender, 110); }
function loadImage(data) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error("Cannot display sprite image")); image.src = "data:image/png;base64," + data; }); }
async function refreshRender() {
  if (rendering) return;
  rendering = true; $("rendering").hidden = false;
  const submittedVersion = version;
  try {
    const r = await json("/api/render", project);
    const [im,indices] = await Promise.all([loadImage(r.png),loadImage(r.sample_indices_png)]);
    if (submittedVersion === version) {
      result = r; spriteImage = im; sampleIndicesImage=indices; renderedVersion = submittedVersion;
      referenceImage = project.reference ? await loadImage(project.reference.png) : null;
      $("sprite-metrics").textContent = `${r.width} × ${r.height} px  ·  offset ${r.offset[0]}, ${r.offset[1]}  ·  ${project.zoom}×`;
      $("colour-badge").textContent = project.colour_mode === "8bpp" ? "8bpp PALETTE" : project.colour_mode === "both" ? "RGB + 8bpp EXPORT" : "32bpp RGB";
      const notes = [];
      if (r.clipped) notes.push(`${r.clipped.toLocaleString()} pixels clipped to the ground footprint`);
      if (r.uncovered) notes.push(`${r.uncovered.toLocaleString()} texture samples use painted material`);
      if (r.missing_ground) notes.push(`${r.missing_ground.toLocaleString()} ground pixels have no surface · fix the boundary or use object placement before exporting`);
      if (project.profile === "object" || isBuilding()) notes.push(`Sorting volume: ${r.bounds.xextent} × ${r.bounds.yextent} × ${r.bounds.zextent} game units`);
      if (isBuilding()) notes.push(`${r.footprint.join(" × ")} tile lot · each tile exports separately · ${project.profile==="house"?"town house with four construction stages":"placeable decorative building"}`);
      else if (!r.tiling.compatible) notes.push("Opposite edges differ · use complementary tiles to join this shape");
      $("render-notes").textContent = notes.join(" · ") || "Ground silhouette preserved. Each exported sprite keeps the north tile corner as its origin.";
      drawStage();
    }
  } catch (error) { if (submittedVersion === version) toast(error.message, true); }
  finally {
    rendering = false; $("rendering").hidden = true;
    if (submittedVersion !== version) scheduleRender();
  }
}

function resizeStage() {
  const rect = canvas.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  canvas.width = Math.round(rect.width*dpr); canvas.height = Math.round(rect.height*dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); drawStage();
}
function drawStage() {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height); hitRect = null;spriteTargets=[];
  if (!spriteImage || !result) return;
  ctx.imageSmoothingEnabled = false;
  const zoom = project.zoom, r = result;
  const multi = view === "tiling" && !isBuilding(), compare = view === "compare";
  const lotX=isBuilding()?r.footprint[0]*16:16,lotY=isBuilding()?r.footprint[1]*16:16;
  const maxWidth = multi ? zoom*220 : compare ? width*.42 : Math.max(zoom*110, r.width);
  stageScale = Math.min((multi ? width*.90 : compare ? width*.42 : width*.75)/ (multi ? maxWidth : Math.max(r.width,zoom*64)),
    height*.78/(multi ? zoom*110+Math.max(0, r.height-zoom*32) : Math.max(r.height,zoom*54))) * fitFactor;
  if (compare) stageScale = Math.min((width*.40)/Math.max(r.width,64*zoom), height*.70/Math.max(r.height,54*zoom))*fitFactor;
  let ox = compare ? width*.72 : width/2;
  let oy = height/2 - (r.offset[1]+r.height/2)*stageScale;
  if(multi){
    const xs=[],ys=[];
    for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++){
      const z=r.tiling.compatible?r.tiling.delta_x*x+r.tiling.delta_y*y:0;
      const px=2*(y-x)*16*zoom+r.offset[0],py=((x+y)*16-z)*zoom+r.offset[1];
      xs.push(px,px+r.width);ys.push(py,py+r.height);
    }
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    stageScale=Math.min(width*.87/(maxX-minX),height*.78/(maxY-minY))*fitFactor;
    ox=width/2-(minX+maxX)/2*stageScale;oy=height/2-(minY+maxY)/2*stageScale;
  }
  const origin = [ox, oy];
  const screen = (x,y,z=0) => [origin[0]+2*(y-x)*zoom*stageScale, origin[1]+(x+y-z)*zoom*stageScale];
  if ($("show-grid").checked) {
    ctx.lineWidth = 1; ctx.strokeStyle = "#a2b49a18";
    for (let i=-2; i<=3; i++) {
      for (const axis of [0,1]) {
        const a = axis ? screen(-32,i*16) : screen(i*16,-32);
        const b = axis ? screen(48,i*16) : screen(i*16,48);
        ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();
      }
    }
    ctx.strokeStyle = "#a6c28b70";
    ctx.beginPath(); [[0,0],[lotX,0],[lotX,lotY],[0,lotY],[0,0]].forEach((v,i) => i ? ctx.lineTo(...screen(...v)) : ctx.moveTo(...screen(...v)));ctx.stroke();
  }
  function drawSprite(im, offset, at = origin, scale = stageScale, alpha = 1) {
    ctx.globalAlpha = alpha;
    const x = Math.round(at[0]+offset[0]*scale), y = Math.round(at[1]+offset[1]*scale);
    ctx.drawImage(im,x,y,Math.round(im.width*scale),Math.round(im.height*scale));ctx.globalAlpha = 1;
    return {x,y,width:Math.round(im.width*scale),height:Math.round(im.height*scale)};
  }
  if (multi) {
    // Composite at sprite resolution first. Independently rounding nine scaled
    // transparent images can introduce display-only cracks between valid tiles.
    const placements=[];
    for (let sum=0;sum<=4;sum++) for(let y=0;y<3;y++) {
      const x=sum-y;if(x<0||x>2)continue;
      const z=r.tiling.compatible?r.tiling.delta_x*(x-1)+r.tiling.delta_y*(y-1):0;
      placements.push({x:32*(y-x)*zoom+r.offset[0],y:(16*(x+y-2)-z)*zoom+r.offset[1],center:x===1&&y===1});
    }
    const minX=Math.floor(Math.min(...placements.map(t=>t.x))),minY=Math.floor(Math.min(...placements.map(t=>t.y)));
    const maxX=Math.ceil(Math.max(...placements.map(t=>t.x+r.width))),maxY=Math.ceil(Math.max(...placements.map(t=>t.y+r.height)));
    const layer=document.createElement("canvas");layer.width=maxX-minX;layer.height=maxY-minY;
    const lc=layer.getContext("2d");lc.imageSmoothingEnabled=false;
    for(const tile of placements)lc.drawImage(spriteImage,tile.x-minX,tile.y-minY);
    const dx=Math.round(origin[0]+minX*stageScale),dy=Math.round(origin[1]+minY*stageScale);
    const dw=Math.round(layer.width*stageScale),dh=Math.round(layer.height*stageScale);
    ctx.drawImage(layer,dx,dy,dw,dh);
    const center=placements.find(t=>t.center),sx=dw/layer.width,sy=dh/layer.height;
    hitRect={x:dx+(center.x-minX)*sx,y:dy+(center.y-minY)*sy,width:r.width*sx,height:r.height*sy};
    for(const tile of placements)spriteTargets.push({source:"render",image:spriteImage,rect:{x:dx+(tile.x-minX)*sx,y:dy+(tile.y-minY)*sy,width:r.width*sx,height:r.height*sy}});
  } else {
    hitRect=drawSprite(spriteImage,r.offset);
    spriteTargets.push({source:"render",image:spriteImage,rect:hitRect});
    if(referenceImage && Number($("overlay").value)>0 && !compare) {
      const ref=project.reference, ratio=zoom/ref.scale;
      const rect=drawSprite(referenceImage,[ref.xoffset,ref.yoffset],origin,stageScale*ratio,Number($("overlay").value)/100);
      spriteTargets.push({source:"reference",image:referenceImage,rect});
    }
  }
  if (compare) {
    ctx.fillStyle="#82918c";ctx.font="10px Segoe UI";ctx.textAlign="center";
    ctx.fillText("VOXEL RENDER",width*.72,height-26);
    if(referenceImage) {
      const ref=project.reference;
      const rect=drawSprite(referenceImage,[ref.xoffset,ref.yoffset],[width*.25,oy],stageScale*zoom/ref.scale);
      spriteTargets.push({source:"reference",image:referenceImage,rect});
      ctx.fillText("ORIGINAL SPRITE",width*.25,height-26);
    } else ctx.fillText("Import a reference to compare",width*.25,height*.5);
    ctx.strokeStyle="#ffffff12";ctx.beginPath();ctx.moveTo(width*.49,55);ctx.lineTo(width*.49,height-45);ctx.stroke();
  }
  if ($("show-bounds").checked && hitRect) {
    ctx.strokeStyle="#e4ae6dcc";ctx.lineWidth=1;ctx.setLineDash([4,4]);
    ctx.strokeRect(hitRect.x-.5,hitRect.y-.5,hitRect.width+1,hitRect.height+1);ctx.setLineDash([]);
    const z=project.profile==="object"||isBuilding()?r.bounds.zextent:0;
    if(z) {
      const corners=[[0,0],[lotX,0],[lotX,lotY],[0,lotY]];
      ctx.strokeStyle="#a2c9e299";
      for(let i=0;i<4;i++) {
        const a=screen(...corners[i]),b=screen(...corners[i],z),c=screen(...corners[(i+1)%4],z);
        ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.lineTo(...c);ctx.stroke();
      }
    }
    ctx.fillStyle="#e4ae6d";ctx.beginPath();ctx.arc(...origin,3,0,Math.PI*2);ctx.fill();
  }
  $("stage-label").textContent=multi?(r.tiling.compatible?"3 × 3 TILE CHECK · MATCHING EDGES":"REPEATED TILES · EDGES NEED COMPLEMENTS"):compare?"REFERENCE COMPARISON":isBuilding()?`BUILDING · ${project.building.view*90}° · STAGE ${project.building.stage+1}/4`:"LIVE SPRITE";
}

function drawMap() {
  if(!project)return;
  if(isBuilding()){drawBuildingPlan();return;}
  const n=project.size, size=map.width/n, max=Math.max(8,...project.heights.map((h,i)=>h+(project.shapes[i]==="cube"?0:project.rises[i])));
  for(let y=0;y<n;y++) for(let x=0;x<n;x++) {
    const i=y*n+x,h=project.heights[i]+(project.shapes[i]==="cube"?0:project.rises[i]*.5);
    const rgb=project.colours[i].match(/[0-9a-f]{2}/gi).map(v=>parseInt(v,16));
    const light=.45+.65*h/max;
    mctx.fillStyle=`rgb(${rgb.map(v=>Math.min(255,Math.round(v*light))).join(",")})`;
    mctx.fillRect(x*size,y*size,size,size);
    mctx.strokeStyle="#0e170e55";mctx.lineWidth=1;mctx.strokeRect(x*size+.5,y*size+.5,size-1,size-1);
    if(project.shapes[i]!=="cube"){
      mctx.save();mctx.translate((x+.5)*size,(y+.5)*size);mctx.rotate(-project.rotations[i]*Math.PI/2);
      mctx.strokeStyle="#eef9daba";mctx.lineWidth=1;mctx.beginPath();mctx.moveTo(size*.26,0);mctx.lineTo(-size*.26,0);mctx.lineTo(-size*.04,-size*.19);mctx.moveTo(-size*.26,0);mctx.lineTo(-size*.04,size*.19);mctx.stroke();mctx.restore();
    }else if(n<=16 && h>0){mctx.fillStyle="#e7f2dcaa";mctx.font=`${n===8?14:9}px Consolas`;mctx.textAlign="center";mctx.fillText(Number(h.toFixed(2)),x*size+size/2,y*size+size*.7);}
  }
  $("grid-label").textContent=`${n} × ${n} columns`;
}
function eventCell(event, surface) {
  const rect=surface.getBoundingClientRect();
  if(surface===map) {
    if(isBuilding()){
      const b=project.building,x=(event.clientX-rect.left)/rect.width*b.width*16,y=(event.clientY-rect.top)/rect.height*b.depth*16;
      let best=-1,z=-1;
      b.parts.forEach((p,i)=>{if(p.visible&&x>=p.x&&x<=p.x+p.width&&y>=p.y&&y<=p.y+p.depth&&p.z+p.height>=z){best=i;z=p.z+p.height;}});
      return best;
    }
    const x=Math.floor((event.clientX-rect.left)/rect.width*project.size),y=Math.floor((event.clientY-rect.top)/rect.height*project.size);
    return x>=0&&x<project.size&&y>=0&&y<project.size?y*project.size+x:-1;
  }
  if(!hitRect || !result || renderedVersion!==version)return -1;
  const px=Math.floor((event.clientX-rect.left-hitRect.x)/hitRect.width*result.width);
  const py=Math.floor((event.clientY-rect.top-hitRect.y)/hitRect.height*result.height);
  if(px<0||py<0||px>=result.width||py>=result.height)return -1;
  return result.cells[py*result.width+px];
}
function imagePixels(image){
  if(!pixelCache.has(image)){
    const surface=document.createElement("canvas");surface.width=image.naturalWidth;surface.height=image.naturalHeight;
    const context=surface.getContext("2d",{willReadFrequently:true});context.drawImage(image,0,0);
    pixelCache.set(image,context.getImageData(0,0,surface.width,surface.height));
  }
  return pixelCache.get(image);
}
function sourcePixel(event, element, image, contain=false){
  const rect=element.getBoundingClientRect();let width=rect.width,height=rect.height,left=rect.left,top=rect.top;
  if(contain){const scale=Math.min(width/image.naturalWidth,height/image.naturalHeight);width=image.naturalWidth*scale;height=image.naturalHeight*scale;left+=(rect.width-width)/2;top+=(rect.height-height)/2;}
  const x=Math.floor((event.clientX-left)/width*image.naturalWidth),y=Math.floor((event.clientY-top)/height*image.naturalHeight);
  return x>=0&&y>=0&&x<image.naturalWidth&&y<image.naturalHeight?{x,y}:null;
}
function acceptColourSample(sample){
  if(!sample.alpha){toast("Transparent pixel · choose an opaque sprite pixel");return;}
  const preserve=$("dropper-effects").checked && sample.palette===project.palette;
  paint=sample.colour;paintTag=preserve?sample.tag:0;
  $("paint-colour").value=paint;
  if(![...$("paint-tag").options].some(o=>o.value===String(paintTag)))$("paint-tag").append(new Option(`Palette index ${paintTag}`,String(paintTag)));
  $("paint-tag").value=String(paintTag);updatePaint();
  if(isBuilding()&&project.building.parts[selectedPart]){
    $("part-colour").value=paint;
    if(![...$("part-tag").options].some(o=>o.value===String(paintTag)))$("part-tag").append(new Option(`Palette index ${paintTag}`,String(paintTag)));
    $("part-tag").value=String(paintTag);
  }
  selectTool("paint");
  toast(`${paint.toUpperCase()}${paintTag?` · palette effect ${paintTag}`:""} picked${sample.tag&&!preserve&&sample.palette!==project.palette?" · palette differs, copied RGB only":""}${isBuilding()?" · ready to paint the selected part":""}`);
}
async function sampleReferenceColour(reference,x,y){
  // Saved references carry the original indexed mask, including duplicate RGB entries.
  return json("/api/sample-reference",{project:{...project,reference,texture:"none"},x,y});
}
async function dropperAt(event){
  if(sampling||renderedVersion!==version)return;
  const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
  for(const target of [...spriteTargets].reverse()){
    const r=target.rect,px=Math.floor((x-r.x)/r.width*target.image.naturalWidth),py=Math.floor((y-r.y)/r.height*target.image.naturalHeight);
    const pixels=imagePixels(target.image);
    if(px<0||py<0||px>=pixels.width||py>=pixels.height)continue;
    const offset=(py*pixels.width+px)*4,rgba=pixels.data.slice(offset,offset+4);
    if(!rgba[3])continue;
    sampling=true;
    try{
      const sample=target.source==="reference"?await sampleReferenceColour(project.reference,px,py):{
        colour:"#"+[...rgba.slice(0,3)].map(v=>v.toString(16).padStart(2,"0")).join(""),alpha:rgba[3],palette:project.palette,
        tag:imagePixels(sampleIndicesImage).data[offset]};
      // In 8bpp output ordinary palette entries remain ordinary paint.
      if(target.source==="render"&&project.colour_mode==="8bpp"&&!reserved[project.palette].includes(sample.tag))sample.tag=0;
      if(tool==="dropper")acceptColourSample(sample);
    }catch(error){toast(error.message,true);}finally{sampling=false;}
    return;
  }
  toast("No opaque sprite pixel here · click a sprite or reference in Compare");
}
function applyBrush(cell, lower=false) {
  if(cell<0)return;
  if(isBuilding()){selectedPart=cell;syncPartEditor();drawMap();return;}
  const n=project.size,x=cell%n,y=Math.floor(cell/n),step=Number($("height-step").value),brush=Number($("brush-size").value);
  if(tool==="pick") {
    shapeBrush=project.shapes[cell];shapeRotation=project.rotations[cell];shapeRise=project.rises[cell];syncShapeBrush();
    paint=project.colours[cell];paintTag=project.tags[cell];$("paint-colour").value=paint;$("paint-tag").value=String(paintTag);updatePaint();selectTool("paint");return;
  }
  const currentTool=lower?"lower":tool;
  let modified=false;
  for(let dy=0;dy<brush;dy++) for(let dx=0;dx<brush;dx++) {
    const xx=x+dx-Math.floor((brush-1)/2),yy=y+dy-Math.floor((brush-1)/2);
    if(xx<0||xx>=n||yy<0||yy>=n)continue;
    const i=yy*n+xx;if(stroke?.seen.has(i))continue;
    stroke?.seen.add(i);
    const ceiling=64-(project.shapes[i]==="cube"?0:project.rises[i]);
    if(currentTool==="raise")project.heights[i]=Math.min(ceiling,project.heights[i]+step);
    else if(currentTool==="lower")project.heights[i]=Math.max(0,project.heights[i]-step);
    else if(currentTool==="level")project.heights[i]=Math.min(ceiling,Math.max(0,Number($("level-height").value)||0));
    else if(currentTool==="paint"){project.colours[i]=paint;project.tags[i]=paintTag;}
    else if(currentTool==="shape")setCellShape(i);
    modified=true;
  }
  if(modified)changed();
}
for(const surface of [map,canvas]) {
  surface.addEventListener("contextmenu",e=>e.preventDefault());
  surface.addEventListener("pointerdown",e=>{
    if(surface===canvas&&tool==="dropper"){e.preventDefault();if(e.button===0)dropperAt(e);return;}
    if(tool==="dropper")return;
    const cell=eventCell(e,surface);if(cell<0)return;
    e.preventDefault();surface.setPointerCapture(e.pointerId);checkpoint();stroke={seen:new Set(),lower:e.button===2};applyBrush(cell,stroke.lower);
  });
  surface.addEventListener("pointermove",e=>{
    const cell=eventCell(e,surface);
    if(cell>=0)$("hover-cell").textContent=isBuilding()?project.building.parts[cell].name:`X ${cell%project.size} · Y ${Math.floor(cell/project.size)} · base ${project.heights[cell]} · ${shapeLabels[project.shapes[cell]]||project.shapes[cell]}`;
    if(stroke)applyBrush(cell,stroke.lower);
  });
  const end=()=>{stroke=null;};surface.addEventListener("pointerup",end);surface.addEventListener("pointercancel",end);surface.addEventListener("lostpointercapture",end);
}
function selectTool(value){tool=value;stroke=null;document.body.classList.toggle("using-dropper",tool==="dropper");document.querySelectorAll("#tools button").forEach(b=>b.classList.toggle("active",b.dataset.tool===tool));$("sprite-dropper").classList.toggle("active",tool==="dropper");$("sprite-dropper").setAttribute("aria-pressed",String(tool==="dropper"));canvas.classList.toggle("dropper-active",tool==="dropper");$("sprite-grid").classList.toggle("dropper-active",tool==="dropper");}
$("sprite-dropper").onclick=()=>{selectTool(tool==="dropper"?"paint":"dropper");if(tool==="dropper")toast("Click a sprite pixel, a library thumbnail, or the reference in Compare · Esc cancels");};
$("tools").addEventListener("click",e=>{const b=e.target.closest("button");if(b)selectTool(b.dataset.tool);});
$("view-tabs").addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;view=b.dataset.view;document.querySelectorAll("#view-tabs button").forEach(v=>v.classList.toggle("active",v===b));drawStage();});
for(const id of ["show-grid","show-bounds"])$(id).addEventListener("change",drawStage);
$("reset-view").onclick=()=>{fitFactor=1;drawStage();};
canvas.addEventListener("wheel",e=>{e.preventDefault();fitFactor=Math.min(3,Math.max(.4,fitFactor*(e.deltaY<0?1.1:.9)));drawStage();},{passive:false});
$("undo").onclick=()=>{if(!undo.length)return;redo.push(clone(project));project=undo.pop();syncControls();changed();updateUndo();};
$("redo").onclick=()=>{if(!redo.length)return;undo.push(clone(project));project=redo.pop();syncControls();changed();updateUndo();};
document.addEventListener("keydown",e=>{
  if(e.target.isContentEditable||["SELECT","TEXTAREA"].includes(e.target.tagName)||(e.target.tagName==="INPUT"&&!["checkbox","range","color","button"].includes(e.target.type)))return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="z"){e.preventDefault();$(e.shiftKey?"redo":"undo").click();}
  else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="y"){e.preventDefault();$("redo").click();}
  else if(!e.ctrlKey&&!e.metaKey){const t={r:"raise",l:"lower",p:"paint",f:"level",i:"dropper",m:"pick",g:"shape",escape:"paint"}[e.key.toLowerCase()];if(t)selectTool(t);else if(e.key.toLowerCase()==="t")$("rotate-shape").click();}
});

const lightDefs=[
  ["azimuth","Sun direction",0,360,1,"°"],["elevation","Sun elevation",5,90,1,"°"],
  ["ambient","Ambient fill",0,100,100,"%"],["strength","Sunlight",0,150,100,"%"],
  ["shadows","Voxel shadows",0,100,100,"%"],["ao","Ambient occlusion",0,60,100,"%"]
];
for(const [key,label,min,max,divisor,unit] of lightDefs) {
  const row=document.createElement("div");row.className="range-label";
  const lab=document.createElement("label");lab.htmlFor=`light-${key}`;lab.textContent=label;
  const output=document.createElement("output");output.id=`light-${key}-value`;
  row.append(lab,output);
  const input=document.createElement("input");input.type="range";input.id=`light-${key}`;input.min=min;input.max=max;
  input.addEventListener("pointerdown",checkpoint);
  input.addEventListener("keydown",e=>{if(e.key.startsWith("Arrow"))checkpoint();});
  input.oninput=()=>{project.light[key]=Number(input.value)/divisor;output.textContent=input.value+unit;changed();};
  $("light-controls").append(row,input);
}
function updatePaint(){ $("paint-value").textContent=paintTag?`INDEX ${paintTag}`:paint.toUpperCase(); }
function drawPalette(){
  $("palette-swatches").replaceChildren();
  const pal=palettes[project.palette];
  for(let i=0;i<256;i++) {
    const b=document.createElement("button"),rgb=pal.slice(i*3,i*3+3),hex="#"+rgb.map(v=>v.toString(16).padStart(2,"0")).join("");
    b.style.backgroundColor=hex;b.title=`${i} · ${hex}`;b.setAttribute("aria-label",`Palette colour ${i}`);b.disabled=reserved[project.palette].includes(i);
    b.onclick=()=>{paint=hex;paintTag=0;$("paint-colour").value=hex;$("paint-tag").value="0";updatePaint();selectTool("paint");};
    $("palette-swatches").append(b);
  }
}
function syncControls(){
  $("project-name").value=project.name;$("resolution").value=project.size;$("profile").value=project.profile;
  $("palette").value=project.palette;$("dither").checked=project.dither;$("texture").value=project.texture;
  $("palette-mapping").value=project.palette_mapping;
  $("preview-zoom").value=project.zoom;$("replacement-id").value=targetId(project);
  $("replacement-id").disabled=project.terrain_slope!==null;
  $("terrain-base").value=project.terrain_base;$("terrain-base").disabled=project.terrain_slope===null;
  $("terrain-slope").value=project.terrain_slope===null?"":String(project.terrain_slope);
  $("texture-light").value=Math.round(project.texture_light*100);$("texture-light-value").textContent=$("texture-light").value+"%";
  $("reference-x").disabled=$("reference-y").disabled=!project.reference;
  $("reference-x").value=project.reference?.xoffset??"";$("reference-y").value=project.reference?.yoffset??"";
  document.querySelectorAll("#colour-modes button").forEach(b=>b.classList.toggle("active",b.dataset.mode===project.colour_mode));
  document.querySelectorAll("[data-zoom]").forEach(b=>b.checked=project.export_zooms.includes(Number(b.dataset.zoom)));
  for(const [key,, , ,divisor,unit] of lightDefs){$("light-"+key).value=Math.round(project.light[key]*divisor);$("light-"+key+"-value").textContent=$("light-"+key).value+unit;}
  $("profile-hint").textContent=project.profile==="ground"?(project.terrain_slope===null?"Clipped to the reference silhouette, or a flat tile footprint.":`${slopeNames[project.terrain_slope]} footprint · target base sprite ${targetId(project)}`):"Keeps raised sides. Exports a full-tile sorting box; placement on flat land.";
  if(isBuilding())$("profile-hint").textContent=project.profile==="house"?"Joins town growth with population, cargo and construction stages.":"Place through OpenTTD's Objects menu. Four selectable orientations.";
  syncBuildingControls();
  $("replacement-field").hidden=project.profile!=="ground";
  $("clear-reference").disabled=!project.reference;
  const detail=$("source-details");detail.replaceChildren();
  const label=document.createElement("span");label.className="eyebrow";label.textContent="SELECTED REFERENCE";detail.append(label);
  const p=document.createElement("p");
  p.textContent=project.reference?`${project.reference.source} · sprite ${project.reference.sprite}\n${project.reference.depth} · ${project.reference.zoom}\nOrigin ${project.reference.xoffset}, ${project.reference.yoffset}`:"No reference selected";
  p.style.whiteSpace="pre-line";detail.append(p);
  drawPalette();drawMap();updateUndo();
}
function drawBuildingPlan(){
  const b=project.building,sx=map.width/(16*b.width),sy=map.height/(16*b.depth);
  mctx.fillStyle="#27332e";mctx.fillRect(0,0,map.width,map.height);
  for(const [i,p] of [...b.parts.entries()].sort((a,c)=>(a[1].z+a[1].height)-(c[1].z+c[1].height))){
    if(!p.visible)continue;
    mctx.globalAlpha=.8;mctx.fillStyle=p.colour;mctx.fillRect(p.x*sx,p.y*sy,p.width*sx,p.depth*sy);mctx.globalAlpha=1;
    mctx.strokeStyle="#00000050";mctx.lineWidth=1;mctx.strokeRect(p.x*sx,p.y*sy,p.width*sx,p.depth*sy);
    if(p.shape!=="box"){
      mctx.strokeStyle="#eeeeee80";mctx.beginPath();
      if(p.rotation){mctx.moveTo(p.x*sx,(p.y+p.depth/2)*sy);mctx.lineTo((p.x+p.width)*sx,(p.y+p.depth/2)*sy);}
      else{mctx.moveTo((p.x+p.width/2)*sx,p.y*sy);mctx.lineTo((p.x+p.width/2)*sx,(p.y+p.depth)*sy);}mctx.stroke();
    }
  }
  mctx.strokeStyle="#ffffff50";mctx.lineWidth=1;mctx.setLineDash([4,4]);
  for(let x=0;x<=b.width;x++){mctx.beginPath();mctx.moveTo(x*16*sx,0);mctx.lineTo(x*16*sx,map.height);mctx.stroke();}
  for(let y=0;y<=b.depth;y++){mctx.beginPath();mctx.moveTo(0,y*16*sy);mctx.lineTo(map.width,y*16*sy);mctx.stroke();}mctx.setLineDash([]);
  const p=b.parts[selectedPart];if(p){mctx.strokeStyle="#f2c47d";mctx.lineWidth=2;mctx.strokeRect(p.x*sx,p.y*sy,p.width*sx,p.depth*sy);}
  $("grid-label").textContent=`${b.width} × ${b.depth} tiles · unrotated plan`;
}
function syncPartEditor(){
  const b=project.building;if(!b)return;
  selectedPart=Math.min(Math.max(0,selectedPart),Math.max(0,b.parts.length-1));
  $("building-parts").replaceChildren(...b.parts.map((p,i)=>new Option(`${p.visible?"●":"○"} ${p.name}`,String(i))));
  $("building-parts").value=String(selectedPart);$("part-count").textContent=`${b.parts.length} / 160`;
  const p=b.parts[selectedPart];$("part-editor").hidden=!p;$("delete-part").disabled=$("duplicate-part").disabled=!p;$("add-part").disabled=b.parts.length>=160;
  if(!p)return;
  for(const key of ["name","shape","x","y","z","width","depth","height","colour","tag"])$("part-"+key).value=p[key];
  if(!$("part-tag").value){$("part-tag").append(new Option(`Palette index ${p.tag}`,String(p.tag)));$("part-tag").value=String(p.tag);}
  $("part-axis").value=p.rotation;$("part-visible").checked=p.visible;
}
function syncBuildingControls(){
  const active=isBuilding();document.body.classList.toggle("building-mode",active);
  for(const id of ["terrain-section","shape-section","terrain-brush-controls","tools"])$(id).hidden=active;
  $("fill-colour").textContent=active?"Paint selected part":"Fill tile";
  $("building-section").hidden=!active;$("house-settings").hidden=project.profile!=="house";
  $("building-toolbar-hint").hidden=!active;
  $("map-title").textContent=active?"Building plan":"Height map";
  document.querySelector('[data-view="tiling"]').disabled=active;
  $("legacy").disabled=active;if(active)$("legacy").checked=false;
  if(!active)return;
  const b=project.building;
  $("building-footprint").value=`${b.width},${b.depth}`;$("building-view").value=b.view;$("building-stage").value=b.stage;$("building-views").checked=b.views===4;
  for(const key of ["population","mail","passenger_acceptance","mail_acceptance","probability","year_from","year_to"])$("house-"+key).value=b[key];
  syncPartEditor();
}
async function updateBuilding(next){
  buildingPending++;
  try{const valid=await json("/api/validate",next);checkpoint();project=valid;syncControls();changed();}
  catch(error){toast(error.message,true);syncControls();}
  finally{buildingPending--;}
}
$("apply-building").onclick=async()=>{
  try{const next=await json("/api/preset",{project,kind:"building_"+$("building-preset").value});if(project.profile==="house")next.profile="house";checkpoint();project=next;selectedPart=0;syncControls();changed();}
  catch(error){toast(error.message,true);}
};
$("building-parts").onchange=()=>{selectedPart=Number($("building-parts").value);syncPartEditor();drawMap();};
$("apply-part").onclick=()=>{
  const next=clone(project),p=next.building.parts[selectedPart];if(!p)return;
  for(const key of ["x","y","z","width","depth","height","tag"])p[key]=Number($("part-"+key).value);
  for(const key of ["name","shape","colour"])p[key]=$("part-"+key).value;
  p.rotation=Number($("part-axis").value);p.visible=$("part-visible").checked;updateBuilding(next);
};
$("add-part").onclick=()=>{
  const next=clone(project);next.building.parts.push({name:"New part",shape:"box",x:4,y:4,z:0,width:4,depth:4,height:8,colour:paint,tag:paintTag,rotation:0,visible:true});selectedPart=next.building.parts.length-1;updateBuilding(next);
};
$("duplicate-part").onclick=()=>{const next=clone(project),p=clone(next.building.parts[selectedPart]);if(!p)return;p.name+=" copy";next.building.parts.push(p);selectedPart=next.building.parts.length-1;updateBuilding(next);};
$("delete-part").onclick=()=>{const next=clone(project);next.building.parts.splice(selectedPart,1);selectedPart=Math.max(0,selectedPart-1);updateBuilding(next);};
$("building-footprint").onchange=()=>{const next=clone(project);[next.building.width,next.building.depth]=$("building-footprint").value.split(",").map(Number);updateBuilding(next);};
for(const [id,key] of [["building-view","view"],["building-stage","stage"],["building-views","views"]])$(id).onchange=()=>{const next=clone(project);next.building[key]=key==="views"?($(id).checked?4:1):Number($(id).value);updateBuilding(next);};
$("rotate-building").onclick=()=>{const next=clone(project);next.building.view=(next.building.view+1)%4;updateBuilding(next);};
for(const key of ["population","mail","passenger_acceptance","mail_acceptance","probability","year_from","year_to"])$("house-"+key).onchange=()=>{const next=clone(project);next.building[key]=Number($("house-"+key).value);updateBuilding(next);};
function bindChange(id,key,convert=v=>v){$(id).onchange=()=>{checkpoint();project[key]=convert($(id).type==="checkbox"?$(id).checked:$(id).value);syncControls();changed();};}
bindChange("project-name","name");bindChange("palette","palette");bindChange("dither","dither");bindChange("texture","texture");bindChange("preview-zoom","zoom",Number);bindChange("replacement-id","replacement_id",Number);
bindChange("palette-mapping","palette_mapping");
$("profile").onchange=async()=>{
  const profile=$("profile").value;
  try{
    let next=clone(project);
    if(["building","house"].includes(profile)&&!next.building)next=await json("/api/preset",{project:next,kind:"building_cottage"});
    next.profile=profile;checkpoint();project=next;view="sprite";document.querySelectorAll("#view-tabs button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));syncControls();changed();
  }catch(error){toast(error.message,true);syncControls();}
};
$("colour-modes").onclick=e=>{const b=e.target.closest("button");if(!b)return;checkpoint();project.colour_mode=b.dataset.mode;syncControls();changed();};
$("resolution").onchange=async()=>{
  try{const next=await json("/api/resize",{project,size:Number($("resolution").value)});checkpoint();project=next;shapeRise=8/project.size;syncShapeBrush();changed();}
  catch(error){toast(error.message,true);}finally{syncControls();}
};
function targetId(p){return p.terrain_slope===null?p.replacement_id:p.terrain_base+Number(slopeOffsets[p.terrain_slope]);}
function syncShapeBrush(){
  $("shape-brush").value=shapeBrush;$("shape-rotation").value=shapeRotation;$("shape-rise").value=shapeRise;
}
function setCellShape(i){project.shapes[i]=shapeBrush;project.rotations[i]=shapeRotation;project.rises[i]=Math.min(shapeRise,64-project.heights[i]);}
$("shape-brush").onchange=()=>{shapeBrush=$("shape-brush").value;selectTool("shape");};
$("shape-rotation").onchange=()=>{shapeRotation=Number($("shape-rotation").value);selectTool("shape");};
$("shape-rise").onchange=()=>{shapeRise=Math.min(64,Math.max(0,Number($("shape-rise").value)||0));syncShapeBrush();selectTool("shape");};
$("rotate-shape").onclick=()=>{shapeRotation=(shapeRotation+1)%4;syncShapeBrush();selectTool("shape");};
$("fill-shape").onclick=()=>{checkpoint();for(let i=0;i<project.size**2;i++)setCellShape(i);changed();};
$("terrain-base").onchange=()=>{checkpoint();project.terrain_base=Number($("terrain-base").value);syncControls();changed();};
$("apply-terrain").onclick=async()=>{
  const code=$("terrain-slope").value;
  if(code===""){checkpoint();project.terrain_slope=null;syncControls();changed();return;}
  try{const next=await json("/api/preset",{project,kind:"ttd_"+code});checkpoint();project=next;syncControls();changed();}
  catch(error){toast(error.message,true);}
};
$("presets").onclick=async e=>{const b=e.target.closest("button");if(!b)return;try{const next=await json("/api/preset",{project,kind:b.dataset.preset});checkpoint();project=next;syncControls();changed();}catch(error){toast(error.message,true);}};
$("paint-colour").oninput=()=>{paint=$("paint-colour").value;paintTag=0;$("paint-tag").value="0";updatePaint();};
$("paint-tag").onchange=()=>{paintTag=Number($("paint-tag").value);updatePaint();selectTool("paint");};
$("fill-colour").onclick=()=>{checkpoint();if(isBuilding()){const p=project.building.parts[selectedPart];if(p){p.colour=paint;p.tag=paintTag;syncPartEditor();}}else{project.colours.fill(paint);project.tags.fill(paintTag);}changed();};
$("texture-light").onpointerdown=checkpoint;
$("texture-light").oninput=()=>{project.texture_light=Number($("texture-light").value)/100;$("texture-light-value").textContent=$("texture-light").value+"%";changed();};
$("overlay").oninput=()=>{$("overlay-value").textContent=$("overlay").value+"%";drawStage();};
for(const [id,key] of [["reference-x","xoffset"],["reference-y","yoffset"]])$(id).onchange=()=>{if(!project.reference)return;checkpoint();project.reference[key]=Number($(id).value);changed();};
$("reset-light").onclick=async()=>{const data=await json("/api/bootstrap");checkpoint();project.light=data.project.light;syncControls();changed();};
document.querySelectorAll("[data-zoom]").forEach(b=>b.onchange=()=>{checkpoint();project.export_zooms=[...document.querySelectorAll("[data-zoom]:checked")].map(el=>Number(el.dataset.zoom));changed();});
$("clear-reference").onclick=()=>{checkpoint();project.reference=null;project.texture="none";referenceImage=null;selectedReferenceKey=null;$("export-reference").disabled=true;document.querySelectorAll(".sprite-card").forEach(v=>v.classList.remove("selected"));$("overlay").value=0;syncControls();changed();};

$("drop-zone").onclick=()=>$("grf-file").click();
$("drop-zone").onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();$("grf-file").click();}};
for(const name of ["dragenter","dragover"])$("drop-zone").addEventListener(name,e=>{e.preventDefault();$("drop-zone").classList.add("drag-over");});
for(const name of ["dragleave","drop"])$("drop-zone").addEventListener(name,e=>{e.preventDefault();$("drop-zone").classList.remove("drag-over");});
$("drop-zone").addEventListener("drop",e=>{const file=e.dataTransfer.files[0];if(file)importFile(file);});
$("grf-file").onchange=()=>{const file=$("grf-file").files[0];if(file)importFile(file);$("grf-file").value="";};
function paletteNote(lib){
  const names={dos:"DOS",windows:"Windows"},used=names[lib.palette];
  const source=lib.declared in names?lib.declared:lib.inferred,how=lib.declared in names?"declares":"looks like";
  if(lib.requested==="auto"){
    if(lib.declared in names)return `${used} palette (declared by the GRF)`;
    if(lib.inferred in names)return `${used} palette (inferred from sprite colours; the GRF declares ${lib.declared==="any"?"any palette":"none"})`;
    return `${used} palette (GRF declares ${lib.declared==="any"?"any palette":"no palette"})`;
  }
  if(source in names&&source!==lib.palette)return `${used} palette as chosen, but the GRF ${how} ${names[source]}`;
  return `${used} palette`;
}
function paletteMismatch(lib){const source=["dos","windows"].includes(lib.declared)?lib.declared:lib.inferred;return lib.requested!=="auto"&&["dos","windows"].includes(source)&&source!==lib.palette;}
async function importFile(file){
  if(!/\.grf$/i.test(file.name))return toast("Choose a .grf file",true);
  if(file.size>128*1024*1024)return toast("The GRF file exceeds 128 MiB",true);
  busy(true,"Importing sprites…","Decoding graphics and preserving their origins.");
  try{
    const lib=await(await api(`/api/import?name=${encodeURIComponent(file.name)}&palette=${$("import-palette").value}`,file,true)).json();
    libraries.push(lib);activeLibrary=lib.id;page=0;
    selectedReferenceKey=null;$("export-reference").disabled=true;$("export-references").disabled=false;
    const option=document.createElement("option");option.value=lib.id;option.textContent=lib.name;$("library-select").append(option);$("library-select").value=lib.id;
    await refreshLibrary();toast(`${lib.count.toLocaleString()} sprite variants loaded · ${paletteNote(lib)}`,paletteMismatch(lib));
  }catch(error){toast(error.message,true);}finally{busy(false);}
}
async function refreshLibrary(){
  if(!activeLibrary)return;
  const id=activeLibrary;
  try{
    const data=await json(`/api/library?id=${id}&offset=${page*60}&q=${encodeURIComponent($("sprite-search").value)}&tiles=${$("tile-filter").checked}`);
    if(id!==activeLibrary)return;
    libraryTotal=data.total;$("sprite-grid").replaceChildren();
    for(const sprite of data.sprites){
      const b=document.createElement("button");b.className="sprite-card";b.title=`Sprite ${sprite.number} · ${sprite.width}×${sprite.height} · ${sprite.depth} · ${sprite.zoom}`;
      const img=document.createElement("img");img.loading="lazy";img.src=`/api/sprite?id=${id}&key=${sprite.key}`;img.alt=`Sprite ${sprite.number}`;
      const text=document.createElement("span");text.textContent=`${sprite.number} · ${sprite.zoom}`;b.append(img,text);
      b.onclick=async event=>{try{
        if(tool==="dropper"){
          const pixel=sourcePixel(event,img,img,true);
          if(!pixel){toast("Click inside the thumbnail image to pick a colour");return;}
          if(sampling)return;sampling=true;
          try{const ref=await json(`/api/reference?id=${id}&key=${sprite.key}`);const sample=await sampleReferenceColour(ref,pixel.x,pixel.y);if(tool==="dropper")acceptColourSample(sample);}
          finally{sampling=false;}
          return;
        }
        const ref=await json(`/api/reference?id=${id}&key=${sprite.key}`);checkpoint();project.reference=ref;
        selectedReferenceKey=sprite.key;$("export-reference").disabled=false;
        project.palette=ref.palette;referenceImage=await loadImage(ref.png);
        document.querySelectorAll(".sprite-card").forEach(v=>v.classList.remove("selected"));b.classList.add("selected");syncControls();changed();
        toast(`Sprite ${sprite.number} selected as reference`);
      }catch(error){toast(error.message,true);}};
      $("sprite-grid").append(b);
    }
    $("library-count").textContent=`${data.total.toLocaleString()} of ${data.all.toLocaleString()} sprite variants`;
    $("page-label").textContent=data.total?`${page*60+1}–${Math.min(data.total,(page+1)*60)} / ${data.total}`:"No matches";
    $("previous-page").disabled=page===0;$("next-page").disabled=(page+1)*60>=data.total;
  }catch(error){toast(error.message,true);}
}
$("library-select").onchange=()=>{activeLibrary=$("library-select").value;selectedReferenceKey=null;$("export-reference").disabled=true;$("export-references").disabled=!activeLibrary;page=0;refreshLibrary();};
$("sprite-search").oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{page=0;refreshLibrary();},220);};
$("tile-filter").onchange=()=>{page=0;refreshLibrary();};
$("previous-page").onclick=()=>{page=Math.max(0,page-1);refreshLibrary();};
$("next-page").onclick=()=>{if((page+1)*60<libraryTotal){page++;refreshLibrary();}};

function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
async function exportReferences(all=false){
  if(!activeLibrary || (!all && selectedReferenceKey===null))return;
  busy(true,"Exporting reference sprites…","Saving each original image with its sprite bounds and offsets.");
  try{
    const data={library:activeLibrary};if(!all)data.key=selectedReferenceKey;
    const response=await api("/api/export-references",data);download(await response.blob(),"grf-reference-sprites.zip");
    toast("Reference sprites exported as individual PNGs");
  }catch(error){toast(error.message,true);}finally{busy(false);}
}
$("export-reference").onclick=()=>exportReferences(false);$("export-references").onclick=()=>exportReferences(true);
$("save-project").onclick=async()=>{
  await window.referenceBoard?.restore();
  const board=window.referenceBoard?.snapshot()||{pictures:[],settings:{}};
  const data={format:"voxel-terrain-workshop",version:1,current:project,tiles,pictures:board.pictures,picture_settings:board.settings};
  download(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}),(project.name.replace(/[^a-z0-9_-]+/gi,"_")||"terrain")+".voxel.json");
  $("status").textContent="Project saved";toast("Project saved with its reference pixels");
};
$("open-project").onclick=()=>$("project-file").click();
$("project-file").onchange=async()=>{
  const file=$("project-file").files[0];if(!file)return;
  try{
    if(file.size>96*1024*1024)throw new Error("Project is larger than 96 MiB");
    const data=JSON.parse(await file.text());
    if(data.format!=="voxel-terrain-workshop"||data.version!==1)throw new Error("This is not a supported workshop project");
    const next=await json("/api/validate",data.current),collection=[];
    if(!Array.isArray(data.tiles)||data.tiles.length>64)throw new Error("Invalid sprite collection");
    for(const tile of data.tiles)collection.push(await json("/api/validate",tile.project||tile));
    await window.referenceBoard.load(data.pictures||[],data.picture_settings||{});
    checkpoint();project=next;tiles=collection.map(p=>({project:p,png:null}));selectedReferenceKey=null;$("export-reference").disabled=true;syncControls();refreshCollection();changed();toast("Project opened");
  }catch(error){toast(error.message,true);}finally{$("project-file").value="";}
};
$("add-tile").onclick=()=>{
  if(!result||renderedVersion!==version)return toast("Wait for the current render to finish");
  if(tiles.length>=64)return toast("A collection can contain up to 64 tiles",true);
  tiles.push({project:clone(project),png:result.png});refreshCollection();changed();toast("Current tile added to collection");
};
function refreshCollection(){
  $("collection").replaceChildren();
  if(!tiles.length){const p=document.createElement("p");p.className="hint";p.textContent="Collect finished tiles here to export them together. Each keeps its own model, reference and sprite offsets.";$("collection").append(p);}
  tiles.forEach((tile,index)=>{
    const el=document.createElement("div");el.className="collection-item";el.tabIndex=0;el.setAttribute("role","button");
    const img=document.createElement("img");img.alt="";if(tile.png)img.src="data:image/png;base64,"+tile.png;
    const info=document.createElement("div");info.className="tile-info";const title=document.createElement("strong");title.textContent=tile.project.name;
    const sub=document.createElement("small");sub.textContent=tile.project.profile==="ground"?`Ground · base sprite ${targetId(tile.project)}`:"Raised tile object";info.append(title,sub);
    const remove=document.createElement("button");remove.textContent="×";remove.title="Remove from collection";remove.setAttribute("aria-label",`Remove ${tile.project.name} from collection`);
    remove.onclick=e=>{e.stopPropagation();tiles.splice(index,1);refreshCollection();changed();};
    const load=()=>{checkpoint();project=clone(tile.project);syncControls();changed();};el.onclick=load;el.onkeydown=e=>{if(e.key==="Enter")load();};el.append(img,info,remove);$("collection").append(el);
    if(!tile.png)json("/api/render",tile.project).then(r=>{tile.png=r.png;img.src="data:image/png;base64,"+r.png;}).catch(()=>{});
  });
  $("collection-count").textContent=`${tiles.length} tile${tiles.length===1?"":"s"} collected`;$("export-collection").disabled=!tiles.length;
}
async function exportTiles(collection=false){
  const projects=collection?tiles.map(t=>t.project):[project];
  if(!projects.length)return;
  busy(true,"Exporting individual sprites…",$("build-grf").checked?"Rendering each zoom and compiling the test NewGRF.":"Saving sprites, origins and placement definitions.");
  try{
    const response=await api("/api/export",{projects,build:$("build-grf").checked,legacy:$("legacy").checked});
    download(await response.blob(),"voxel-terrain-sprites.zip");toast("Sprites exported with bounds and offsets");$("status").textContent="Export complete · in-game review still required";
  }catch(error){toast(error.message,true);}finally{busy(false);}
}
$("export").onclick=()=>exportTiles(false);$("export-collection").onclick=()=>exportTiles(true);

async function init(){
  try{
    const data=await json("/api/bootstrap");token=data.token;project=data.project;palettes=data.palettes;reserved=data.reserved;
    shapeLabels=data.shapes;slopeNames=data.terrain_slopes;slopeOffsets=data.slope_offsets;
    for(const [value,label] of Object.entries(data.building_shapes)){const option=new Option(label,value);$("part-shape").append(option);}
    for(const [value,label] of Object.entries(data.building_presets))$("building-preset").append(new Option(label,value));
    for(const [value,label] of Object.entries(shapeLabels)){const option=document.createElement("option");option.value=value;option.textContent=label;$("shape-brush").append(option);}
    const custom=document.createElement("option");custom.value="";custom.textContent="Custom / reference footprint";$("terrain-slope").append(custom);
    for(const [value,label] of Object.entries(slopeNames)){const option=document.createElement("option");option.value=value;option.textContent=label;$("terrain-slope").append(option);}
    syncShapeBrush();
    $("codec-notice").hidden=data.codec;$("build-grf").checked=data.compiler;
    const saved=localStorage.getItem("voxel-terrain-project");let restored=false;
    if(saved){try{
      const parsed=JSON.parse(saved);project=await json("/api/validate",parsed.current);
      if(Array.isArray(parsed.tiles)&&parsed.tiles.length<=64){tiles=[];for(const tile of parsed.tiles){tiles.push({project:await json("/api/validate",tile.project||tile),png:tile.png||null});}}
      restored=true;
    }catch(_){toast("The previous workspace could not be restored. Open a saved project to recover it.",true);}}
    if(!restored){
      project.zoom=4;project.profile="object";project.name="Terraced meadow";
      project=await json("/api/preset",{project,kind:"mound"});
      const greens=["#648b39","#6b943f","#729943","#608535","#789c47"];
      project.colours=project.colours.map((_,i)=>greens[((i*13)^Math.floor(i/project.size)*7)%greens.length]);
    }
    syncControls();refreshCollection();new ResizeObserver(resizeStage).observe(canvas);changed();window.dispatchEvent(new Event("workshop-ready"));
  }catch(error){toast(error.message,true);$("status").textContent="Connection failed · restart the local workshop";}
}
init();
