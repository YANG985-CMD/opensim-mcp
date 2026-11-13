(() => {
  'use strict';
  const byId=id=>document.getElementById(id), canvas=byId('scene'), gl=canvas.getContext('webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true});
  byId('title').textContent=DATA.name+' · 运动查看';
  byId('frame-count').textContent=DATA.frames.length;byId('mesh-count').textContent=DATA.meshes.length;
  let wbHidden=[],wbOpacity=1,wbMeasure=[];
  const wbSend=(event,payload)=>{if(DATA.workbench_embedded)parent.postMessage({channel:DATA.workbench_channel,event,payload},'*');};
  if(DATA.workbench_embedded){const style=document.createElement('style');style.textContent='html,body{height:100%;overflow:hidden}header,aside,footer,.bar{display:none!important}main{display:block;padding:0;height:100%}.stage{height:100%;border:0;border-radius:0}#scene{height:100%;width:100%}';document.head.append(style);}
  const externalSignals=DATA.external_signals||[];let selectedComponent=null;
  const muscleNames=DATA.muscle_names||Object.keys(DATA.frames[0].muscle_paths||{});
  byId('muscle-count').textContent=muscleNames.length;byId('muscles').disabled=!muscleNames.length;byId('muscle-width').disabled=!muscleNames.length;
  const resultInfo=DATA.muscle_result_info||[],hasForces=resultInfo.length>0,muscleSelect=byId('selected-muscle'),colorSelect=byId('muscle-color');
  for(const name of muscleNames){const option=document.createElement('option');option.value=name;option.textContent=name;muscleSelect.append(option);}
  muscleSelect.disabled=!muscleNames.length;
  for(const option of colorSelect.options)if(option.value!=='plain')option.disabled=!hasForces;
  colorSelect.value=hasForces?'force':'plain';
  const forceScale=DATA.frames.reduce((largest,f)=>Object.values(f.muscle_forces_N||{}).reduce((a,b)=>Math.max(a,b),largest),1);
  if(!hasForces&&externalSignals.length){byId('quality-summary').textContent='已绑定外部数据（'+externalSignals.length+' 个信号）';byId('quality-box').classList.add('info');byId('quality-details').textContent='按明确声明的单位、时间偏移和插值显示源数据；本视图未提供肌肉受力求解结果。';}
  if(hasForces){const failed=resultInfo.flatMap(r=>r.quality.checks.filter(c=>!c.passed).map(c=>r.label+' / '+c.name+': '+(c.value===null?'参考需求接近零':c.value.toFixed(3))+'，上限 '+c.limit));byId('quality-summary').textContent=failed.length?'质量检查：需复核（'+failed.length+' 项）':'质量检查：数值检查通过';byId('quality-box').classList.toggle('pass',!failed.length);byId('quality-details').textContent=failed.length?failed.join('；'):'残余力、辅助力矩和激活范围符合本次明确设置的阈值；仍需验证人体模型与实验数据。';}
  byId('primary-force-label').textContent=resultInfo[0]?.label||'当前模型';byId('comparison-force-label').textContent=resultInfo[1]?.label||'未提供对照';
  byId('download-muscle').disabled=!hasForces;
  byId('muscle-result-note').textContent=hasForces?'肌肉力为静态优化估计；管状粗细仅用于显示。'+(resultInfo[0].lowpass_cutoff_hz?'受力计算使用 '+resultInfo[0].lowpass_cutoff_hz+' Hz 滤波，动画显示输入动作。':''):'尚未绑定受力结果。红色仅表示肌肉路径。';
  byId('sample-note').textContent=`显示 ${DATA.frames.length} / ${DATA.source_rows} 个原始运动帧。蓝线为主运动，橙线为对比运动。`;
  byId('warning').textContent=DATA.warnings.map(w=>w==='Caller supplied visual geometry must match the current physical model, scale and frame identities.'?'已使用额外的外观模型，请核对尺寸与身体框架是否匹配。':w.replace('Missing/unapproved mesh ','未读取的表面文件：').replace('Unsupported visual geometry: ','暂未显示的几何类型：').replace('Missing physical frame ','缺少的模型框架：')).join('；');
  byId('error-label').textContent=`蓝色 0 — 红色 ${(DATA.error_color_range_m*1000).toFixed(1)} mm；参考：${DATA.error_reference==='experimental markers'?'实验标记':DATA.comparison_frames.length?'对比运动':'无参考数据'}。`;
  byId('compare').disabled=!DATA.comparison_frames.length;
  byId('errors').disabled=!DATA.frames.some(f=>Object.keys(f.marker_errors_m||{}).length);
  if(!gl){byId('failure').style.display='block';byId('failure').textContent='当前浏览器无法显示三维表面。请使用支持 WebGL 的浏览器；导出的坐标数据仍可独立读取。';document.body.dataset.viewerReady='false';return;}
  const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
  const program=gl.createProgram();
  gl.attachShader(program,shader(gl.VERTEX_SHADER,`attribute vec3 p;attribute vec3 n;uniform mat4 vp;uniform mat4 model;varying vec3 normal;void main(){gl_Position=vp*model*vec4(p,1.0);normal=mat3(model)*n;gl_PointSize=8.0;}`));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`precision mediump float;uniform vec4 color;uniform bool points;varying vec3 normal;void main(){if(points&&length(gl_PointCoord-vec2(.5))>.5)discard;float light=length(normal)<.01?1.:.35+.65*abs(dot(normalize(normal),normalize(vec3(.4,.8,1.))));gl_FragColor=vec4(color.rgb*light,color.a);}`));
  gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.useProgram(program);
  const loc={p:gl.getAttribLocation(program,'p'),n:gl.getAttribLocation(program,'n'),vp:gl.getUniformLocation(program,'vp'),model:gl.getUniformLocation(program,'model'),color:gl.getUniformLocation(program,'color'),points:gl.getUniformLocation(program,'points')};
  const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], subtract=(a,b)=>a.map((v,i)=>v-b[i]), cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]],dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),unit=a=>{let l=Math.hypot(...a)||1;return a.map(v=>v/l);};
  const multiply=(a,b)=>{const o=Array(16).fill(0);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;};
  const bounds=[];for(const frame of DATA.frames){for(const [path,m] of Object.entries(frame.transforms))if(path!='/ground')bounds.push(m.slice(12,15));bounds.push(...Object.values(frame.markers));}
  if(!bounds.length)bounds.push([0,0,0]);
  const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];for(const p of bounds)for(let i=0;i<3;i++){min[i]=Math.min(min[i],p[i]);max[i]=Math.max(max[i],p[i]);}const center=min.map((v,i)=>(v+max[i])/2);
  let radius=Math.max(.3,...max.map((v,i)=>v-min[i]));
  for(const m of DATA.meshes){let r=0;for(const p of m.vertices)r=Math.max(r,Math.hypot(...p));radius=Math.max(radius,r*1.8);}
  let yaw=.7,pitch=.25,distance=radius*2.7,index=0,playing=false,lastStamp=0,clock=DATA.frames[0].time,drag=null;
  const buffer=(positions,normals)=>{const p=gl.createBuffer(),n=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,p);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(positions),gl.STATIC_DRAW);gl.bindBuffer(gl.ARRAY_BUFFER,n);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(normals),gl.STATIC_DRAW);return {p,n,count:positions.length/3};};
  const meshes=DATA.meshes.map(mesh=>{const positions=[],normals=[];for(const t of mesh.triangles){const a=mesh.vertices[t[0]],b=mesh.vertices[t[1]],c=mesh.vertices[t[2]],normal=unit(cross(subtract(b,a),subtract(c,a)));positions.push(...a,...b,...c);normals.push(...normal,...normal,...normal);}return {...mesh,buffer:buffer(positions,normals)};});
  const draw=(b,model,color,mode=gl.TRIANGLES)=>{if(!b.count)return;gl.bindBuffer(gl.ARRAY_BUFFER,b.p);gl.enableVertexAttribArray(loc.p);gl.vertexAttribPointer(loc.p,3,gl.FLOAT,false,0,0);gl.bindBuffer(gl.ARRAY_BUFFER,b.n);gl.enableVertexAttribArray(loc.n);gl.vertexAttribPointer(loc.n,3,gl.FLOAT,false,0,0);gl.uniformMatrix4fv(loc.model,false,new Float32Array(model));gl.uniform4fv(loc.color,new Float32Array(color));gl.uniform1i(loc.points,mode===gl.POINTS);gl.drawArrays(mode,0,b.count);};
  const dispose=b=>{gl.deleteBuffer(b.p);gl.deleteBuffer(b.n);};
  const muscleCache=[];
  function muscleBuffer(frame){
    const width=+byId('muscle-width').value,existing=muscleCache.find(c=>c.frame===frame&&c.width===width);
    if(existing)return existing.items;
    const items=[],sides=8;
    for(const [name,path] of Object.entries(frame.muscle_paths||{})){
      const positions=[],normals=[];
      const lengths=path.slice(1).map((point,i)=>Math.hypot(...subtract(point,path[i]))),total=lengths.reduce((a,b)=>a+b,0);
      if(total<1e-10)continue;
      let along=0;
      for(let segment=0;segment<lengths.length;segment++){
        const a=path[segment],delta=subtract(path[segment+1],a),length=lengths[segment];if(length<1e-10)continue;
        const axis=unit(delta),u=unit(cross(axis,Math.abs(axis[1])<.9?[0,1,0]:[1,0,0])),v=cross(axis,u),steps=Math.max(1,Math.min(16,Math.ceil(length/.025)));
        const ring=(t,j)=>{const angle=2*Math.PI*j/sides,normal=u.map((x,i)=>x*Math.cos(angle)+v[i]*Math.sin(angle)),fraction=(along+t*length)/total,radius=.009*width*(.18+.82*Math.pow(Math.sin(Math.PI*Math.max(0,Math.min(1,fraction))),.7));return {point:a.map((x,i)=>x+t*delta[i]+radius*normal[i]),normal};};
        for(let k=0;k<steps;k++)for(let j=0;j<sides;j++){
          const p=ring(k/steps,j),q=ring(k/steps,j+1),r=ring((k+1)/steps,j),s=ring((k+1)/steps,j+1);
          for(const vertex of [p,r,q,q,r,s]){positions.push(...vertex.point);normals.push(...vertex.normal);}
        }
        along+=length;
      }
      items.push({name,buffer:buffer(positions,normals)});
    }
    const entry={frame,width,items};muscleCache.push(entry);
    while(muscleCache.length>2)for(const item of muscleCache.shift().items)dispose(item.buffer);
    return entry.items;
  }
  const errorColor=value=>{const t=Math.max(0,Math.min(1,value/DATA.error_color_range_m));return [.15+.7*t,.48-.24*t,.72-.5*t,1];};
  const muscleColor=(name,frame)=>{if(colorSelect.value==='plain')return [.73,.12,.16,1];const value=colorSelect.value==='activation'?frame.muscle_activations?.[name]:frame.muscle_forces_N?.[name]/forceScale,t=Math.max(0,Math.min(1,value||0));return [.14+.72*t,.48-.25*t,.75-.59*t,1];};
  function camera(){const eye=[center[0]+distance*Math.cos(pitch)*Math.sin(yaw),center[1]+distance*Math.sin(pitch),center[2]+distance*Math.cos(pitch)*Math.cos(yaw)],z=unit(subtract(eye,center)),x=unit(cross([0,1,0],z)),y=cross(z,x),view=[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1],near=radius/100,far=radius*150,f=1/Math.tan(Math.PI/8),aspect=canvas.width/canvas.height,projection=[f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0];return multiply(projection,view);}
  function modelDraw(frame,ghost=false){
    const bodyErrors={};for(const [name,error] of Object.entries(frame.marker_errors_m||{})){const body=DATA.marker_bodies[name];bodyErrors[body]=Math.max(bodyErrors[body]||0,error);}
    if(byId('surfaces').checked)for(const mesh of meshes){const transform=frame.transforms[mesh.frame];if(!transform||wbHidden.some(c=>(c.kind==='frame'&&c.name===mesh.frame)||(c.kind==='body'&&c.name===DATA.frame_to_body[mesh.frame])))continue;let color=ghost?[.95,.48,.12,.38]:byId('errors').checked&&Object.hasOwn(bodyErrors,DATA.frame_to_body[mesh.frame])?errorColor(bodyErrors[DATA.frame_to_body[mesh.frame]]):[...mesh.color,1];if(!ghost&&selectedComponent&&((selectedComponent.kind==='body'&&DATA.frame_to_body[mesh.frame]===selectedComponent.name)||(selectedComponent.kind==='frame'&&mesh.frame===selectedComponent.name)))color=[.1,.72,.86,1];color[3]*=wbOpacity;draw(mesh.buffer,transform,color);}
    if(byId('muscles').checked){for(const item of muscleBuffer(frame))if(!wbHidden.some(c=>c.kind==='muscle'&&c.name===item.name))draw(item.buffer,identity,ghost?[.95,.48,.12,.38]:muscleColor(item.name,frame));
      const path=frame.muscle_paths?.[muscleSelect.value];if(!ghost&&path){const points=[...path[0],...path.at(-1)],b=buffer(points,Array(6).fill(0));draw(b,identity,[1,.67,.08,1],gl.POINTS);dispose(b);}}
    if(byId('skeleton').checked){const points=[];for(const [a,b] of DATA.joint_links){const x=frame.transforms[a],y=frame.transforms[b];if(x&&y)points.push(...x.slice(12,15),...y.slice(12,15));}const data=buffer(points,Array(points.length).fill(0));draw(data,identity,ghost?[.95,.48,.12,.8]:[.15,.28,.39,1],gl.LINES);dispose(data);}
    if(byId('markers').checked&&!ghost)for(const [name,point] of Object.entries(frame.markers)){const data=buffer(point,[0,0,0]);draw(data,identity,byId('errors').checked&&Object.hasOwn(frame.marker_errors_m||{},name)?errorColor(frame.marker_errors_m[name]):[.88,.35,.16,1],gl.POINTS);dispose(data);}
  }
  function render(){const ratio=Math.min(devicePixelRatio||1,2),w=Math.round(canvas.clientWidth*ratio),h=Math.round(canvas.clientHeight*ratio);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}gl.viewport(0,0,w,h);gl.clearColor(.96,.975,.985,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.uniformMatrix4fv(loc.vp,false,new Float32Array(camera()));if(wbOpacity<1){gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);}modelDraw(DATA.frames[index]);gl.disable(gl.BLEND);if(wbMeasure.length){const pts=wbMeasure.map(c=>c.kind==='marker'?DATA.frames[index].markers[c.name]:DATA.frames[index].transforms[c.name]?.slice(12,15));if(pts.every(Boolean)){const b=buffer(pts.flat(),Array(pts.length*3).fill(0));draw(b,identity,[.9,.4,.06,1],gl.LINE_STRIP);draw(b,identity,[.9,.4,.06,1],gl.POINTS);dispose(b);}}if(DATA.comparison_frames.length&&byId('compare').checked){gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);modelDraw(DATA.comparison_frames[index],true);gl.depthMask(true);gl.disable(gl.BLEND);}byId('time').textContent=DATA.frames[index].time.toFixed(3)+' s';byId('timeline').value=index;document.body.dataset.frameIndex=index;document.body.dataset.time=DATA.frames[index].time;plot();musclePlot();signalPlot();}
  const plotCanvas=byId('plot'),coordinate=byId('coordinate');for(const name of Object.keys(DATA.coordinate_units)){const option=document.createElement('option');option.value=name;option.textContent=name;coordinate.append(option);}
  function plot(){const ratio=Math.min(devicePixelRatio||1,2),w=plotCanvas.clientWidth,h=220;plotCanvas.width=w*ratio;plotCanvas.height=h*ratio;const c=plotCanvas.getContext('2d');c.scale(ratio,ratio);c.clearRect(0,0,w,h);const name=coordinate.value,values=DATA.frames.map(f=>f.coordinate_values[name]),other=DATA.comparison_frames.map(f=>f.coordinate_values[name]);let lo=Math.min(...values,...other),hi=Math.max(...values,...other);if(hi-lo<1e-10){lo-=.05;hi+=.05;}let pad=(hi-lo)*.1;lo-=pad;hi+=pad;const t0=DATA.frames[0].time,t1=DATA.frames.at(-1).time,x=t=>42+(w-55)*(t-t0)/(t1-t0||1),y=v=>185-150*(v-lo)/(hi-lo);c.strokeStyle='#d2dfe8';c.lineWidth=1;c.strokeRect(42,35,w-55,150);c.fillStyle='#526b80';c.font='11px system-ui';c.fillText(hi.toFixed(3),0,39);c.fillText(lo.toFixed(3),0,185);c.fillText(DATA.coordinate_units[name],1,20);c.fillText(t0.toFixed(2),40,204);c.fillText(t1.toFixed(2)+' s',w-48,204);for(const [frames,color] of [[DATA.frames,'#176e96'],[DATA.comparison_frames,'#db862c']]){c.beginPath();c.strokeStyle=color;c.lineWidth=2;frames.forEach((f,i)=>{const a=x(f.time),b=y(f.coordinate_values[name]);i?c.lineTo(a,b):c.moveTo(a,b);});c.stroke();}c.strokeStyle='#d34636';c.beginPath();c.moveTo(x(DATA.frames[index].time),30);c.lineTo(x(DATA.frames[index].time),190);c.stroke();}
  function musclePlot(){
    const name=muscleSelect.value,frame=DATA.frames[index],volume=DATA.muscle_volumes?.[name],format=(v,n=1)=>Number.isFinite(v)?v.toFixed(n):'—';
    byId('muscle-force').textContent=format(frame.muscle_forces_N?.[name]);byId('muscle-activation').textContent=format(frame.muscle_activations?.[name],3);byId('muscle-comparison').textContent=format(frame.comparison_muscle_forces_N?.[name]);byId('muscle-volume').textContent=format(volume?.volume_cm3);
    byId('muscle-volume-source').textContent=!volume?'未提供体积数据。':volume.source==='supplied_measurement'?'体积来源：提供测量；'+volume.source_label:'体积来源：参数估算；假设肌肉比张力 '+(volume.specific_tension_Pa/1e6).toFixed(3)+' MPa。';
    byId('muscle-volume-label').textContent=!volume?'肌肉体积 cm³':volume.source==='supplied_measurement'?'提供测量体积 cm³':'参数估算体积 cm³';
    byId('muscle-color-legend').textContent=colorSelect.value==='plain'?'统一红色；无受力含义。':colorSelect.value==='activation'?'蓝色 0 — 红色 1；肌肉激活估计。':'蓝色 0 — 红色 '+forceScale.toFixed(0)+' N；所有显示帧共用同一色标。';
    const target=byId('muscle-plot'),ratio=Math.min(devicePixelRatio||1,2),w=target.clientWidth,h=210;target.width=w*ratio;target.height=h*ratio;const c=target.getContext('2d');c.scale(ratio,ratio);c.clearRect(0,0,w,h);if(!hasForces||w<1)return;
    const primary=DATA.frames.map(f=>f.muscle_forces_N[name]),secondary=resultInfo[1]?DATA.frames.map(f=>f.comparison_muscle_forces_N[name]):[],high=Math.max(1,...primary,...secondary)*1.08,t0=DATA.frames[0].time,t1=DATA.frames.at(-1).time,x=t=>43+(w-55)*(t-t0)/(t1-t0),y=v=>177-145*v/high;
    c.strokeStyle='#d2dfe8';c.strokeRect(43,32,w-55,145);c.fillStyle='#526b80';c.font='11px system-ui';c.fillText(high.toFixed(0),0,37);c.fillText('0 N',5,177);c.fillText(t0.toFixed(2),43,198);c.fillText(t1.toFixed(2)+' s',w-48,198);
    for(const [values,color] of [[primary,'#176e96'],[secondary,'#db862c']]){c.beginPath();c.strokeStyle=color;c.lineWidth=2;values.forEach((v,i)=>{const a=x(DATA.frames[i].time),b=y(v);i?c.lineTo(a,b):c.moveTo(a,b);});c.stroke();}c.strokeStyle='#ce3f3f';c.beginPath();c.moveTo(x(frame.time),28);c.lineTo(x(frame.time),182);c.stroke();
    document.body.dataset.selectedMuscle=name;document.body.dataset.muscleForce=frame.muscle_forces_N[name];
  }
  function select(i){index=Math.max(0,Math.min(DATA.frames.length-1,i));clock=DATA.frames[index].time;render();}
  byId('timeline').max=DATA.frames.length-1;byId('timeline').addEventListener('input',()=>select(+byId('timeline').value));
  byId('play').addEventListener('click',()=>{playing=!playing;byId('play').textContent=playing?'暂停':'播放';lastStamp=0;document.body.dataset.playing=playing;});
  for(const id of ['surfaces','skeleton','markers','compare','errors','coordinate','muscles','selected-muscle','muscle-color'])byId(id).addEventListener('change',render);
  function showTab(name){for(const value of ['muscle','display','coordinate','signals']){byId('panel-'+value).hidden=value!==name;byId('tab-'+value).classList.toggle('active',value===name);}render();}
  for(const name of ['muscle','display','coordinate','signals'])byId('tab-'+name).addEventListener('click',()=>showTab(name));
  byId('download-muscle').addEventListener('click',()=>{if(!hasForces)return;const name=muscleSelect.value,quality=resultInfo.some(r=>r.quality.status!=='pass')?'needs_review':'pass',rows=['time_s,current_force_N,reference_force_N,current_activation,quality_status,interpolation'];for(const frame of DATA.frames)rows.push([frame.time,frame.muscle_forces_N[name],frame.comparison_muscle_forces_N?.[name]??'',frame.muscle_activations[name],quality,DATA.muscle_data_interpolation||'none'].join(','));const url=URL.createObjectURL(new Blob(['\ufeff'+rows.join('\r\n')+'\r\n'],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=(name.replace(/[^a-z0-9_-]/gi,'_')||'muscle')+'_forces.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  byId('muscle-width').addEventListener('input',render);
  byId('reset').addEventListener('click',()=>{yaw=.7;pitch=.25;distance=radius*2.7;render();});
  function pickMuscle(event){const rect=canvas.getBoundingClientRect(),mouse=[event.clientX-rect.left,event.clientY-rect.top],vp=camera();let best=81,name=null;
    const project=p=>{const q=[...p,1],v=[0,0,0,0];for(let r=0;r<4;r++)for(let k=0;k<4;k++)v[r]+=vp[k*4+r]*q[k];return v[3]>0?[(v[0]/v[3]+1)*rect.width/2,(1-v[1]/v[3])*rect.height/2]:null;};
    for(const [key,points] of Object.entries(DATA.frames[index].muscle_paths||{}))for(let i=1;i<points.length;i++){const a=project(points[i-1]),b=project(points[i]);if(!a||!b)continue;const d=[b[0]-a[0],b[1]-a[1]],t=Math.max(0,Math.min(1,((mouse[0]-a[0])*d[0]+(mouse[1]-a[1])*d[1])/(d[0]*d[0]+d[1]*d[1]||1))),dist=(mouse[0]-a[0]-t*d[0])**2+(mouse[1]-a[1]-t*d[1])**2;if(dist<best){best=dist;name=key;}}
    if(name){muscleSelect.value=name;if(!signalForComponent('muscle',name))showTab('muscle');}}
  let pointerStart=null;
  canvas.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];pointerStart=drag.slice();canvas.setPointerCapture(e.pointerId);});canvas.addEventListener('pointerup',e=>{drag=null;if(pointerStart&&Math.hypot(e.clientX-pointerStart[0],e.clientY-pointerStart[1])<4){if(DATA.workbench_embedded)wbPick(e);else pickMuscle(e);}if(DATA.workbench_embedded)wbSend('camera',{yaw,pitch,zoom:distance/radius});pointerStart=null;});canvas.addEventListener('pointermove',e=>{if(!drag)return;yaw+=(e.clientX-drag[0])*.008;pitch=Math.max(-1.4,Math.min(1.4,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];render();});canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(radius*.3,Math.min(radius*100,distance*Math.exp(e.deltaY*.001)));render();wbSend('camera',{yaw,pitch,zoom:distance/radius});},{passive:false});window.addEventListener('resize',render);

  const externalSelect=byId('external-signal');
  for(const signal of externalSignals){const option=document.createElement('option');option.value=signal.id;option.textContent=signal.label+' · '+signal.unit;externalSelect.append(option);}
  for(const id of ['external-signal','download-signal','download-context','tab-signals'])byId(id).disabled=!externalSignals.length;
  selectedComponent=externalSignals[0]?.component||null;
  function selectedSignal(){return externalSignals.find(s=>s.id===externalSelect.value);}
  function signalForComponent(kind,name){const signal=externalSignals.find(s=>s.component?.kind===kind&&s.component.name===name);if(!signal)return false;externalSelect.value=signal.id;selectedComponent=signal.component;showTab('signals');return true;}
  function chooseSignal(){const signal=selectedSignal();selectedComponent=signal?.component||null;if(selectedComponent?.kind==='muscle')muscleSelect.value=selectedComponent.name;if(selectedComponent?.kind==='coordinate')coordinate.value=selectedComponent.name;render();}
  externalSelect.addEventListener('change',chooseSignal);
  function signalPlot(){
    const signal=selectedSignal();if(!signal)return;
    const value=signal.frame_values[index];byId('external-value').textContent=Number(value).toPrecision(6);byId('external-unit').textContent=signal.unit;byId('external-source').textContent=signal.source_label;
    byId('external-component').textContent=signal.component?'绑定组件：'+signal.component.kind+' / '+signal.component.name:'未绑定组件；作为独立时序信号查看。';
    const provenance=DATA.signal_provenance[signal.source_index];byId('external-alignment').textContent='时间单位 '+provenance.time_unit+'；偏移 '+provenance.time_offset_s+' s；'+(signal.interpolation==='none'?'同时间点':signal.interpolation==='previous'?'前值保持':'线性插值')+'；最大间隔 '+signal.max_gap_s+' s。曲线保留 '+signal.times.length+' 个源采样点，姿态显示 '+DATA.frames.length+' 帧。';
    document.body.dataset.selectedSignal=signal.id;document.body.dataset.externalValue=value;document.body.dataset.selectedComponent=signal.component?JSON.stringify(signal.component):'';
    const target=byId('external-plot'),w=target.clientWidth;if(w<1)return;const ratio=Math.min(devicePixelRatio||1,2),h=220;target.width=w*ratio;target.height=h*ratio;const c=target.getContext('2d');c.scale(ratio,ratio);c.clearRect(0,0,w,h);
    const t0=DATA.frames[0].time,t1=DATA.frames.at(-1).time,visible=signal.values.filter((v,i)=>signal.times[i]>=t0&&signal.times[i]<=t1);visible.push(...signal.frame_values);let lo=Math.min(...visible),hi=Math.max(...visible);if(hi-lo<1e-12){lo-=.5;hi+=.5;}const pad=(hi-lo)*.08;lo-=pad;hi+=pad;
    const x=t=>48+(w-61)*(t-t0)/(t1-t0),y=v=>185-150*(v-lo)/(hi-lo);c.strokeStyle='#d2dfe8';c.strokeRect(48,35,w-61,150);c.fillStyle='#526b80';c.font='11px system-ui';c.fillText(hi.toPrecision(3),0,39);c.fillText(lo.toPrecision(3),0,185);c.fillText(signal.unit,2,20);c.fillText(t0.toFixed(2),48,207);c.fillText(t1.toFixed(2)+' s',w-48,207);
    c.save();c.beginPath();c.rect(48,35,w-61,150);c.clip();c.strokeStyle='#176e96';c.lineWidth=2;c.beginPath();let drawing=false;
    signal.times.forEach((t,i)=>{if(t<t0-1e-9||t>t1+1e-9){drawing=false;return;}const gap=i&&t-signal.times[i-1]>signal.max_gap_s+1e-12;if(!drawing||gap)c.moveTo(x(t),y(signal.values[i]));else{if(signal.interpolation==='previous')c.lineTo(x(t),y(signal.values[i-1]));c.lineTo(x(t),y(signal.values[i]));}drawing=true;});c.stroke();c.restore();c.strokeStyle='#ce3f3f';c.beginPath();c.moveTo(x(DATA.frames[index].time),30);c.lineTo(x(DATA.frames[index].time),190);c.stroke();c.fillStyle='#176e96';c.beginPath();c.arc(x(DATA.frames[index].time),y(value),3,0,Math.PI*2);c.fill();
  }
  byId('external-plot').addEventListener('pointerdown',event=>{if(!externalSignals.length)return;const rect=byId('external-plot').getBoundingClientRect(),fraction=Math.max(0,Math.min(1,(event.clientX-rect.left-48)/(rect.width-61))),time=DATA.frames[0].time+fraction*(DATA.frames.at(-1).time-DATA.frames[0].time);let closest=0;for(let i=1;i<DATA.frames.length;i++)if(Math.abs(DATA.frames[i].time-time)<Math.abs(DATA.frames[closest].time-time))closest=i;playing=false;byId('play').textContent='播放';select(closest);});
  function downloadFile(filename,type,data){const url=URL.createObjectURL(new Blob([data],{type})),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  byId('download-signal').addEventListener('click',()=>{const s=selectedSignal();if(!s)return;const safe=v=>{let text=String(v);if(typeof v==='string'&&/^[=+\-@\t\r]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';},rows=[['aligned_time_s','value','unit','source_sha256'],...s.times.map((t,i)=>[t,s.values[i],s.unit,DATA.signal_provenance[s.source_index].sha256])];downloadFile(s.id+'_signal.csv','text/csv;charset=utf-8','\ufeff'+rows.map(r=>r.map(safe).join(',')).join('\r\n')+'\r\n');});
  byId('download-context').addEventListener('click',()=>{const s=selectedSignal();if(!s)return;downloadFile('selection.json','application/json',JSON.stringify({schema:'opensim_visual_selection_v1',physics_signature:DATA.physics_signature,component:s.component,frame_index:index,aligned_time_s:DATA.frames[index].time,signal_id:s.id,signal_label:s.label,value:s.frame_values[index],unit:s.unit,source_sha256:DATA.signal_provenance[s.source_index].sha256},null,2));});


  function wbPick(event){
    const rect=canvas.getBoundingClientRect(),mouse=[event.clientX-rect.left,event.clientY-rect.top],vp=camera(),frame=DATA.frames[index];
    const project=p=>{const q=[...p,1],v=[0,0,0,0];for(let r=0;r<4;r++)for(let k=0;k<4;k++)v[r]+=vp[k*4+r]*q[k];return v[3]>0?[(v[0]/v[3]+1)*rect.width/2,(1-v[1]/v[3])*rect.height/2,v[2]/v[3]]:null;};
    let found=null,best=64;
    if(byId('muscles').checked)for(const [name,path] of Object.entries(frame.muscle_paths||{})){if(wbHidden.some(c=>c.kind==='muscle'&&c.name===name))continue;for(let i=1;i<path.length;i++){const a=project(path[i-1]),b=project(path[i]);if(!a||!b)continue;const d=[b[0]-a[0],b[1]-a[1]],t=Math.max(0,Math.min(1,((mouse[0]-a[0])*d[0]+(mouse[1]-a[1])*d[1])/(d[0]**2+d[1]**2||1))),v=(mouse[0]-a[0]-t*d[0])**2+(mouse[1]-a[1]-t*d[1])**2;if(v<best){best=v;found={kind:'muscle',name};}}}
    let depth=Infinity;
    if(!found&&byId('surfaces').checked)for(const mesh of meshes){const m=frame.transforms[mesh.frame];if(!m||wbHidden.some(c=>(c.kind==='frame'&&c.name===mesh.frame)||(c.kind==='body'&&c.name===DATA.frame_to_body[mesh.frame])))continue;
      const vertices=mesh.vertices.map(p=>project([m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12],m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13],m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14]]));
      for(const tri of mesh.triangles){const [a,b,c]=tri.map(i=>vertices[i]);if(!a||!b||!c)continue;const den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);if(Math.abs(den)<1e-9)continue;const u=((b[1]-c[1])*(mouse[0]-c[0])+(c[0]-b[0])*(mouse[1]-c[1]))/den,v=((c[1]-a[1])*(mouse[0]-c[0])+(a[0]-c[0])*(mouse[1]-c[1]))/den,w=1-u-v,z=u*a[2]+v*b[2]+w*c[2];if(u>=0&&v>=0&&w>=0&&z>=-1&&z<=1&&z<depth){depth=z;found=mesh.frame===DATA.frame_to_body[mesh.frame]?{kind:'body',name:mesh.frame}:{kind:'frame',name:mesh.frame};}}
    }
    if(found){selectedComponent=found;if(found.kind==='muscle')muscleSelect.value=found.name;wbSend('selection',found);render();}
  }
  if(DATA.workbench_embedded)window.addEventListener('message',event=>{
    const msg=event.data;if(event.source!==parent||msg?.channel!==DATA.workbench_channel||msg.event!=='state')return;
    const v=msg.payload;if(!v||typeof v!=='object')return;
    if(v.camera&&[v.camera.yaw,v.camera.pitch,v.camera.zoom].every(Number.isFinite)){yaw=v.camera.yaw;pitch=Math.max(-1.4,Math.min(1.4,v.camera.pitch));distance=radius*Math.max(.3,Math.min(100,v.camera.zoom));}
    if(v.layers)for(const k of ['surfaces','muscles','markers','skeleton'])if(typeof v.layers[k]==='boolean')byId(k).checked=v.layers[k];
    if(Array.isArray(v.hidden))wbHidden=v.hidden;
    if(Number.isFinite(v.opacity))wbOpacity=Math.max(.05,Math.min(1,v.opacity));
    if(Array.isArray(v.measurement))wbMeasure=v.measurement;
    if(Object.hasOwn(v,'selected'))selectedComponent=v.selected;
    if(selectedComponent?.kind==='muscle')muscleSelect.value=selectedComponent.name;
    if(Number.isInteger(v.frame))select(v.frame);else render();
    document.body.dataset.workbenchSelection=JSON.stringify(selectedComponent);document.body.dataset.workbenchCamera=JSON.stringify({yaw,pitch,zoom:distance/radius});
  });

  function tick(stamp){if(playing){if(lastStamp){clock+=(stamp-lastStamp)/1000*(+byId('speed').value);const first=DATA.frames[0].time,last=DATA.frames.at(-1).time;if(clock>last)clock=first;while(index<DATA.frames.length-1&&DATA.frames[index+1].time<=clock)index++;if(clock<DATA.frames[index].time)index=0;render();}lastStamp=stamp;}requestAnimationFrame(tick);}
  const initial=Number(new URLSearchParams(location.search).get('frame'));select(Number.isInteger(initial)?initial:0);showTab(externalSignals.length?'signals':hasForces?'muscle':'display');document.body.dataset.viewerReady='true';document.body.dataset.meshCount=meshes.length;wbSend('ready',{});requestAnimationFrame(tick);
})();
