// SPDX-License-Identifier: GPL-2.0-only
"use strict";
// Screenshot references belong to the workspace, outside the frequently rendered model.
window.referenceBoard=(()=>{
  const panel=$("picture-window"),surface=$("picture-canvas"),context=surface.getContext("2d");
  const defaults={index:0,mode:"balanced",palette:"dos",dither:true,compare:true,visible:false,left:null,top:100,width:740,height:540,
                  originalZoom:1,convertedZoom:1,originalPanX:0,originalPanY:0,convertedPanX:0,convertedPanY:0};
  let pictures=[],settings={...defaults},request=0,targets=[],converted=null,importing=false,restorePromise,persistTimer;
  const originals=new WeakMap(),conversions=new WeakMap();
  const database=new Promise((resolve,reject)=>{
    const open=indexedDB.open("voxel-workshop-reference-pictures",1);
    open.onupgradeneeded=()=>open.result.createObjectStore("workspace");
    open.onsuccess=()=>resolve(open.result);open.onerror=()=>reject(open.error);
  });
  database.catch(()=>{});
  async function storage(write,value){
    const db=await database;
    return new Promise((resolve,reject)=>{
      const transaction=db.transaction("workspace",write?"readwrite":"readonly");
      const operation=write?transaction.objectStore("workspace").put(value,"current"):transaction.objectStore("workspace").get("current");
      let result;operation.onsuccess=()=>result=operation.result;
      transaction.oncomplete=()=>resolve(result);transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error);
    });
  }
  const snapshot=()=>({pictures,settings:{...settings}});
  function persist(){
    clearTimeout(persistTimer);persistTimer=setTimeout(()=>storage(true,snapshot()).catch(()=>toast("Reference pictures could not be autosaved · save the project file",true)),250);
  }
  function normalSettings(value){
    const s={...defaults,...value};
    if(!["original","nearest","balanced"].includes(s.mode))s.mode=defaults.mode;
    if(!["dos","windows"].includes(s.palette))s.palette="dos";
    for(const key of ["index","top","width","height"]){if(!Number.isFinite(s[key]))s[key]=defaults[key];}
    if(s.left!==null&&!Number.isFinite(s.left))s.left=null;
    s.index=Math.max(0,Math.min(Math.floor(s.index),Math.max(0,pictures.length-1)));
    for(const key of ["dither","compare","visible"])s[key]=Boolean(s[key]);
    for(const role of ["original","converted"]){
      const key=role+"Zoom";s[key]=Number.isFinite(s[key])?Math.max(.25,Math.min(16,s[key])):1;
      for(const axis of ["X","Y"]){const key=role+"Pan"+axis;s[key]=Number.isFinite(s[key])?Math.max(-100000,Math.min(100000,s[key])):0;}
    }
    return s;
  }
  function fitWindow(){
    const w=Math.min(Math.max(420,settings.width),innerWidth-20),h=Math.min(Math.max(330,settings.height),innerHeight-30);
    panel.style.width=`${Math.max(1,w)}px`;panel.style.height=`${Math.max(1,h)}px`;
    panel.style.left=`${Math.max(10,Math.min(settings.left??(innerWidth-w)/2,innerWidth-w-10))}px`;
    panel.style.top=`${Math.max(10,Math.min(settings.top,innerHeight-h-10))}px`;
  }
  function captureWindow(){
    if(panel.hidden)return;const r=panel.getBoundingClientRect();Object.assign(settings,{left:r.left,top:r.top,width:r.width,height:r.height});
  }
  function visible(show){
    if(!show)captureWindow();settings.visible=show;panel.hidden=!show;$("toggle-pictures").setAttribute("aria-expanded",String(show));
    if(show){fitWindow();refresh();}persist();
  }
  function controls(){
    $("picture-count").textContent=`${pictures.length?settings.index+1:0} / ${pictures.length} pictures`;
    $("picture-select").replaceChildren(...pictures.map((p,i)=>new Option(p.name,String(i))));$("picture-select").value=String(settings.index);
    $("picture-mode").value=settings.mode;$("picture-palette").value=settings.palette;$("picture-dither").checked=settings.dither;$("picture-compare").checked=settings.compare;
    for(const id of ["picture-prev","picture-next"])$(id).disabled=pictures.length<2;
    $("picture-select").disabled=$("picture-remove").disabled=!pictures.length;
    $("picture-add").disabled=importing||pictures.length>=12;
    $("picture-download").disabled=!converted||settings.mode==="original";
    $("picture-dither").disabled=$("picture-palette").disabled=$("picture-compare").disabled=settings.mode==="original";
    $("picture-empty").hidden=!!pictures.length;
    $("picture-thumbs").replaceChildren(...pictures.map((p,i)=>{
      const b=document.createElement("button");b.classList.toggle("active",i===settings.index);b.title=p.name;b.setAttribute("aria-label",`Show ${p.name}`);
      const im=new Image();im.src="data:image/png;base64,"+p.png;im.alt="";b.append(im);b.onclick=()=>choose(i);return b;
    }));
  }
  let displayed=[];
  function zoomControls(){
    $("picture-zoom-controls").hidden=!displayed.length;
    for(const role of ["original","converted"]){
      $("picture-zoom-"+role).hidden=!displayed.some(t=>t.role===role);
      $("picture-"+role+"-minus").disabled=settings[role+"Zoom"]<=.25;
      $("picture-"+role+"-plus").disabled=settings[role+"Zoom"]>=16;
    }
  }
  function draw(){
    zoomControls();
    const width=surface.clientWidth,height=surface.clientHeight,dpr=devicePixelRatio||1;
    surface.width=Math.max(1,Math.round(width*dpr));surface.height=Math.max(1,Math.round(height*dpr));
    context.setTransform(dpr,0,0,dpr,0,0);context.clearRect(0,0,width,height);context.imageSmoothingEnabled=true;targets=[];
    const columns=displayed.length;
    displayed.forEach(({image,label,role},i)=>{
      const pane=width/columns,scale=Math.min((pane-18)/image.naturalWidth,(height-34)/image.naturalHeight)*settings[role+"Zoom"];
      if(scale<=0)return;
      const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
      const limitX=Math.max(0,(w-(pane-18))/2),limitY=Math.max(0,(h-(height-34))/2);
      const panX=settings[role+"PanX"]=Math.max(-limitX,Math.min(limitX,settings[role+"PanX"]));
      const panY=settings[role+"PanY"]=Math.max(-limitY,Math.min(limitY,settings[role+"PanY"]));
      const x=pane*i+(pane-w)/2+panX,y=27+(height-30-h)/2+panY;
      const clip={x:pane*i,y:26,width:pane,height:Math.max(0,height-26)};
      context.fillStyle="#9dac9b";context.font="11px Segoe UI";context.textAlign="center";context.fillText(label,pane*(i+.5),17,Math.max(1,pane-16));
      context.save();context.beginPath();context.rect(clip.x,clip.y,clip.width,clip.height);context.clip();
      context.imageSmoothingEnabled=scale<1;context.drawImage(image,x,y,w,h);context.restore();
      targets.push({image,x,y,width:w,height:h,role,clip});
      $("picture-"+role+"-scale").textContent=Math.abs(settings[role+"Zoom"]-1)<.001?"Fit":`${Math.round(scale*100)}%`;
      if(i){context.strokeStyle="#ffffff19";context.beginPath();context.moveTo(pane*i,8);context.lineTo(pane*i,height-8);context.stroke();}
    });
  }
  async function refresh(){
    const generation=++request;converted=null;displayed=[];controls();draw();
    const p=pictures[settings.index];if(!p)return;
    const mode=settings.mode,palette=settings.palette,dither=settings.dither,compare=settings.compare;
    $("picture-info").textContent=`${p.width} × ${p.height}${p.resized?` · reference copy from ${p.original_width} × ${p.original_height}`:""}${mode!=="original"?" · Converting…":""}`;
    try{
      if(!originals.has(p))originals.set(p,loadImage(p.png));
      const original=await originals.get(p);
      if(generation!==request)return;
      displayed=[{image:original,label:"Original RGB",role:"original"}];draw();
      if(mode==="original"){controls();return;}
      if(!conversions.has(p))conversions.set(p,new Map());const cache=conversions.get(p),key=`${mode}/${palette}/${dither}`;
      if(!cache.has(key)){
        const pending=json("/api/pictures/convert",{png:p.png,palette,mapping:mode,dither}).catch(error=>{cache.delete(key);throw error;});
        cache.set(key,pending);if(cache.size>4)cache.delete(cache.keys().next().value);
      }
      const result=await cache.get(key),image=await loadImage(result.png);
      if(generation!==request)return;
      converted=result.png;displayed=compare?[{image:original,label:"Original RGB",role:"original"}]:[];
      displayed.push({image,role:"converted",label:`${palette.toUpperCase()} 8bpp · ${mode==="balanced"?"Keep colour families":"Nearest RGB"}${dither?" · dithered":""}`});
      $("picture-info").textContent=`${p.width} × ${p.height} · ${palette.toUpperCase()} palette${p.resized?" · resized reference copy":""}`;
      controls();draw();
    }catch(error){if(generation===request){$("picture-info").textContent="Conversion failed · original is still available";toast(error.message,true);}}
  }
  function choose(index){settings.index=(index+pictures.length)%pictures.length;refresh();persist();}
  async function add(files){
    if(importing)return;importing=true;controls();
    let count=0;
    try{
      for(const file of files){
        if(pictures.length>=12){toast("The reference window holds up to 12 pictures",true);break;}
        try{
          const p=await(await api(`/api/pictures/import?name=${encodeURIComponent(file.name)}`,file,true)).json();
          if(pictures.reduce((sum,p)=>sum+p.png.length,0)+p.png.length>64*1024*1024)throw new Error("The reference-picture collection exceeds 64 MiB");
          pictures.push(p);settings.index=pictures.length-1;count++;
        }catch(error){toast(`${file.name}: ${error.message}`,true);}
      }
    }finally{importing=false;controls();if(count){visible(true);persist();}$("picture-files").value="";}
  }
  function restore(){
    if(restorePromise)return restorePromise;
    restorePromise=(async()=>{
    try{
      const saved=await storage(false);
      if(saved&&Array.isArray(saved.pictures)&&saved.pictures.length<=12){pictures=saved.pictures;settings=normalSettings(saved.settings||{});}
      controls();panel.hidden=!settings.visible;$("toggle-pictures").setAttribute("aria-expanded",String(settings.visible));
      if(settings.visible){fitWindow();refresh();}
    }catch(_){toast("Reference-picture autosave is unavailable · use Save project to keep pictures",true);}
    })();return restorePromise;
  }
  async function load(items,value={}){
    await restore();
    const valid=await json("/api/pictures/validate",items);pictures=valid;settings=normalSettings(value);request++;converted=null;
    panel.hidden=!settings.visible;$("toggle-pictures").setAttribute("aria-expanded",String(settings.visible));controls();
    if(settings.visible){fitWindow();refresh();}persist();
  }
  $("toggle-pictures").onclick=async()=>{await restore();visible(panel.hidden);};$("picture-close").onclick=()=>visible(false);
  $("picture-add").onclick=()=>$("picture-files").click();$("picture-files").onchange=()=>add([...$("picture-files").files]);
  $("picture-prev").onclick=()=>choose(settings.index-1);$("picture-next").onclick=()=>choose(settings.index+1);
  $("picture-select").onchange=()=>choose(Number($("picture-select").value));
  $("picture-remove").onclick=()=>{pictures.splice(settings.index,1);settings.index=Math.max(0,Math.min(settings.index,pictures.length-1));refresh();persist();};
  for(const [id,key] of [["picture-mode","mode"],["picture-palette","palette"],["picture-dither","dither"],["picture-compare","compare"]])$(id).onchange=()=>{settings[key]=$(id).type==="checkbox"?$(id).checked:$(id).value;refresh();persist();};
  $("picture-dropper").onclick=()=>{selectTool("dropper");toast("Click the original or converted picture to pick a colour");};
  for(const role of ["original","converted"]){
    for(const [suffix,factor] of [["minus",1/1.25],["plus",1.25]])$("picture-"+role+"-"+suffix).onclick=()=>{
      settings[role+"Zoom"]=Math.max(.25,Math.min(16,settings[role+"Zoom"]*factor));draw();persist();
    };
    $("picture-"+role+"-fit").onclick=()=>{settings[role+"Zoom"]=1;settings[role+"PanX"]=settings[role+"PanY"]=0;draw();persist();};
  }
  $("picture-download").onclick=()=>{if(converted)download(new Blob([Uint8Array.from(atob(converted),c=>c.charCodeAt(0))],{type:"image/png"}),`${pictures[settings.index].name.replace(/\.[^.]*$/,"").replace(/[^a-z0-9_-]+/gi,"_")}_${settings.palette}_${settings.mode}.png`);};
  let panning=null;
  surface.onpointerdown=event=>{
    surface.focus();if(event.button!==0)return;
    const r=surface.getBoundingClientRect(),x=event.clientX-r.left,y=event.clientY-r.top;
    for(const t of targets){
      if(x<t.clip.x||y<t.clip.y||x>=t.clip.x+t.clip.width||y>=t.clip.y+t.clip.height)continue;
      if(tool!=="dropper"){
        panning={role:t.role,x:event.clientX,y:event.clientY,panX:settings[t.role+"PanX"],panY:settings[t.role+"PanY"]};
        surface.setPointerCapture(event.pointerId);surface.classList.add("picture-panning");event.preventDefault();return;
      }
      const px=Math.floor((x-t.x)/t.width*t.image.naturalWidth),py=Math.floor((y-t.y)/t.height*t.image.naturalHeight);
      if(px<0||py<0||px>=t.image.naturalWidth||py>=t.image.naturalHeight)continue;
      const rgba=imagePixels(t.image).data.slice((py*t.image.naturalWidth+px)*4,(py*t.image.naturalWidth+px)*4+4);
      acceptColourSample({colour:"#"+[...rgba.slice(0,3)].map(v=>v.toString(16).padStart(2,"0")).join(""),alpha:rgba[3],tag:0,palette:settings.palette});return;
    }
  };
  surface.onpointermove=event=>{if(!panning)return;settings[panning.role+"PanX"]=panning.panX+event.clientX-panning.x;settings[panning.role+"PanY"]=panning.panY+event.clientY-panning.y;draw();};
  const endPan=()=>{if(panning){panning=null;surface.classList.remove("picture-panning");persist();}};
  surface.onpointerup=endPan;surface.onpointercancel=endPan;surface.onlostpointercapture=endPan;
  panel.onkeydown=event=>{if(!["INPUT","SELECT"].includes(event.target.tagName)&&pictures.length&&["ArrowLeft","ArrowRight"].includes(event.key)){event.preventDefault();event.stopPropagation();choose(settings.index+(event.key==="ArrowRight"?1:-1));}};
  const stage=$("picture-stage");
  for(const name of ["dragenter","dragover"])stage.addEventListener(name,e=>{e.preventDefault();stage.classList.add("drag-over");});
  for(const name of ["dragleave","drop"])stage.addEventListener(name,e=>{e.preventDefault();stage.classList.remove("drag-over");});
  stage.addEventListener("drop",e=>add([...e.dataTransfer.files]));
  panel.addEventListener("paste",e=>{if(e.clipboardData.files.length){e.preventDefault();add([...e.clipboardData.files]);}});
  let dragging=null;
  $("picture-titlebar").onpointerdown=e=>{if(e.target.closest("button"))return;const r=panel.getBoundingClientRect();dragging={x:e.clientX-r.left,y:e.clientY-r.top};e.currentTarget.setPointerCapture(e.pointerId);};
  $("picture-titlebar").onpointermove=e=>{if(!dragging)return;settings.left=e.clientX-dragging.x;settings.top=e.clientY-dragging.y;fitWindow();};
  $("picture-titlebar").onpointerup=()=>{if(dragging){dragging=null;captureWindow();persist();}};
  new ResizeObserver(()=>{if(!panel.hidden){captureWindow();draw();persist();}}).observe(stage);
  window.addEventListener("resize",()=>{if(!panel.hidden){fitWindow();draw();}});
  window.addEventListener("workshop-ready",restore);document.addEventListener("DOMContentLoaded",()=>{if(typeof token!=="undefined"&&token)restore();});
  return {snapshot,load,restore,add,show:()=>visible(true),refresh,draw,get ready(){return !importing&&targets.length>0&&(!pictures.length||settings.mode==="original"||!!converted);},get targets(){return targets;}};
})();
