// SPDX-License-Identifier: GPL-2.0-only
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs");
module.exports=async function checkPictures(page,settled){
  const initial=await page.evaluate(()=>({board:referenceBoard.snapshot(),project:structuredClone(project)}));
  const png=await page.evaluate(()=>{
    const c=document.createElement("canvas");c.width=240;c.height=140;const x=c.getContext("2d");
    x.fillStyle="#607058";x.fillRect(0,0,240,140);x.fillStyle="#6098c8";x.fillRect(0,0,240,40);
    x.fillStyle="#708068";x.fillRect(70,65,70,45);x.fillStyle="#919191";x.fillRect(155,60,55,65);x.clearRect(0,0,4,4);
    return c.toDataURL("image/png").split(",")[1];
  });
  await page.locator("#toggle-pictures").click();
  await page.locator("#picture-files").setInputFiles([
    {name:"Forest reference.png",mimeType:"image/png",buffer:Buffer.from(png,"base64")},
    {name:"Second reference.png",mimeType:"image/png",buffer:Buffer.from(png,"base64")}
  ]);
  const ready=()=>page.waitForFunction(()=>referenceBoard.ready&&referenceBoard.snapshot().pictures.length===2);
  await ready();assert.equal(await page.locator("#picture-select").inputValue(),"1");
  await page.locator("#picture-prev").click();await ready();assert.equal(await page.locator("#picture-select").inputValue(),"0");
  await page.locator("#picture-canvas").focus();await page.keyboard.press("ArrowRight");await ready();assert.equal(await page.locator("#picture-select").inputValue(),"1");
  await page.locator("#picture-select").selectOption("0");await ready();
  const initialWidths=await page.evaluate(()=>referenceBoard.targets.map(t=>t.width));
  await page.locator("#picture-original-plus").click();await page.locator("#picture-original-plus").click();
  assert(await page.evaluate(()=>referenceBoard.targets[0].width)>initialWidths[0]*1.5);
  assert.equal(await page.evaluate(()=>referenceBoard.targets[1].width),initialWidths[1]);
  await page.locator("#picture-original-minus").click();
  assert.equal(await page.evaluate(()=>referenceBoard.snapshot().settings.originalZoom),1.25);
  const panPoint=await page.evaluate(()=>{const t=referenceBoard.targets[0],r=$("picture-canvas").getBoundingClientRect();return {x:r.left+t.clip.x+t.clip.width/2,y:r.top+t.clip.y+t.clip.height/2};});
  await page.mouse.move(panPoint.x,panPoint.y);await page.mouse.down();await page.mouse.move(panPoint.x+22,panPoint.y+10,{steps:4});await page.mouse.up();
  assert(await page.evaluate(()=>referenceBoard.snapshot().settings.originalPanX)>0);
  assert.equal(await page.evaluate(()=>referenceBoard.snapshot().settings.convertedPanX),0);
  await page.locator("#picture-dropper").click();await picturePixel(0,120,45);
  assert.equal(await page.evaluate(()=>paint),"#607058");
  await page.locator("#picture-converted-plus").click();
  assert.equal(await page.evaluate(()=>referenceBoard.snapshot().settings.convertedZoom),1.25);
  await page.locator("#picture-original-fit").click();await page.locator("#picture-converted-fit").click();
  assert.equal(await page.evaluate(()=>referenceBoard.snapshot().settings.originalPanX),0);
  async function picturePixel(which,x,y){
    const point=await page.evaluate(({which,x,y})=>{const t=referenceBoard.targets[which],r=$("picture-canvas").getBoundingClientRect();return {x:r.left+t.x+(x+.5)/t.image.naturalWidth*t.width,y:r.top+t.y+(y+.5)/t.image.naturalHeight*t.height};},{which,x,y});
    await page.mouse.click(point.x,point.y);
  }
  await page.locator("#picture-dropper").click();await picturePixel(0,20,80);
  assert.equal(await page.evaluate(()=>paint),"#607058");
  await page.locator("#picture-dither").uncheck();await ready();
  // The enlarged original overlaps the converted image's rectangle, but not its clipped pane.
  for(let i=0;i<4;i++)await page.locator("#picture-original-plus").click();
  await page.locator("#picture-dropper").click();await picturePixel(1,20,80);
  assert.equal(await page.evaluate(()=>paint),"#687c4c");
  await page.locator("#picture-original-fit").click();
  await page.locator("#picture-mode").selectOption("nearest");await ready();
  await page.locator("#picture-dropper").click();await picturePixel(1,20,80);
  assert.notEqual(await page.evaluate(()=>paint),"#687c4c");
  await page.locator("#picture-mode").selectOption("original");await ready();
  assert.equal(await page.evaluate(()=>referenceBoard.targets.length),1);
  assert.equal(await page.locator("#picture-zoom-converted").isVisible(),false);
  assert.equal(await page.locator("#picture-download").isDisabled(),true);
  await page.locator("#picture-mode").selectOption("balanced");await ready();
  await page.locator("#picture-palette").selectOption("windows");await ready();
  await page.locator("#picture-compare").uncheck();await ready();
  assert.equal(await page.locator("#picture-zoom-original").isVisible(),false);
  assert.equal(await page.locator("#picture-zoom-converted").isVisible(),true);
  await page.locator("#picture-compare").check();await ready();
  const downloaded=page.waitForEvent("download");await page.locator("#picture-download").click();await(await downloaded).saveAs(".work/picture-converted.png");
  assert(fs.statSync(".work/picture-converted.png").size>100);
  // Move and resize the optional nonmodal window while the editor stays available.
  const before=await page.locator("#picture-window").boundingBox();
  await page.mouse.move(before.x+110,before.y+18);await page.mouse.down();await page.mouse.move(before.x+50,before.y+50,{steps:5});await page.mouse.up();
  const moved=await page.locator("#picture-window").boundingBox();assert(moved.x<before.x);
  await page.mouse.move(moved.x+moved.width-3,moved.y+moved.height-3);await page.mouse.down();await page.mouse.move(moved.x+moved.width+50,moved.y+moved.height+30,{steps:5});await page.mouse.up();
  const resized=await page.locator("#picture-window").boundingBox();assert(resized.width>moved.width);
  await page.locator("#picture-original-plus").click();
  await page.screenshot({path:".work/reference-pictures.png"});
  // Gallery changes never attach screenshot bytes to the rendered/exported model.
  assert.deepEqual(await page.evaluate(()=>project),initial.project);
  const saved=page.waitForEvent("download");await page.locator("#save-project").click();await(await saved).saveAs(".work/pictures-project.json");
  const data=JSON.parse(fs.readFileSync(".work/pictures-project.json","utf8"));assert.equal(data.pictures.length,2);
  await page.locator("#picture-remove").click();await page.waitForFunction(()=>referenceBoard.snapshot().pictures.length===1);
  await page.locator("#project-file").setInputFiles(".work/pictures-project.json");await ready();await settled();
  assert.equal(await page.evaluate(()=>referenceBoard.snapshot().settings.originalZoom),1.25);
  await page.waitForTimeout(400);await page.reload();await settled();await ready();
  assert.equal(await page.locator("#picture-window").isVisible(),true);
  assert.equal(await page.evaluate(()=>referenceBoard.snapshot().settings.originalZoom),1.25);
  await page.locator("#picture-close").click();assert.equal(await page.locator("#picture-window").isVisible(),false);
  await page.locator("#toggle-pictures").click();await ready();
  await page.locator("#picture-close").click();
  await page.evaluate(async data=>{await referenceBoard.load(data.board.pictures,data.board.settings);},initial);
  console.log("Pictures: independent pane zoom, pan, fit, clipped colour picking, persistence and existing picture workflows passed");
};
