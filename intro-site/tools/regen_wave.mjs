import { writeFileSync } from 'fs';
const KEY='sk-QKQiaX30FgJBXB6FKoE6EAj4rGyanfhrhioopXyz4tVawwCL';
const ANCHOR='https://files.evolink.ai/004YZHRNKD9Q81QEGY/images/png/1785603108_c86c6cbf';
const CHAR='以参考图中的卡通男孩角色为原型，严格保持完全相同的角色设定：棕色短发带一撮蓝色挑染、戴在眼睛上的青色半透明科技护目镜（镜片上有HUD数据反光）、橙色拼接深蓝色的连帽衫（帽子和袖子是深蓝色、衣身是橙色、带发光的青色线条装饰）、机甲风格的左臂、扁平卡通插画画风、粗描边。';
const prompt=`${CHAR}生成该角色的半身立绘：身体正面朝向观众，右臂弯曲抬起、手掌在肩膀旁边挥手打招呼，手臂和手掌必须与身体自然相连，严禁出现悬空、漂浮、断开的手。张嘴灿烂微笑。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。`;
const r=await fetch('https://api.evolink.ai/v1/images/generations',{method:'POST',headers:{Authorization:`Bearer ${KEY}`,'Content-Type':'application/json'},body:JSON.stringify({model:'gemini-3-pro-image-preview',prompt,size:'3:4',quality:'2K',image_urls:[ANCHOR]})});
const d=await r.json(); console.log('task:',d.id);
for(;;){await new Promise(s=>setTimeout(s,12000));
 const t=await (await fetch('https://api.evolink.ai/v1/tasks/'+d.id,{headers:{Authorization:`Bearer ${KEY}`}})).json();
 if(t.status==='completed'){const buf=Buffer.from(await (await fetch(t.results[0])).arrayBuffer());
   writeFileSync(new URL('../raw_生图原图/sp_wave.png',import.meta.url),buf);console.log('✅ sp_wave 重生成完成',buf.length);break;}
 if(t.status==='failed'){console.log('❌',JSON.stringify(t));break;}}
