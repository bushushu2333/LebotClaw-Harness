# LebotClaw 橙光风功能介绍站 · 说明

- **内容**：橙光游戏（视觉小说）式 LebotClaw 第一次见面引导。四段流程：认识超级小博并填写名字 → 了解通用陪伴能力与自动选模型 → 了解记忆、技能和成长 → 成为好朋友并回主站创建头像。
- **版本**：v3.2（名字输入不再自动带出测试账号或历史名字；模型路由演示改为豆包 Seedream 4.0、Kimi K2.6、DeepSeek V4 Pro、GLM 5.2 等具体模型；保留无护目镜小博立绘和炀炀2.0 配音）
- **日期**：2026-08-17
- **来源**：剧情引擎复用 LebotSchool课程平台「AI训练师成长纪·序章」（story.js/story.css，交接文档-橙光剧情模式-v1.0-20260721）；立绘以小博品牌形象/小博_锚_定稿.png 为参考图经 EvoLink gemini-3-pro-image-preview 生成；配音用豆包 TTS 双向流式（炀炀2.0 = ICL_uranus_zh_male_yangyang_tob，音色出处 LebotClaw 仓库 src/lebotclaw/web/tts_doubao.py）
- **用途**：LebotClaw 产品对外介绍/新用户欢迎页，可挂 lebotworld.com/lebotclaw/ 下作为 /intro 入口
- **状态**：v3.2 本地版；空白名字输入、具体模型路由演示和无护目镜小博立绘已接入。

## 目录结构

- `index.html` — 入口页（封面/HUD/对话框/目录/结算）
- `assets/story/story.js` — 剧情引擎（存档/回看/打字机；配音优先播 voice/<djb2>.mp3；WIDGETS = meet / model_switch / growth / friendcard）
- `assets/story/story.css` — 样式（末尾追加 LebotClaw 定制组件样式）
- `assets/story/script-intro.js` — 剧情脚本（改文案只动这个文件，改完 index.html 里 ?v= +1，并重跑 gen_voice.py 补配音）
- `assets/story/voice/` — 炀炀2.0 配音 mp3，按脚本文本 djb2 哈希命名
- `assets/story/bg_*_v3.png` — v3 四张 EvoLink 新背景；`sp_*_ng_v3.png` — 七张无护目镜小博透明立绘
- `raw_生图原图/` — EvoLink 原始 2K 大图（留底，网页未直接用）
- `tools/gen_images.mjs` — 批量生图脚本（`node gen_images.mjs [名字]`，已存在自动跳过；内含锚点图 URL，过期需重传）
- `tools/matte_sprites.py` — 立绘抠图（自适应四角背景色洪泛填充→透明 PNG+裁剪，黑底白底通吃）
- `tools/gen_voice.py` — 批量配音脚本（node 导出脚本文本→豆包炀炀2.0逐条合成→voice/<hash>.mp3，已存在自动跳过；API key 从环境变量 `DOUBAO_TTS_API_KEY` 或本地 `tools/.api_key`（已 gitignore）读取，不入库）
- `tools/_tts_ws/` — 火山官方 WebSocket 协议库（gen_voice.py 依赖）

## 本地预览

```bash
python3 -m http.server 8931 --directory "本目录"
# 打开 http://127.0.0.1:8931/
```

调试跳转：`index.html#debug=t01`（start / t01 / t02 / t03）
