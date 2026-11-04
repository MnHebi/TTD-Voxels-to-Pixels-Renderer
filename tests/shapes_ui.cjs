// SPDX-License-Identifier: GPL-2.0-only
const {chromium}=require("playwright");
const fs=require("node:fs");
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.WORKSHOP_BROWSER?{executablePath:process.env.WORKSHOP_BROWSER}:{})});
  const page=await browser.newPage({viewport:{width:1512,height:1100}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(process.env.WORKSHOP_URL||"http://127.0.0.1:7866/");
  const settled=()=>page.waitForFunction(()=>typeof renderedVersion!=="undefined"&&renderedVersion===version&&!rendering);
  await settled();
  await page.locator("#profile").selectOption("ground");
  await page.locator("#terrain-slope").selectOption("12");
  await page.locator("#apply-terrain").click();await settled();
  await page.locator("#resolution").selectOption("32");await settled();
  await page.locator("#resolution").selectOption("8");await settled();
  await page.locator('[data-view="tiling"]').click();
  await page.screenshot({path:".work/shapes-ramp-tiling.png",fullPage:true});
  if(!await page.locator("#stage-label").textContent().then(t=>t.includes("MATCHING EDGES")))throw new Error("Ramp edge matching not reported");
  await page.locator("#terrain-slope").selectOption("8");await page.locator("#apply-terrain").click();await settled();
  if(!await page.locator("#stage-label").textContent().then(t=>t.includes("COMPLEMENTS")))throw new Error("Corner edge mismatch not reported");
  await page.locator("#profile").selectOption("object");
  await page.locator('[data-preset="flat"]').click();await settled();
  await page.locator('[data-view="sprite"]').click();
  for(const shape of ["wedge","diagonal","corner","inner_corner","ridge","valley","pyramid","cube"]){
    await page.locator("#shape-brush").selectOption(shape);
    await page.locator("#shape-rise").fill("2");await page.locator("#shape-rise").press("Tab");
    await page.locator("#fill-shape").click();await settled();
    if(shape==="pyramid")await page.screenshot({path:".work/shapes-pyramid.png",fullPage:true});
  }
  await page.locator("#shape-brush").selectOption("corner");await page.locator("#rotate-shape").click();
  const rect=await page.locator("#heightmap").boundingBox();await page.mouse.click(rect.x+rect.width*.55,rect.y+rect.height*.55);await settled();
  const saved=page.waitForEvent("download");await page.locator("#save-project").click();await(await saved).saveAs(".work/shapes-project.json");
  const data=JSON.parse(fs.readFileSync(".work/shapes-project.json","utf8"));
  if(!data.current.shapes.includes("corner")||!data.current.rotations.includes(1))throw new Error("Shape brush state not saved");
  await page.locator("#project-file").setInputFiles(".work/shapes-project.json");await settled();
  await page.locator("#terrain-slope").selectOption("29");await page.locator("#apply-terrain").click();
  await page.locator("#profile").selectOption("ground");await settled();
  await page.locator("#build-grf").check();
  const exported=page.waitForEvent("download",{timeout:120000});await page.locator("#export").click();
  await(await exported).saveAs(".work/shapes-ui-export.zip");
  if(errors.length)throw new Error(errors.join("\n"));
  console.log(JSON.stringify({ui:"passed",shapes:8,errors,exportBytes:fs.statSync(".work/shapes-ui-export.zip").size}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
