# 小红书采集 Skill 安装说明

> 📖 图文版完整使用指南：https://my.feishu.cn/docx/Xv6RdejA2o4lWixGnsdcWv8Wnsb

## 推荐：GitHub 一键安装

Claude Code：

```bash
npx skills add bekoxue/xhs-collector-skill --skill xhs-collector -g -a claude-code -y
```

OpenClaw：

```bash
npx skills add bekoxue/xhs-collector-skill --skill xhs-collector -g -a openclaw -y
```

安装器需要 Node.js / npx。如当前电脑未安装 Node.js，可从上方飞书指南下载 ZIP，再按下文手动放入对应的 Skill 目录。

## 准备：生成令牌（仅一次）

1. 登录 https://xhs.baojianlab.com/ （没有账号先注册，并绑定购买的激活码）
2. 进入「我的账户 → 智能体接入（API 令牌）」，点「生成令牌」
3. 复制令牌（**仅显示一次**，关闭弹窗后无法再查看）

## Claude Code 安装

1. 如未使用 GitHub 一键安装，把 `xhs-collector` 文件夹整个解压到 `~/.claude/skills/`
2. 在终端运行（粘贴令牌，输入不回显）：

```bash
python3 ~/.claude/skills/xhs-collector/scripts/xhs.py configure
```

3. 重启 Claude Code 会话，直接说「帮我采集小红书 xxx」即可。

## OpenClaw 安装

1. 如未使用 GitHub 一键安装，把 `xhs-collector` 文件夹解压到 `~/.openclaw/skills/`（或工作区的 `skills/` 目录）
2. 在 `~/.openclaw/openclaw.json` 中注入令牌：

```json
{
  "skills": {
    "entries": {
      "xhs-collector": {
        "enabled": true,
        "env": { "COLLECTOR_API_KEY": "粘贴你的令牌" }
      }
    }
  }
}
```

3. 重启 OpenClaw 后即可使用。**请勿在 sandbox 模式下运行本 skill**（宿主机执行）。

## 常见问题

- **令牌提示已绑定其他设备**：令牌首次使用后绑定当时的电脑。换电脑时到网页端「我的账户 → 智能体接入」点「解绑设备」，或重新生成令牌。
- **提示令牌无效**：修改平台密码、或在网页端重新生成过令牌，都会让旧令牌失效——重新生成并 configure 即可。
- **余额不足**：添加客服微信 baojian_xue 充值；采集中断的任务充值后可从断点续采，不会重复扣费。
- 系统要求：macOS / Linux / Windows，Python 3.9+（无需安装任何第三方包）。
