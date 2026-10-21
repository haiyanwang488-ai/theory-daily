# 理论日课 · TheoryDaily

中文主流媒体理论文章的每日聚合阅读器。抓取 → 清洗去重 → 生成单文件网页。

**线上地址**：https://haiyanwang488-ai.github.io/theory-daily/
**仓库**：https://github.com/haiyanwang488-ai/theory-daily

每天 08:30（北京时间）由 GitHub Actions 自动抓取、生成网页、推送微信。电脑无需开机。

> 部署细节见 [DEPLOY.md](DEPLOY.md)。本地仍可手动运行 `更新.bat`。

## 怎么用

| 操作 | 做法 |
|---|---|
| 更新今天的文章 | 双击 `更新.bat`，跑完自动打开页面 |
| 只看不更新 | 直接打开 `site/index.html` |
| 首次建库 / 补历史 | 命令行跑 `python run_daily.py --backfill 30` |
| 测试微信推送 | `python push.py --dry-run`（只打印不发） |
| 立即推一次 | `python push.py` |

页面是单个 HTML 文件，不依赖网络和服务器，可以拷到任何地方打开。

## 微信推送

每天 **08:30** 把当日文章清单推到微信，走 Server酱。

**首次配置（只做一次）**

1. 微信扫码登录 https://sct.ftqq.com
2. 打开 SendKey 页面，复制你的 key（形如 `SCTxxxxxxxx`）
3. 填进 `config.json`：

```json
{
  "serverchan": { "sendkey": "SCTxxxxxxxx" },
  "push": { "max_items": 80, "skip_empty": true }
}
```

4. 验证：`python push.py --dry-run` 先看内容，再 `python push.py` 真发一条

**推送长什么样**：按学科主题分组，每条「标题 — 来源」，标题可点击直达原文。标题是 `理论日课 · 10月21日 · 53篇`。

**规则**
- 同一天只推一次，重复运行自动跳过；`--force` 可强制重推
- 当天没有新文章就不推，不浪费额度
- 免费版每天 5 条额度，一天一条绰绰有余
- 想改时间：任务计划程序里改 `TheoryDailyPush` 的触发器


## 覆盖的源

| 源 | 抓取位置 | 说明 |
|---|---|---|
| 求是网 | 首页 | 《求是》杂志与求是网理论文章 |
| 人民日报 · 理论版 | 电子版当日版面（自动定位含「理论」的版） | 纸质版全文 |
| 人民网 · 理论频道 | 首页 + 党建政治/经济社会/国际外交/文史哲教/学术动态 | 覆盖最广 |
| 光明网 · 理论频道 | 首页 | 含「理响中国」等专栏 |
| 学习时报 | 首页 | 中央党校主办 |
| 中国社会科学网 | 首页 | 社科院系统，学术动态最全 |

## 页面功能

- **主题分栏**：马克思主义 / 党史党建 / 政治经济学 / 哲学 / 法学 / 政治学 / 国际 / 历史 / 文化 / 新闻传播 / 社会 / 经济 / 科技教育 / 生态
- **搜索**：标题与摘要全文检索，按 `/` 聚焦
- **已读 / 收藏**：存在浏览器本地（localStorage），换浏览器不通用
- **复制引用**：按 GB/T 7714 格式生成 `题名[N/OL]. 来源, 日期. URL.`
- **去重**：同一篇文章被多个源收录时只留权重最高的（人民网转发人民日报理论版的情况很常见）
- **过滤**：会议消息、活动报道、视频专题自动标记并从阅读流中剔除

## 目录

```
theory-daily/
├── sources.py        源定义、主题规则、标题清洗、资讯过滤
├── fetch.py          列表解析 + 详情页补全 + 入库
├── normalize.py      就地重算（改规则后跑这个）
├── build.py          生成 site/index.html
├── push.py           微信推送（Server酱）
├── config.json       SendKey 与推送参数
├── run_daily.py      每日入口（抓取→清洗→生成）
├── 更新.bat          双击即更新
├── data/theory.db    SQLite，唯一数据源
├── templates/index.html  页面模板
└── site/index.html   生成结果
```

## 加一个新源

在 `sources.py` 的 `SOURCES` 里加一条。关键是 `href_re` 和 `date_from_href`：
只要文章 URL 里带日期，就能自动解析。例如：

```python
Source(
    key="xxx", name="某某报 · 理论版", short="某某报",
    homepage="https://example.com/",
    list_urls=["https://example.com/theory/"],
    href_re=r"/(\d{4})(\d{2})(\d{2})/t\d+\.html$",
    base="https://example.com/",
    date_from_href=r"/(\d{4})(\d{2})(\d{2})/t\d+\.html$",
    section="理论", weight=80,
)
```

加完跑 `python run_daily.py` 验证。改过主题规则或清洗规则后，跑 `python normalize.py` 就地重算，不用重抓。

## 说明

- 只存标题、摘要（正文前 320 字）和原文链接，不存全文，不绕过任何付费墙。阅读全文跳原文。
- 请求有 UA 标识、串行间隔和失败重试，日更一次的量对源站压力很小。
- 摘要取不到的文章会在卡片上标注，点原文阅读即可。
