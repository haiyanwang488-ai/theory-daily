# 部署到 GitHub Actions（脱离本机运行）

> **当前状态：已部署完成并验证通过（2026-10-21）**
>
> - 仓库：https://github.com/haiyanwang488-ai/theory-daily
> - 网页：https://haiyanwang488-ai.github.io/theory-daily/
> - Secret `SERVERCHAN_SENDKEY` 已配置，Pages 已开启（workflow 模式）
> - 首次运行 daily + deploy 均 success，本机定时任务已移除
>
> 下面的流程保留作为参考，重装或迁移到新仓库时照做即可。

部署完成后：每天 08:30 由 GitHub 的服务器自动抓取、生成网页、推送到微信。你的电脑关机也照常运行。

---

## 0. 先决条件

- 一个 GitHub 账号（没有就注册，免费）
- **仓库必须是 Public**。GitHub 免费账户不支持私有仓库的 Pages 功能；而且本项目代码里不含任何密钥（SendKey 存在 Secrets 里），公开没有风险。

> 如果坚持私有仓库，就只能推送微信、不能托管网页；或者升级 GitHub Pro（$4/月）。

---

## 1. 在 GitHub 建一个空仓库

1. 打开 https://github.com/new
2. Repository name 填 `theory-daily`
3. 选 **Public**
4. **不要**勾选 "Add a README file"（保持空仓库）
5. 点 Create repository

---

## 2. 把本地代码推上去

打开终端（或 Git Bash），逐条执行。把 `<你的用户名>` 换成你的 GitHub 用户名：

```bash
cd "D:/微软下载/2026-10-21-17-29-57/theory-daily"
git remote add origin https://github.com/<你的用户名>/theory-daily.git
git push -u origin main
```

第一次推送会弹出 GitHub 登录窗口（浏览器授权），登录即可。仓库已初始化好，不需要再 `git init`。

推完后刷新仓库页面，应该能看到 `sources.py`、`.github/workflows/daily.yml` 等文件。

> 注意：`config.json` 和 `site/` 已被 `.gitignore` 排除，不会上传——前者含密钥，后者是生成物。

---

## 3. 配置 SendKey（关键）

1. 仓库页 → **Settings** → 左侧 **Secrets and variables** → **Actions**
2. 点 **New repository secret**
3. Name 填：`SERVERCHAN_SENDKEY`
4. Secret 填：你的 SendKey（`SCT` 开头那串）
5. 点 Add secret

代码会优先读这个环境变量，本地 `config.json` 只在没设环境变量时生效。

---

## 4. 开启 GitHub Pages

1. 仓库页 → **Settings** → 左侧 **Pages**
2. **Source** 选 **GitHub Actions**（不要选 "Deploy from a branch"）
3. 不用点保存，选完即生效

---

## 5. 手动跑一次验证

1. 仓库页 → **Actions** 标签
2. 左侧选「理论日课 每日更新」
3. 右侧 **Run workflow** → **Run workflow**
4. 等 1-2 分钟，点进去看日志

**期望看到**：
- `抓取开始` 后各源显示「列表 N 条，新增 M 条」
- `已生成 site/index.html`
- `推送成功：理论日课 · X月X日 · N篇`
- 微信收到消息
- 最后 deploy 步骤显示绿色，给出 `https://<用户名>.github.io/theory-daily/`

**如果抓取失败**：说明海外机器访问某些国内站点受限。点开日志看哪个源报错，告诉我就行，我可以换成国内可达的镜像入口或调整超时。

---

## 6. 停掉本机任务（重要）

云端跑起来后，本机的定时任务必须停掉，否则两边都在推送（虽然各自有去重，但数据会分叉）：

```powershell
Unregister-ScheduledTask -TaskName "TheoryDaily","TheoryDailyPush" -Confirm:$false
```

`更新.bat` 可以留着，偶尔想在本地手动更新时用。

---

## 日常维护

| 事项 | 做法 |
|---|---|
| 看今天的推送 | 微信，或打开 `https://<用户名>.github.io/theory-daily/` |
| 立刻手动跑一次 | Actions → Run workflow |
| 改推送时间 | 改 `.github/workflows/daily.yml` 的 cron。注意是 **UTC**，北京时间减 8 小时 |
| 改推送内容 | 改 `push.py` 的 `render()`，推上去即生效 |
| 加新源 | 改 `sources.py`，推上去 |
| 改主题规则 | 改 `sources.py` 的 `TOPIC_RULES`，推上去（下次运行自动重算全库） |
| 换 SendKey | Settings → Secrets 里更新 |

---

## 已知限制

1. **cron 不精确**。GitHub 的定时任务在高负载时会延迟，通常几分钟，偶尔半小时。设的是 08:30，实际可能 08:35-09:00 到。
2. **60 天无提交会自动停用 schedule**。本项目每天提交数据库，天然保持活跃，不会触发。
3. **免费额度**：Public 仓库的 Actions 不限时长；每次运行约 1-2 分钟。
4. **数据库每天提交一次**，一年后仓库约几十 MB。如果嫌大，可以定期删历史提交，或者告诉我改成 JSONL 增量存储。
5. **GitHub Pages 在国内访问可能慢**，但微信推送里的原文链接都是直连媒体站点，不受影响。

---

## 备注：用 API 自动化部署时踩过的坑

如果不想在网页上点，用 API 全自动配置，注意这几点：

- **创建 Pages 必须用 `POST /repos/{owner}/{repo}/pages`**，body `{"build_type": "workflow"}`。用 `PUT` 在 Pages 尚未创建时返回 404（PUT 只能更新已存在的）。
- **设置 Secret 需要先取公钥再加密**：`GET .../actions/secrets/public-key` 拿 `key` 和 `key_id`，用 libsodium sealed box 加密值，再 `PUT .../actions/secrets/{name}`。
- **git push 在非交互环境会失败**：`GIT_TERMINAL_PROMPT=0` 会导致 `could not read Username`。需要显式 `GIT_TERMINAL_PROMPT=1` 让凭据管理器弹窗授权。
