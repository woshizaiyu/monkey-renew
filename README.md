## 🚀 Monkey-Network 自动续期（GitHub Actions）

定时登录 [dash.monkey-network.xyz](https://dash.monkey-network.xyz)，进入服务器 `Lifecycle` Tab，点击 `Confirm Server`，把 14 天计时器重置。基于 `eooce/Auto-Renew-Bothosting` 骨架改造（代理/TG/cron），登录块取自 Lunes 邮箱密码方案。

> ⚠️ 有 CF 盾，太垃圾的机房节点可能过不了，建议配一个干净点的节点（`NODE_LINK`）。

━━━━━━━━━━━━━━━━━━━━━━

### 🔐 Secrets 配置说明

| Secret 名称      | 是否必填 | 说明 |
|------------------|----------|------|
| MONKEY_EMAIL     | ✅ 必填  | Monkey 登录邮箱 |
| MONKEY_PASSWORD  | ✅ 必填  | Monkey 登录密码 |
| MONKEY_SERVER_ID | ❌ 可选  | 服务器短 id；单服可留空（自动点第一台），多服/定位不准时填写 |
| MONKEY_API_KEY   | ❌ 可选  | 面板 `Account Settings → API Credentials` 申请，仅用于状态查询，不能替代浏览器续期 |
| NODE_LINK        | ❌ 可选  | 代理链接（vless/vmess/trojan/hysteria2/tuic/anytls/socks5），不填则直连 |
| TG_BOT_TOKEN     | ❌ 可选  | Telegram Bot Token（用于发送通知） |
| TG_CHAT_ID       | ❌ 可选  | Telegram Chat ID（接收通知的用户或群组 ID） |

### 部署步骤

1. 新建**私库**，把本目录 `app.py`、`requirements.txt`、`.github/workflows/renew.yml` 推上去（不要用公库放密码），在 Actions 菜单允许工作流。
2. 在 `Settings → Secrets and variables → Actions` 里添加上方必填 Secrets。
3. 去 Actions 菜单手动试运行一次：
   - 收到 `✅ 续期成功` → 正常，之后每 3 天自动跑（`cron: 0 2 */3 * *`，按钮仅剩 ≤7 天可点，3 天一次留足重试窗）。
   - 收到 `⏳ 未到续期时间` → 正常，剩余天数会在通知里，等进 amber 区（≤7天）再自动点。
   - 收到 `ℹ️ 未找到确认按钮` → 把 Lifecycle 页面的按钮文字/截图发回来改选择器（附带的 `lifecycle_unknown.png` 在 Actions 日志/工件里找）。

### 续期规则（官网 lifecycle 页）

- 每台服务器 14 天周期；剩 ≤7 天按钮激活（amber），≤3 天变红，0 天删机。
- 确认免费，无需 token/积分，点一次重置 14 天。

### 注意事项

- 不要多账号薅羊毛，易封号。
- GA 的 cron 会延迟几十分钟，属于正常现象。
- 官方 Client API（`openapi.json` 实测）只有查服务器 3 个 GET 端点，**没有 confirm 端点**，所以 MVP 必须走浏览器模拟；`MONKEY_API_KEY` 只做查询增强。

### ⚠️ 免责声明

- 本程序仅供学习了解，非盈利目的。
- 遵守部署服务器所在地、所在国家和用户所在国家的法律法规，作者不对使用者任何不当行为负责。
