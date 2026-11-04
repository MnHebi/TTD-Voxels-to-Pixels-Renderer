// SPDX-License-Identifier: GPL-2.0-only
/* Optional browser smoke test: NODE_PATH must expose playwright. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.WORKSHOP_BROWSER ? {executablePath:process.env.WORKSHOP_BROWSER} : {})});
  const page = await browser.newPage({viewport:{width:1512,height:1100},deviceScaleFactor:1});
  const errors=[];
  page.on("pageerror",e=>errors.push(e.message));
  await page.goto(process.env.WORKSHOP_URL||"http://127.0.0.1:7865/");
  await page.waitForFunction(()=>document.getElementById("sprite-metrics").textContent.includes("offset"));
  await page.screenshot({path:".work/workshop-desktop.png",fullPage:true});
  const before=await page.locator("#heightmap").boundingBox();
  await page.mouse.click(before.x+before.width/2,before.y+before.height/2);
  await page.locator("#undo").click();
  await page.locator('[data-mode="8bpp"]').click();
  await page.waitForFunction(()=>document.getElementById("colour-badge").textContent==="8bpp PALETTE");
  await page.locator('[data-view="tiling"]').click();
  await page.screenshot({path:".work/workshop-tiling.png",fullPage:true});
  await page.locator("#add-tile").click();
  await page.waitForFunction(()=>document.getElementById("collection-count").textContent.includes("1 tile"));
  if(process.env.WORKSHOP_TEST_GRF){
    await page.locator("#grf-file").setInputFiles(process.env.WORKSHOP_TEST_GRF);
    await page.waitForFunction(()=>document.querySelectorAll(".sprite-card").length>0,null,{timeout:120000});
    await page.locator("#sprite-search").fill("3981");
    await page.waitForFunction(()=>document.getElementById("page-label").textContent.includes("/ 1"));
    await page.locator(".sprite-card").first().click();
    await page.locator("#texture").selectOption("surface");
    await page.locator('[data-view="compare"]').click();
    await page.waitForTimeout(1200);
    await page.screenshot({path:".work/workshop-reference.png",fullPage:true});
    const referenceDownload=page.waitForEvent("download");
    await page.locator("#export-reference").click();
    await (await referenceDownload).saveAs(".work/ui-reference.zip");
    const savedProject=page.waitForEvent("download");
    await page.locator("#save-project").click();
    await (await savedProject).saveAs(".work/ui-project.json");
    await page.locator("#clear-reference").click();
    await page.locator("#project-file").setInputFiles(".work/ui-project.json");
    await page.waitForFunction(()=>document.getElementById("source-details").textContent.includes("3981"));
  }
  if(process.env.WORKSHOP_TEST_BUILD)await page.locator("#build-grf").check();
  else await page.locator("#build-grf").uncheck();
  const downloadEvent=page.waitForEvent("download",{timeout:120000});
  await page.locator("#export").click();
  const download=await downloadEvent;
  await download.saveAs(".work/ui-export.zip");
  if(fs.statSync(".work/ui-export.zip").size<1000)throw new Error("Empty export");
  await page.setViewportSize({width:980,height:900});
  await page.screenshot({path:".work/workshop-compact.png",fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  if(overflow)throw new Error("Horizontal overflow at compact width");
  if(errors.length)throw new Error(errors.join("\n"));
  console.log(JSON.stringify({ui:"passed",errors,screenshots:4,downloadBytes:fs.statSync(".work/ui-export.zip").size}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
