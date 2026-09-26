# LebotClaw Harness

**超级小博的开源本地智能体运行环境。** 接上自己的模型，通过浏览器描述目标，让它在获得授权后读取材料、写代码、生成图片、制作网页和可编辑文档，并检查实际结果。MIT 许可。

**v0.2.1 · 开发预览**。程序与项目运行在本机，界面由本地服务提供。无需 LebotWorld 账号；在线模型仍会接收你选择提供的对话、材料和工具结果。

## 启动

需要 Python 3.9+；建议 Python 3.12。macOS/Linux 执行：

```sh
git clone https://github.com/bushushu2333/LebotClaw-Harness.git
cd LebotClaw-Harness
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[documents,browser,secure-keys]'
python -m playwright install chromium
lebotclaw web --open
```

浏览器打开 `http://127.0.0.1:18866/`。Windows 可用 PowerShell 激活 `.venv\Scripts\Activate.ps1` 后执行相同安装命令。Windows 命令执行请选择 Docker；本机命令的完整进程树停止当前只在 macOS/Linux 验证。

1. 首次进入先连接**文字与编程模型**，填入模型 ID、官方或中转站地址和 Key，点击「保存并测试连接」。对话、工具调用通过后进入下一步。
2. **选择项目**：创建独立本地文件夹，或浏览选择已有目录。图片生成推荐配置，语音可选，均可之后在设置中添加。
3. 在 **Plan** 中描述想法、讨论方案。准备制作时点「授权并继续」，确认本项目的读写、生图等范围。
4. 点击「授权并开始制作」，自动接着刚才的需求执行。过程中的回复逐步显示，需要批准的操作会出现卡片；错误直接显示原因和重试入口。
5. 生成成果后出现项目文件与预览，可运行网页、查看图片、下载文档或**下载包含资源的整个项目 ZIP**。也可在本机文件管理器中打开目录。

`--home` 放在子命令前，例如 `lebotclaw --home ./my-state web --port 18868`。同一数据目录只能运行一个进程；不要让两个数据目录的运行器同时编辑同一项目。

## 模型与可选服务

| 能力 | 已实现协议 |
| --- | --- |
| 文字、推理、工具调用 | OpenAI Chat Completions / SSE，保留工具 ID 和 `reasoning_content` |
| 试卷照片等图片输入 | 文字模型具备视觉能力时，用户可在界面声明并添加图片附件 |
| 生图 | OpenAI Images 的 `data[].b64_json` / `url`；另支持万相 DashScope SSE（智云协议） |
| ASR | `audio/transcriptions`，multipart 音频上传 |
| TTS | `audio/speech`，MP3 返回 |

DeepSeek、GLM 内置基础地址；Kimi、Qwen、其他厂商与中转站通过自定义兼容地址接入。**兼容协议是具体前提**，不代表任意厂商的专有协议都无需适配。模型 ID 以你账户实际可用的型号为准。

生图设置中可选协议、尺寸、质量和返回格式。万相一次请求可能产出多张，按上游实际张数计费；Harness 会保存返回的图片。生图预算限制请求次数，不等于图片张数或人民币金额。异步任务查询类生图协议尚需适配器。

Key 可仅放当前进程内存、来自配置声明的环境变量，或由用户勾选后存入系统凭据库。安全库不可用时明确报错，不写明文 Key 文件。凭据绑定配置名称、服务商与接口地址，改地址不会把旧 Key 发给新地址。

**LebotAPI 是可选途径。** 用户可在 LebotAPI 创建个人 Key、设定可用乐豆额度后接入；国内主流模型按官方价 **95 折**，使用乐豆结算。当前仓库提供客户端模型接入，不包含充值账本或已验证的余额接口，金额与额度由 LebotAPI 服务端负责。自带其他服务 Key 不走乐豆。

## 授权

| 模式 | 行为 |
| --- | --- |
| Plan（默认） | 只讨论，或读取用户另外授权的项目材料；拒绝文件制作、命令、生图 |
| 逐次批准 | 对修改文件、执行命令、制作素材显示完整参数，批准后才执行 |
| 自动执行 | 常规文件制作和已授权 Docker 命令自动执行；生图与本机命令仍逐项批准 |
| 不需要批准 | 范围内连续执行，仍受任务预算限制 |

