#!/usr/bin/env node
/* LebotClaw 橙光介绍站 · EvoLink 批量生图脚本
 * 用法: node gen_images.mjs [only_name1,only_name2]   （不带参数=全部生成）
 * 背景: 16:9 2K 无参考图；立绘: 3:4 2K + 小博锚点参考图 + 纯黑底
 * 结果下载到 ../raw_生图原图/ （URL 24h 过期，必须立即下载）
 */
import { writeFileSync, existsSync, mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const KEY = 'sk-QKQiaX30FgJBXB6FKoE6EAj4rGyanfhrhioopXyz4tVawwCL';
const API = 'https://api.evolink.ai/v1/images/generations';
const TASK = 'https://api.evolink.ai/v1/tasks/';
const ANCHOR = 'https://files.evolink.ai/004YZHRNKD9Q81QEGY/images/png/1786927916_bea90f18';

const DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'raw_生图原图');
mkdirSync(DIR, { recursive: true });

/* 小博角色一致性描述（每张立绘都带） */
const CHAR = '以参考图中的卡通男孩角色为原型，严格保持完全相同的角色设定：棕色短发带一撮蓝色挑染、戴在眼睛上的青色半透明科技护目镜（镜片上有HUD数据反光）、橙色拼接深蓝色的连帽衫（帽子和袖子是深蓝色、衣身是橙色、带发光的青色线条装饰）、机甲风格的左臂、扁平卡通插画画风、粗描边。';
const CHAR_NOGOGGLES = '以参考图中的卡通男孩角色为原型，保持同一个小博的角色一致性：棕色短发带一撮蓝色挑染、橙色拼接深蓝色的连帽衫、发光的青色线条装饰、机甲风格的左臂、扁平卡通插画画风、粗描边。唯一角色改动：彻底去掉护目镜，让两只大眼睛完整、清晰、自然地露出。脸上和头部不得出现任何眼镜、护目镜、镜片、镜框、绑带、HUD、面罩或头戴设备。';

const BG_STYLE = '扁平科技卡通风格插画，视觉小说游戏背景，深蓝色夜空主色调，亮蓝色和橙色霓虹点缀，光影干净，构图大气，画面中不要出现任何人物，不要出现任何文字、字母、水印。';

