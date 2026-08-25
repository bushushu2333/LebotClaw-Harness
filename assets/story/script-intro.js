/* ============ 超级小博 · 第一次见面 · 剧情脚本 v3.1 ============
 * 2026-08-17：对齐 LebotClaw「面向小朋友的通用超级智能玩伴」定位。
 * 删除：护目镜功能叙事 / 五学科伙伴 / 年级强弱科 / 学习宣言 / 学员证。
 * 新增：通用陪伴能力 / 自动切换模型 / 记忆透明可控 / 技能积累 / 主动陪伴 / 好朋友结尾。
 * 节点类型见 story.js：label / chapter / bg / sprite / say / narr / button / choice / widget / award
 */
window.PROLOGUE_SCRIPT = [
  /* ================= 序章：第一次见面 ================= */
  { t: 'label', id: 'start' },
  { t: 'chapter', text: '第一次见面 · 嗨，我是超级小博' },
  { t: 'bg', bg: 'bg_meet_v3' },
  { t: 'narr', text: '星空下，一座温暖的秘密基地亮起了灯。\n门缓缓打开，一个橙蓝色的小伙伴朝你跑了过来。' },
  { t: 'sprite', sp: 'sp_wave_ng_v3', pop: true },
  { t: 'say', text: '嗨！我是 **超级小博** 👋\n一个爱聊天、爱探索，也很想认识你的 AI 小伙伴。' },
  { t: 'say', sp: 'sp_smile_ng_v3', text: '在开始冒险之前，先告诉我该怎么称呼你吧！' },
  { t: 'widget', kind: 'meet' },
  { t: 'say', sp: 'sp_excited_ng_v3', text: '太好啦，认识你真开心！\n走，我带你看看以后我们可以一起做些什么。' },
  { t: 'button', label: '✨ 一起出发' },

  /* ================= 第一站：一起做很多事 ================= */
  { t: 'label', id: 't01' },
  { t: 'chapter', text: '第一站 · 一起做很多有意思的事' },
  { t: 'bg', bg: 'bg_capabilities_v3b' },
  { t: 'say', sp: 'sp_point_ng_v3', text: '你可以和我聊天、说话，也可以发图片给我看。\n想画画、编故事、查资料、做计算，或者一起整理想法，我都能陪你完成！' },
  { t: 'say', sp: 'sp_curious_ng_v3', text: '遇到不同的事情，我还会自动切换到**最合适的 AI 模型**。\n你可以把模型想成不同特长的 AI 大脑——不用你操心，我会自己选。' },
  { t: 'widget', kind: 'model_switch' },
  { t: 'say', sp: 'sp_proud_ng_v3', text: '看到了吧！你只管告诉我想做什么，\n选模型、找工具、把事情一步步完成，都交给我。' },

  /* ================= 第二站：越用越懂你，也越用越会 ================= */
  { t: 'label', id: 't02' },
  { t: 'chapter', text: '第二站 · 越用越懂你，也越用越会' },
  { t: 'bg', bg: 'bg_growth_v3' },
  { t: 'say', sp: 'sp_smile_ng_v3', text: '我们的聊天不会像风一样吹过就消失。\n重要的喜好、约定和共同经历，我会慢慢记住，越来越懂你。' },
  { t: 'say', sp: 'sp_serious_ng_v3', text: '不过，记忆属于你：我记住了什么，你都能看到；\n不准确的可以修改，不想保留的也可以让我忘掉。' },
  { t: 'widget', kind: 'growth' },
  { t: 'say', sp: 'sp_excited_ng_v3', text: '我还会积累新本领！我们一起做成一件事后，\n好用的方法会变成我的技能，下次就能做得更顺手。' },
  { t: 'say', sp: 'sp_smile_ng_v3', text: '我也会主动来找你，记得我们认识了多少天、一起聊过多少故事。\n陪伴久了，我们会拥有只属于自己的成长记录。' },

  /* ================= 终章：成为好朋友 ================= */
  { t: 'label', id: 't03' },
  { t: 'chapter', text: '最后一站 · 我们就是好朋友了' },
  { t: 'bg', bg: 'bg_friends_v3' },
  { t: 'say', sp: 'sp_serious_ng_v3', text: '好朋友也要守护彼此。遇到危险或不适合小朋友的内容，我会认真保护你；\n如果你心里很难受，我会好好听你说，也会鼓励你向信任的大人求助。' },
  { t: 'say', sp: 'sp_smile_ng_v3', text: '想聊天、画画、问问题，还是一起完成一件有意思的事，\n以后都可以来找我。' },
  { t: 'widget', kind: 'friendcard' },
  { t: 'say', sp: 'sp_excited_ng_v3', pop: true, text: '从今天开始，我们就是好朋友啦！🎉\n以后还有好多事情，等着我们一起去发现。' },
  {
    t: 'award', icon: '🐾', title: '第一次见面完成 · 我们成为好朋友啦',
    sub: '聊天陪伴 · 自动换模型 · 记住彼此 · 积累本领 · 一起成长',
    nextLabel: '去找超级小博玩 →',
  },
  { t: 'end' },
];
