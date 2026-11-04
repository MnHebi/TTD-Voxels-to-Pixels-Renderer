// SPDX-License-Identifier: GPL-2.0-only
const {chromium}=require("playwright");
const fs=require("node:fs");
const path=require("node:path"),{spawn}=require("node:child_process");
(async()=>{
  let browser,server,page;
  try{
  const url=process.env.WORKSHOP_URL||"http://127.0.0.1:7866/";
  if(process.env.WORKSHOP_REUSE_SERVER!=="1"){
    const candidates=[process.env.WORKSHOP_PYTHON,path.resolve(".venv/Scripts/python.exe"),path.join(require("node:os").homedir(),".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")];
    const python=candidates.find(p=>p&&fs.existsSync(p))||"python";
    server=spawn(python,["app.py","--no-browser","--port",new URL(url).port],{windowsHide:true});
    let serverErrors="";server.stderr.on("data",data=>serverErrors+=data.toString());
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error("Test server did not start")),10000);
      server.stdout.on("data",data=>{if(data.toString().includes("http://")){clearTimeout(timer);resolve();}});
      server.on("error",reject);server.on("exit",code=>{clearTimeout(timer);reject(new Error(`Test server exited ${code}: ${serverErrors}`));});
    });
  }
  browser=await chromium.launch({headless:true,executablePath:process.env.WORKSHOP_BROWSER});
  page=await browser.newPage({viewport:{width:1580,height:1120}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(url);
  const settled=()=>page.waitForFunction(()=>typeof renderedVersion!=="undefined"&&renderedVersion===version&&!rendering&&!buildingPending);
  await settled();await require("./pictures_ui.cjs")(page,settled);await require("./dropper_ui.cjs")(page,settled);
  await page.locator("#profile").selectOption("building");
  await page.waitForFunction(()=>project.profile==="building");await settled();
  if(!await page.locator("#building-section").isVisible())throw new Error("Missing building editor");
  await page.locator("#building-parts").selectOption("1");
  await page.locator("#part-height").fill("14");await page.locator("#part-name").fill("Edited walls");
  await page.locator("#part-tag").selectOption("202");await page.locator("#apply-part").click();
  await page.waitForFunction(()=>project.building.parts[1].height===14);await settled();
  await page.locator("#undo").click();await settled();
  if(await page.evaluate(()=>project.building.parts[1].height)!==10)throw new Error("Building undo failed");
  await page.locator("#redo").click();await settled();
  await page.locator("#duplicate-part").click();await settled();
  await page.locator("#delete-part").click();await settled();
  await page.locator("#add-part").click();await settled();
  await page.locator("#part-z").fill("22");await page.locator("#part-shape").selectOption("shed");
  await page.locator("#apply-part").click();await page.waitForFunction(()=>project.building.parts.at(-1).z===22);await settled();
  await page.locator("#rotate-building").click();await page.waitForFunction(()=>project.building.view===1);await settled();
  await page.locator("#building-stage").selectOption("1");await page.waitForFunction(()=>project.building.stage===1);await settled();
  await page.locator("#building-stage").selectOption("3");await page.waitForFunction(()=>project.building.stage===3);await settled();
  await page.locator("#building-preset").selectOption("warehouse");await page.locator("#apply-building").click();
  await page.waitForFunction(()=>project.name==="Warehouse");await settled();
  await page.locator("#show-bounds").check();
  await page.screenshot({path:".work/building-editor.png",fullPage:true});
  await page.locator("#profile").selectOption("house");await page.waitForFunction(()=>project.profile==="house");await settled();
  await page.locator("#house-population").fill("65");await page.locator("#house-population").press("Tab");
  await page.waitForFunction(()=>project.building.population===65);await settled();
  const saved=page.waitForEvent("download");await page.locator("#save-project").click();await(await saved).saveAs(".work/building-project.json");
  const data=JSON.parse(fs.readFileSync(".work/building-project.json","utf8"));
  if(data.current.profile!=="house"||data.current.building.population!==65)throw new Error("Building save failed");
  await page.locator("#project-file").setInputFiles(".work/building-project.json");await settled();
  await page.locator("#building-views").uncheck();await page.waitForFunction(()=>project.building.views===1);await settled();
  for(const z of [2,4])await page.locator(`[data-zoom="${z}"]`).uncheck();await settled();
  await page.locator("#build-grf").check();const exported=page.waitForEvent("download",{timeout:120000});
  await page.locator("#export").click();await(await exported).saveAs(".work/buildings-ui-export.zip");
  if(errors.length)throw new Error(errors.join("\n"));
  console.log(JSON.stringify({ui:"passed",errors,exportBytes:fs.statSync(".work/buildings-ui-export.zip").size}));
  }catch(error){
    if(page){console.error(await page.evaluate(()=>({tool,paint,paintTag,sampling,version,renderedVersion,toast:$("toast").textContent})).catch(()=>null));await page.screenshot({path:".work/buildings-ui-failure.png"}).catch(()=>{});}
    throw error;
  }finally{if(browser)await browser.close();if(server)server.kill();}
})().catch(e=>{console.error(e);process.exit(1);});
