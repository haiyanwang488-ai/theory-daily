"""源定义与列表页解析规则。

每个源声明：名称、列表页、链接识别正则、URL 归一化方式、日期提取方式。
链接识别统一用「href 正则 + 从 href 中提取日期」，因为六个站点的文章 URL 都带日期。
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Source:
    key: str
    name: str
    short: str
    homepage: str
    list_urls: list[str]
    href_re: str                    # 用于匹配文章链接的正则（对 href 属性值匹配）
    base: str                       # 相对链接的 base
    date_from_href: str             # 从 href 提取 YYYY-MM-DD 的正则（需 3 个组：年 月 日）
    section: str = ""
    note: str = ""
    dynamic: Optional[str] = None   # 需要先解析版面导航的源（人民日报电子版）
    weight: int = 50                # 排序权重，理论属性越强越高
    needs_browser: bool = False     # 纯前端 SPA，必须用浏览器渲染

    def match_href(self, href: str) -> Optional[re.Match]:
        return re.search(self.href_re, href)


def _d(y, m, d) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def parse_date(src: Source, href: str) -> Optional[str]:
    m = re.search(src.date_from_href, href)
    if not m:
        return None
    return _d(*m.groups()[:3])


SOURCES: list[Source] = [
    Source(
        key="people_theory",
        name="人民网 · 理论频道",
        short="人民网理论",
        homepage="http://theory.people.com.cn/",
        list_urls=[
            "http://theory.people.com.cn/",
            "http://theory.people.com.cn/GB/49150/index.html",   # 党建政治
            "http://theory.people.com.cn/GB/49154/index.html",   # 经济社会
            "http://theory.people.com.cn/GB/136457/index.html",  # 国际外交
            "http://theory.people.com.cn/GB/49157/index.html",   # 文史哲教
            "http://theory.people.com.cn/GB/40534/index.html",   # 学术动态
        ],
        href_re=r"/n1/(\d{4})/(\d{2})(\d{2})/c\d+-\d+\.html$",
        base="http://theory.people.com.cn",
        date_from_href=r"/n1/(\d{4})/(\d{2})(\d{2})/",
        section="理论",
        note="人民日报理论版文章的网上发布口，含「深入学习贯彻」系列",
        weight=95,
    ),
    Source(
        key="qstheory",
        name="求是网",
        short="求是",
        homepage="https://www.qstheory.cn/",
        list_urls=["https://www.qstheory.cn/"],
        href_re=r"/(\d{8})/[0-9a-f]{32}/c\.html$",
        base="https://www.qstheory.cn",
        date_from_href=r"/(\d{4})(\d{2})(\d{2})/[0-9a-f]{32}/c\.html$",
        section="求是",
        note="《求是》杂志及求是网理论文章，中央党刊口径",
        weight=98,
    ),
    Source(
        key="gmw_theory",
        name="光明网 · 理论频道",
        short="光明网理论",
        homepage="https://theory.gmw.cn/",
        list_urls=["https://theory.gmw.cn/"],
        href_re=r"(\d{4}-\d{2})/(\d{2})/content_\d+\.htm$",
        base="https://theory.gmw.cn/",
        date_from_href=r"(\d{4})-(\d{2})/(\d{2})/content_\d+\.htm$",
        section="理论",
        note="《光明日报》理论版配套频道，含「理响中国」等专栏",
        weight=90,
    ),
    Source(
        key="studytimes",
        name="学习时报",
        short="学习时报",
        homepage="http://www.studytimes.cn/",
        list_urls=["http://www.studytimes.cn/"],
        href_re=r"/([a-z_]+/\d{6}/t(\d{4})(\d{2})(\d{2})_\d+\.html)$",
        base="http://www.studytimes.cn/",
        date_from_href=r"t(\d{4})(\d{2})(\d{2})_\d+\.html$",
        section="学习时报",
        note="中央党校主办，干部理论教育主阵地",
        weight=88,
    ),
    Source(
        key="cssn",
        name="中国社会科学网",
        short="中国社科网",
        homepage="https://www.cssn.cn/",
        list_urls=["https://www.cssn.cn/"],
        href_re=r"/([a-z_]+/\d{6}/t(\d{4})(\d{2})(\d{2})_\d+\.shtml)$",
        base="https://www.cssn.cn/",
        date_from_href=r"t(\d{4})(\d{2})(\d{2})_\d+\.shtml$",
        section="综合",
        note="中国社科院主办，学术理论动态最全",
        weight=85,
    ),
    Source(
        key="rmrb_paper",
        name="人民日报 · 理论版",
        short="人民日报理论版",
        homepage="http://paper.people.com.cn/rmrb/",
        list_urls=[],  # 由 dynamic 逻辑填充
        href_re=r"/content/(\d{6})/(\d{2})/content_\d+\.html$",
        base="http://paper.people.com.cn",
        date_from_href=r"/content/(\d{4})(\d{2})/(\d{2})/content_\d+\.html$",
        section="理论版",
        note="当日纸质版理论版全文，版面号按日期自动定位",
        weight=96,
        dynamic="rmrb",
    ),
    Source(
        key="ce_paper",
        name="经济日报 · 理论版",
        short="经济日报理论版",
        homepage="http://paper.ce.cn/",
        list_urls=[],  # 由 dynamic 逻辑填充
        href_re=r"/content/(\d{6})/(\d{2})/content_\d+\.html$",
        base="http://paper.ce.cn",
        date_from_href=r"/content/(\d{4})(\d{2})/(\d{2})/content_\d+\.html$",
        section="理论版",
        note="当日纸质版理论版全文，中央三报之一",
        weight=94,
        dynamic="ce",
    ),
    # ---- 上观新闻旗下（纯前端 SPA，必须浏览器渲染；日期靠列表页相对时间换算）----
    Source(
        key="jfdaily",
        name="解放日报 · 思想",
        short="解放日报",
        homepage="https://www.jfdaily.com/",
        list_urls=[
            "https://www.jfdaily.com/staticsg/res/html/web/section.html?id=62&v=2.2",       # 思想
            "https://www.jfdaily.com/staticsg/res/html/web/subsection.html?id=57&v=2.2",    # 思想汇（理论主阵地）
            "https://www.jfdaily.com/staticsg/res/html/web/subsection.html?id=135&v=2.2",   # 观点评论
        ],
        href_re=r"newsDetail\.html\?id=(\d+)",
        base="https://www.jfdaily.com/staticsg/res/html/web/",
        date_from_href="",  # 列表页只有相对时间，由 parse_observed 处理
        section="思想",
        note="上海市委机关报，思想周刊、思想汇与观点评论",
        weight=82,
        needs_browser=True,
    ),
    Source(
        key="whb",
        name="文汇报 · 学人",
        short="文汇报",
        homepage="https://www.whb.cn/",
        list_urls=[
            "https://www.jfdaily.com/staticsg/res/html/web/subsection.html?id=353&v=2.2",   # 文汇学人
            "https://www.jfdaily.com/staticsg/res/html/web/subsection.html?id=349&v=2.2",   # 文汇文艺评论
        ],
        href_re=r"newsDetail\.html\?id=(\d+)",
        base="https://www.jfdaily.com/staticsg/res/html/web/",
        date_from_href="",
        section="学人",
        note="文汇学人、文汇文艺评论，偏人文社科学术",
        weight=80,
        needs_browser=True,
    ),
]


BY_KEY = {s.key: s for s in SOURCES}


# 主题归类：规则命中即归入，按顺序取第一个命中；用于页面上的主题分栏。
# 顺序即优先级——越靠前越"理论"，避免泛词把文章吸走。
TOPIC_RULES: list[tuple[str, str]] = [
    ("马克思主义", r"马克思|恩格斯|资本论|唯物史观|辩证法|剩余价值|科学社会主义|《资本论》|历史唯物主义|《共产党宣言》"),
    ("党史党建", r"党史|党建|党的领导|从严治党|自我革命|长征|红军|延安|井冈山|西柏坡|照金|伟大建党精神|革命传统|作风建设|党风廉政|组织建设|管党治党|政治忠诚|执政基础"),
    ("政治经济学", r"政治经济学|生产力|生产关系|基本经济制度|新发展格局|高质量发展|新质生产力|公有制|按劳分配"),
    ("哲学", r"哲学|认识论|本体论|现象学|伦理学|美学|逻辑学|价值论|实践唯物主义|辩证法|思维方式|格物|知行|心性|和合|天人|体用|工夫"),
    ("法学", r"法治|法律|宪法|司法|立法|法理|依法治国|民法典|权利保障|合法性|犯罪|检察|审判"),
    ("国际", r"国际|全球|外交|地缘|中美|中欧|一带一路|人类命运共同体|全球治理|世界秩序|安全格局|大国|周边|会谈|总统|联合国"),
    ("历史", r"史学|近代史|古代史|世界史|历史研究|历史叙事|抗战史|中华人民共和国史|文明史|编年史|史料|考古|方志"),
    ("文化", r"文化|文明|文艺|意识形态|文化自信|精神谱系|传统文化|文学|艺术|文旅|非遗"),
    ("新闻传播", r"传播|媒体|舆论|短视频|报业|新闻|出版|网络内容"),
    ("政治学", r"权力|监督|民主|人大|政协|干部|国家治理|政治建设|政治发展|政治文明|制度优势|治理体系|反腐败"),
    ("军事国防", r"强军|军队|国防|军事|官兵|国家安全|大安全|战争|战略支援"),
    ("社会", r"社会治理|基层|民生|人口|乡村|社会保障|共同富裕|城镇化|社区|托育|健康中国|就业|民族团结"),
    ("经济", r"经济|金融|市场|产业|财政|货币|数字经济|消费|投资|贸易|企业"),
    ("科技教育", r"科技|创新|教育|人才|人工智能|自立自强|基础研究|学科建设|高校|科研|青少年|育人|课程|教师"),
    ("生态", r"生态|绿色|双碳|环境|人与自然|美丽中国|增绿|低碳"),
]

TOPIC_RE = [(t, re.compile(p)) for t, p in TOPIC_RULES]

# 站点名后缀：从详情页 <title> 里剥掉「--理论-中国共产党新闻网」这类尾巴
_SITE = (
    r"(?:中国共产党新闻网|人民网|光明网|求是网|中国社会科学网|中国社科网|"
    r"学习时报|人民日报|新华网|央视网|中国日报网|澎湃新闻|光明日报|经济日报)"
)
_SECTION_WORD = r"(?:理论|观点|评论|思想|学术|文化|政治|国际|经济|社会|文史|哲学|法学|党建|党史)"
SITE_SUFFIX_RE = re.compile(
    rf"[\s\-—_|~、·]*{_SECTION_WORD}?[\s\-—_|~、·]*{_SITE}[\s\-—_|~、·]*(?:网)?[\s\-—_|~、·]*$"
)
TAIL_JUNK_RE = re.compile(r"[\s\-—_|~、·]+$")

# 会议消息 / 活动报道：不是理论文章，入库时标记，前端默认折叠
NEWS_BODY_RE = re.compile(r"^(?:本报讯|中国社会科学报[^。]{0,15}讯|新华社[^。]{0,10}电|本报[^。]{0,10}讯|据新华社)")
NEWS_TITLE_RE = re.compile(
    r"(召开|举行|开幕|闭幕|启动|揭牌|签约|座谈会在|调研|会见|来访|颁奖|启动仪式|论坛在|"
    r"致信|贺信|祝贺|出席|发表重要讲话|联合宣讲|全网推送|新闻联播|公布.*名单|将部署|宣布|签署|"
    r"一周票房|票房榜|收视率|排行榜)"
)
# 理论文章不会只有几百字：短于这个长度的基本是快讯、图文稿、公告、视频文字稿
THIN_CHARS = 350
# 视频 / 专题片 / 图集：不是可读的理论文章
VIDEO_RE = re.compile(r"(求是视频|第\d+集|专题片|微视频|短视频|图集|直播回放|H5|【海报】)")
# 期刊期号页、评奖公告、目录页：不是单篇文章
NON_ARTICLE_RE = re.compile(r"^(\d{4}\s*年\s*第\s*\d+\s*期|第\s*\d+\s*期)$|(评奖结果|获奖名单|结果公布|目录页)")


def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title or "").strip()
    prev = None
    while prev != t:  # 可能有多层后缀
        prev = t
        t = SITE_SUFFIX_RE.sub("", t)
        t = TAIL_JUNK_RE.sub("", t)
    return t.strip()


def is_news(title: str, summary: str = "", chars: int = 0) -> bool:
    """非理论文章：会议消息、活动报道、快讯、公告、视频文字稿。

    chars 为 0 表示正文没抓到，不能据此判断，只靠标题与导语规则。
    """
    if 0 < chars < THIN_CHARS:
        return True
    return bool(NEWS_BODY_RE.search(summary or "") or NEWS_TITLE_RE.search(title or ""))


def is_video(title: str, url: str = "") -> bool:
    """非单篇文章：视频、专题片、图集、期刊期号页、评奖公告。"""
    t = title or ""
    return bool(VIDEO_RE.search(t) or NON_ARTICLE_RE.search(t) or "/video/" in (url or ""))


def classify(title: str, summary: str = "") -> str:
    """先只看标题，标题全不命中再退到摘要。

    摘要里的泛词（高质量发展、治理、文明）会把文章吸到不相干的学科，
    标题优先能显著减少这种误判。
    """
    t = title or ""
    for topic, rx in TOPIC_RE:
        if rx.search(t):
            return topic
    s = (summary or "")[:150]
    if s:
        for topic, rx in TOPIC_RE:
            if rx.search(s):
                return topic
    return "其他"