授权范围分别控制读取、写入、命令、图片和命令网络；可以仅本次任务生效或记住此项目。临时执行授权结束后回到 Plan，已授权的项目读取在本次服务中保留。重启不保留临时授权。授权不能由模型或文档修改。

撤销会停止当前运行、使待批准卡片失效、禁止新的项目读取和执行；已有文件保留。不同会话指向同一目录时共享项目授权，并且只允许一个运行中的任务。

**执行环境与批准模式不同。** Docker 挂载当前项目，默认禁网、只读根目录、非特权并限制资源；需要操作者安装 Docker、启动 daemon 并预备镜像。可通过 `lebotclaw execution docker --image YOUR_IMAGE` 配置镜像。安装依赖通常需要用户授予网络；系统目录仍只读，可将依赖装进项目。

本机命令使用当前操作系统用户权限，不能保证只访问项目目录；只有独立确认后才能启用。文件工具的路径校验不等于命令沙箱。推荐普通用户使用 Docker 或仅开启文件制作与浏览器验证。

## 能做的工作

- 读写与搜索本地项目，按 SHA-256 检查冲突，精确文本补丁；旧文件版本保留原始字节与路径记录。
- 通用“模型 → 工具 → 真实结果 → 修复 → 继续”循环，不靠固定场景模板生成作品。
- 多文件 HTML/JS/CSS/图片作品预览；每个项目独立本地来源，与模型设置和其他项目隔离。预览端口记录在本机，重启复用以保留 localStorage。
- 用 Chromium 点击、填写、检查页面文字与脚本错误，并保存截图。浏览器测试禁外网；这不等于对任意游戏逻辑的完整测试。
- 生图 API 返回的图片落到项目，供网页、游戏和 PPT 引用。
- 用模型给出的章节与内容制作可编辑 PPTX、DOCX，可插入项目图片；提取 PDF 文本层、DOCX/PPTX 文本。
- 可选录音转文字，用户检查后发送；点击回复可调用已配置的 TTS 播报。
- 会话、消息、事件、操作意图与结果落 SQLite；取消、中断恢复及 token/时间/调用次数预算。
- 显式信任的 Python 工具扩展。

PPTX 文件可编辑不代表排版经过视觉验证。扫描件没有文本层时需视觉/OCR，当前没有通用 OCR 工具。常驻系统闹钟、后台开发服务器、任意网页浏览、MCP、长上下文压缩尚未完成。不同提供商切换需新建会话，可复用已有项目目录。

## CLI

```sh
lebotclaw models add deepseek --provider deepseek --model YOUR_MODEL_ID --key-env DEEPSEEK_API_KEY
lebotclaw models test
# 先规划，不开放项目读写
lebotclaw run "规划一个课程表" --workspace ./course-project
# 显式授权本次项目制作；不运行系统命令
lebotclaw run "制作课程表并验证网页" --workspace ./course-project --mode full --allow-write
# 每个制作操作交互批准；非交互 CLI 会拒绝待批准操作
lebotclaw run "修改课程表" --workspace ./course-project --mode ask --allow-write
lebotclaw resume SESSION_ID "继续改进" --mode full --allow-write
lebotclaw tools list
```

图片服务在浏览器设置中单独绑定；CLI 加 `--allow-images` 仍需已有生图服务配置。命令授权需 `--allow-commands --execution-mode docker`；开启网络再加 `--allow-network`。本机执行需额外的 `--acknowledge-unrestricted-host-access`。

## 开发与验证

```sh
python -m pip install -e '.[dev,documents,browser,secure-keys]'
python -m playwright install chromium
python -m pytest -q
python -m build
lebotclaw plugins add ./examples/plugins/csv_summary.py --trust-code
```

`Tool(name, description, parameters, handler, effect)` 是工具扩展接口。插件是在宿主 Python 中执行的受信任代码，不是沙箱技能市场。运行目录、用户 Key、验收作品不打入 wheel。

参见 [本次交互整改与真实验收](docs/ux-repair-v0.2.1.md)、[架构](docs/architecture.md)、[v0.2 验证](docs/validation-v0.2.md)、[待办](docs/roadmap.md)、[安全说明](SECURITY.md)。本项目参考 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的产品形态，当前为独立 Python 实现，没有声称已与 DSH/Claude Code 能力等价。
