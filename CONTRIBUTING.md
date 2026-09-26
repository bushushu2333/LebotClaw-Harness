# 贡献指南

Python 3.9+，macOS/Linux 为首轮开发验证环境。Windows 可用性和 Docker 实际运行需另外验证，不因为 CI 配置存在就声明通过。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,documents,browser,secure-keys]'
python -m playwright install chromium
python -m pytest -q
python -m build
```

新功能优先沿公开工具接口或模型适配边界实现。UI 不应有第二套 Agent 循环，不用预置文案假装模型或工具成功，不把示例任务变成固定场景分类。

测试应覆盖实际行为：生成文件内容、命令退出码、中断恢复、权限边界和协议完整性。当前自动化使用本机 HTTP 测试模型返回确定的工具请求，真正执行文件/程序操作；这不能替代真实 DeepSeek/GLM 任务质量评测。测试不得调用真实付费 API、读取本机密钥或修改个人目录。

插件处理耗时工作时用异步可取消 handler。同步 handler 仅做有限快速工作。加载插件等同信任本机 Python 代码；不要把 plugin effect 说成能限制恶意插件的安全边界。

不提交模型凭据、用户会话、个人材料和构建缓存。版本发布前检查 README、SECURITY、架构和实际能力一致。除 MIT 协议和贡献说明外，公开发布还应由仓库所有者确认名称、维护渠道、商标/素材授权与发布范围。
