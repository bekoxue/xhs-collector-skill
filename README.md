# 小红书采集助手 Skill

适用于 Claude Code、OpenClaw 等支持 Agent Skills 的智能体，可通过自然语言采集小红书公开数据。

## 一键安装

Claude Code：

```bash
npx skills add bekoxue/xhs-collector-skill --skill xhs-collector -g -a claude-code -y
```

OpenClaw：

```bash
npx skills add bekoxue/xhs-collector-skill --skill xhs-collector -g -a openclaw -y
```

安装完成后，按 [INSTALL.md](INSTALL.md) 生成并安全配置 API 令牌。完整令牌仅显示一次，建议由用户本人在本机终端粘贴，不要发送到聊天中。

图文版完整指南：https://my.feishu.cn/docx/Xv6RdejA2o4lWixGnsdcWv8Wnsb

## 运行要求

- Python 3.9+，无需安装第三方 Python 依赖
- 宿主机执行，不支持 Docker、容器或云沙箱
- 一个令牌仅绑定一台设备

