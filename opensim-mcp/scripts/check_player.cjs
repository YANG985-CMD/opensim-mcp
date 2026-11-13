// Optional developer regression: npm install playwright-core@1.64.1 in scratch.
// NODE_PATH points to that scratch node_modules. Uses an existing Edge binary.
const fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright-core');
const [html,edge,scratch]=process.argv.slice(2);
if(!html||!edge||!scratch)throw Error('Usage: node check_player.cjs <viewer-demo.html> <msedge.exe> <scratch-output>');
(async()=>{
 fs.mkdirSync(scratch,{recursive:true});
 const context=await chromium.launchPersistentContext(path.join(scratch,'edge-profile'),{headless:true,executablePath:edge,viewport:{width:1440,height:1000},
  args:['--enable-unsafe-swiftshader','--no-first-run','--no-default-browser-check']});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(pathToFileURL(path.resolve(html)).href);
  await page.waitForFunction(()=>document.body.dataset.viewerReady==='true',null,{timeout:30000});
  const pixels=()=>page.evaluate(()=>{const c=document.getElementById('scene'),g=c.getContext('webgl'),p=new Uint8Array(c.width*c.height*4);
   g.readPixels(0,0,c.width,c.height,g.RGBA,g.UNSIGNED_BYTE,p);let colored=0;
   for(let i=0;i<p.length;i+=4)if(p[i]<220||p[i+1]<220||p[i+2]<220)colored++;
   return {colored,sample:Array.from(p.filter((_,i)=>i%113===0))};});
  const original=await pixels();if(original.colored<500)throw Error('No rendered geometry.');
  const maximum=await page.locator('#timeline').getAttribute('max');
  await page.locator('#timeline').focus();await page.keyboard.press('End');
  await page.waitForFunction(max=>document.body.dataset.frameIndex===max,maximum);
  const final=await pixels();if(JSON.stringify(original.sample)===JSON.stringify(final.sample))throw Error('Timeline did not move geometry.');
  await page.locator('#errors').check();const colored=await pixels();
  if(JSON.stringify(final.sample)===JSON.stringify(colored.sample))throw Error('Error colors unchanged; use supplied comparison demo.');
  await page.screenshot({path:path.join(scratch,'final-frame.png'),fullPage:true});
  const box=await page.locator('#scene').boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+box.width/2+130,box.y+box.height/2+40,{steps:8});await page.mouse.up();
  if(JSON.stringify(colored.sample)===JSON.stringify((await pixels()).sample))throw Error('Orbit view unchanged.');
  await page.locator('#reset').click();await page.locator('#play').click();await page.waitForTimeout(300);await page.locator('#play').click();
  const state=await page.evaluate(()=>({index:document.body.dataset.frameIndex,playing:document.body.dataset.playing}));
  if(state.index===maximum||state.playing!=='false')throw Error('Playback failed.');
  if(errors.length)throw Error(errors.join('\n'));
  const result={passed:true,browser:'Microsoft Edge / Playwright core '+require('playwright-core/package.json').version,
   mesh_pixels_rendered:original.colored,timeline_keyboard:true,marker_error_coloring:true,orbit_drag:true,reset_view:true,play_pause:true,offline_file_page:true,javascript_errors:errors};
  fs.writeFileSync(path.join(scratch,'player-browser.json'),JSON.stringify(result,null,2));process.stdout.write(JSON.stringify(result)+'\n');
 }finally{await context.close();}
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