const JOBS = [
  /* ---------- 背景 16:9 ---------- */
  /* v3（2026-08-17）：通用智能玩伴叙事。使用新文件名，保留 v2 原图以便回退。 */
  { name: 'bg_meet_v3', size: '16:9', prompt: `星空下温暖的未来感秘密基地入口，圆形舷窗外能看到银河，室内有柔软沙发、暖橙色小夜灯和一条迎接新朋友的发光步道，像孩子们放学后会来的梦幻俱乐部，不是学校、教室或实验室。画面中央和右侧留出角色与对话框空间。${BG_STYLE}` },
  { name: 'bg_capabilities_v3b', size: '16:9', prompt: `充满想象力的未来创作工坊，空中漂浮着画布与彩色画笔光效、语音波形、相册画面、聊天气泡轮廓、放大镜和知识星球；中心是一颗会根据不同任务切换颜色的多面晶体 AI 核心，表现自动切换最合适的大脑。不出现闹钟、时钟、日历、提醒、计划表、公式或教材。活泼、友好、适合儿童。${BG_STYLE}` },
  { name: 'bg_growth_v3', size: '16:9', prompt: `梦幻的陪伴成长花园，发光的记忆星星沿蓝色光带汇聚成一棵成长之树，树枝上挂着相册、爱心、兴趣收藏、技能徽章和小工具图标，远处有记录共同旅程的星河道路；温柔、安全、有长期陪伴感，不出现学校、课本和成绩元素。${BG_STYLE}` },
  { name: 'bg_friends_v3', size: '16:9', prompt: `清晨星空渐变成日出的未来感屋顶花园，两张并排的小椅子面向发光城市和远方银河，桌上放着两杯果汁，周围有温暖的橙色灯串和轻轻飘动的蓝橙彩带，表达两个好朋友刚刚开始共同冒险；安静温暖，不是毕业典礼或舞台。${BG_STYLE}` },
  { name: 'bg_welcome', size: '16:9', prompt: `未来感科技学院的入口大门，巨大拱门上悬浮着全息蓝色光屏和旋转的数据粒子，门前一条发光的步道延伸到画面深处，夜晚星空，温暖橙色路灯点缀。${BG_STYLE}` },
  { name: 'bg_agents', size: '16:9', prompt: `圆形科技大厅内部，穹顶是星空投影，大厅里环绕着五个不同颜色发光的学科主题传送门展台：蓝色（数学公式光效）、红色（书卷光效）、紫色（字母光效）、绿色（烧瓶光效）、橙色（星星光效），地面有发光圆环纹路。${BG_STYLE}` },
  { name: 'bg_memory', size: '16:9', prompt: `梦幻的记忆宫殿场景，空中漂浮着发光的水晶、档案卡片和相册，蓝色数据流光线把卡片连成星河，蓝紫色调，温柔梦幻。${BG_STYLE}` },
  { name: 'bg_tools', size: '16:9', prompt: `卡通风格的实验室工作台，桌上整齐摆放着发光的计算器、厚字典、打开的知识书籍、圆形计时器，背后是挂满工具的洞洞板墙，蓝橙色灯光，明亮整洁。${BG_STYLE}` },
  { name: 'bg_dashboard', size: '16:9', prompt: `未来感控制台室，一整面弧形大屏幕墙，屏幕上有数据图表、聊天气泡、日历提醒的蓝色全息界面，屏幕前一把炫酷的椅子，深色科技氛围。${BG_STYLE}` },
  { name: 'bg_finale', size: '16:9', prompt: `星空下的庆典舞台，蓝色和橙色烟花在夜空绽放，发光彩带和气球，舞台灯光璀璨，地面反射星光，梦幻庆祝氛围。${BG_STYLE}` },

  /* ---------- 小博立绘 3:4 纯黑底 ---------- */
  { name: 'sp_wave', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：单手高高举起挥手打招呼，张嘴灿烂微笑，热情友好。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_smile', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：双手自然放在身前，温柔开心地微笑，亲切可爱。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_point', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：单手伸出食指指向斜上方，另一只手背在身后，表情自信，像在讲解知识的小老师。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_think', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：单手托着下巴，头微微歪向一边，眉毛上扬，表情好奇地在思考提问。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_excited', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：双手握拳举到胸前，身体微微前倾，眼睛发亮，张大嘴兴奋欢呼。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_proud', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：单手竖起大拇指，自信地眨眼微笑，鼓励夸奖的样子。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_curious', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：单手抬起伸出食指、像要提问，眉毛微挑，表情好奇又期待。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_serious', size: '3:4', ref: true, prompt: `${CHAR}生成该角色的半身立绘：双手交叉抱在胸前，表情认真专注，像在讲重要的事情。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },

  /* ---------- v3 无护目镜立绘：保留旧版以便回退 ---------- */
  { name: 'sp_wave_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：右臂弯曲抬起，手掌在肩膀旁边挥手打招呼，手臂和手掌必须与身体自然相连，张嘴灿烂微笑，热情友好。严禁悬空、漂浮或断开的手。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_smile_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：双手自然放在身前，温柔开心地微笑，亲切可爱。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_point_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：单手伸出食指指向斜上方，另一只手自然收在身侧，表情自信，像在介绍有趣的新发现。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_excited_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：双手握拳举到胸前，身体微微前倾，双眼发亮，张大嘴兴奋欢呼。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_proud_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：单手竖起大拇指，自信地眨眼微笑，是鼓励和夸奖的样子。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_curious_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：单手抬起伸出食指、像要提问，眉毛微挑，表情好奇又期待。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
  { name: 'sp_serious_ng_v3', size: '3:4', ref: true, prompt: `${CHAR_NOGOGGLES}生成该角色的半身立绘：双手交叉抱在胸前，表情认真专注，像在讲重要的事情。纯黑色背景，角色完整居中，光线均匀，适合后期抠图。` },
];

const only = process.argv[2] ? process.argv[2].split(',') : null;
const jobs = only ? JOBS.filter(j => only.includes(j.name)) : JOBS;

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function submit(job) {
  const body = { model: 'gemini-3-pro-image-preview', prompt: job.prompt, size: job.size, quality: '2K' };
  if (job.ref) body.image_urls = [ANCHOR];
  const res = await fetch(API, {
    method: 'POST',
    headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const d = await res.json();
  if (!d.id) throw new Error(`提交失败 ${job.name}: ${JSON.stringify(d)}`);
  return d.id;
}

async function poll(id) {
  for (;;) {
    await sleep(12000);
    const res = await fetch(TASK + id, { headers: { Authorization: `Bearer ${KEY}` } });
    const d = await res.json();
    if (d.status === 'completed') return d.results[0];
    if (d.status === 'failed') throw new Error(`任务失败: ${JSON.stringify(d.error || d)}`);
  }
}

async function run(job) {
  const out = join(DIR, job.name + '.png');
  if (existsSync(out)) { console.log(`⏭  ${job.name} 已存在，跳过`); return; }
  try {
    const id = await submit(job);
    console.log(`📤 ${job.name} → ${id}`);
    const url = await poll(id);
    const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
    writeFileSync(out, buf);
    console.log(`✅ ${job.name} 完成 (${(buf.length / 1024).toFixed(0)}KB)`);
  } catch (e) {
    console.log(`❌ ${job.name} 失败: ${e.message}`);
  }
}

console.log(`共 ${jobs.length} 个任务，并行提交…`);
await Promise.all(jobs.map(run));
console.log('全部结束');
