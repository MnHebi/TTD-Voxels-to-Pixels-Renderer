// SPDX-License-Identifier: GPL-2.0-only
"use strict";
const assert=require("node:assert/strict");

module.exports=async function checkDropper(page,settled){
  const original=await page.evaluate(()=>structuredClone(project));
  const fixture=await page.evaluate(async png=>{
    const data=await json("/api/bootstrap");project=data.project;project.profile="object";project.zoom=1;
    project.colours.fill("#2864aa");project.colour_mode="32bpp";
    project.light={azimuth:55,elevation:60,ambient:1,strength:0,shadows:0,ao:0};
    const ref={png,mask:null,xoffset:-31,yoffset:0,scale:1,depth:"32bpp",palette:"dos",source:"Dropper fixture"};
    project.reference=ref;syncControls();changed();return ref;
  },require("node:fs").readFileSync(require("node:path").join(__dirname,"fixtures/dropper.png")).toString("base64"));
  await settled();
  const paint=()=>page.evaluate(()=>({colour:paint,tag:paintTag,tool}));
  async function clickPixel(source,x,y,which=0){
    const point=await page.evaluate(({source,x,y,which})=>{
      const t=spriteTargets.filter(t=>t.source===source)[which],r=canvas.getBoundingClientRect();
      return {x:r.left+t.rect.x+(x+.5)/t.image.naturalWidth*t.rect.width,
              y:r.top+t.rect.y+(y+.5)/t.image.naturalHeight*t.rect.height};
    },{source,x,y,which});await page.mouse.click(point.x,point.y);
  }
  // Render RGB, independent of editor background, grid and overlays; no model undo entry.
  const undoBefore=await page.evaluate(()=>undo.length);
  await page.locator("#sprite-dropper").click();await clickPixel("render",31,15);
  await page.waitForFunction(()=>tool==="paint");assert.equal((await paint()).colour,"#2864aa");
  assert.equal(await page.evaluate(()=>undo.length),undoBefore);
  await page.locator('[data-view="compare"]').click();await page.keyboard.press("i");
  await clickPixel("reference",0,0);assert.equal((await paint()).tool,"dropper");assert.equal((await paint()).colour,"#2864aa");
  await clickPixel("reference",44,21);await page.waitForFunction(()=>paint==="#fedcba");
  assert.equal((await paint()).tag,0);
  // An overlay must sample its unblended source pixel, not the composited stage.
  await page.locator('[data-view="sprite"]').click();await page.locator("#overlay").evaluate(el=>{el.value="50";el.dispatchEvent(new Event("input"));});await page.keyboard.press("i");
  await clickPixel("reference",12,10);await page.waitForFunction(()=>paint==="#12ab34");
  await page.locator("#overlay").evaluate(el=>{el.value="0";el.dispatchEvent(new Event("input"));});
  // Rendered indexed pixels retain exact special indices, including unlisted shades.
  await page.evaluate(()=>{project.colour_mode="8bpp";project.tags.fill(203);syncControls();changed();});await settled();
  await page.keyboard.press("i");await clickPixel("render",31,15);await page.waitForFunction(()=>paintTag===203);
  assert.equal(await page.locator("#paint-tag").inputValue(),"203");
  await page.locator("#dropper-effects").uncheck();await page.keyboard.press("i");await clickPixel("render",31,15);
  assert.equal((await paint()).tag,0);await page.locator("#dropper-effects").check();
  // Saved indexed references use source indices, not a nearest-RGB search.
  const indexed=await page.evaluate(async()=>{
    const r=await json("/api/render",project);const ref={...project.reference,png:r.palette_png,mask:r.palette_png,depth:"8bpp"};
    project.reference=ref;syncControls();changed();return ref;
  });await settled();await page.locator('[data-view="compare"]').click();await page.keyboard.press("i");
  await clickPixel("reference",31,15);await page.waitForFunction(()=>paintTag===203&&tool==="paint"&&!sampling);
  // Any repeated tile can be sampled; Esc cancels without painting.
  await page.locator('[data-view="tiling"]').click();await page.keyboard.press("i");await clickPixel("render",31,15,0);
  await page.waitForFunction(()=>tool==="paint");assert.equal((await paint()).tag,203);
  await page.keyboard.press("i");await page.keyboard.press("Escape");assert.equal((await paint()).tool,"paint");
  // A thumbnail sample must account for object-fit letterboxing and leave the reference unchanged.
  await page.route("**/api/library?**",route=>route.fulfill({json:{name:"Fixture",total:1,all:1,sprites:[{number:42,key:0,width:64,height:31,depth:"32bpp",zoom:"normal"}]}}));
  await page.route("**/api/sprite?**",route=>route.fulfill({contentType:"image/png",body:Buffer.from(fixture.png,"base64")}));
  await page.route("**/api/reference?**",route=>route.fulfill({json:fixture}));
  await page.evaluate(async()=>{activeLibrary="fixture";await refreshLibrary();});
  await page.locator(".sprite-card img").evaluate(im=>im.decode());
  const thumb=await page.locator(".sprite-card img").boundingBox();
  await page.locator("#sprite-dropper").click();await page.mouse.click(thumb.x+thumb.width/2,thumb.y+thumb.height/2);
  await page.waitForFunction(()=>paint==="#12ab34"&&tool==="paint");
  assert.equal(await page.evaluate(()=>project.reference.depth),"8bpp");
  await page.unrouteAll();
  // The same sampled colour is usable as a building part material.
  await page.locator("#profile").selectOption("building");await page.waitForFunction(()=>project.profile==="building");await settled();
  await page.evaluate(ref=>{project.reference=ref;syncControls();changed();},fixture);await settled();
  await page.locator('[data-view="compare"]').click();await page.locator("#sprite-dropper").click();
  await clickPixel("reference",44,21);await page.waitForFunction(()=>paint==="#fedcba");
  assert.equal(await page.locator("#part-colour").inputValue(),"#fedcba");
  await page.locator("#fill-colour").click();await settled();assert.equal(await page.evaluate(()=>project.building.parts[selectedPart].colour),"#fedcba");
  await page.evaluate(p=>{project=p;view="sprite";undo=[];redo=[];activeLibrary="";$("sprite-grid").replaceChildren();$("overlay").value=0;selectTool("raise");document.querySelectorAll("#view-tabs button").forEach(b=>b.classList.toggle("active",b.dataset.view===view));syncControls();changed();},original);
  await settled();console.log("Dropper: rendered RGB/indexed, Compare, overlay, transparency, masks, tiling, thumbnails, buildings, cancel passed");
};
