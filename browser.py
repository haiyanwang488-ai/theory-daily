"""浏览器渲染：抓纯前端 SPA 站点（上观新闻旗下的解放日报、文汇报）。

这两家所有路径都返回同一个 JS 空壳，requests 拿不到内容，必须执行 JS。
本地优先复用系统 Edge/Chrome，云端退回 Playwright 自带的 Chromium。

注意：Playwright 的 sync API 不能跨线程复用，所以浏览器源一律串行处理。
"""

from __future__ import annotations

import os
import time

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 依次尝试：系统 Edge → 系统 Chrome → Playwright 自带 Chromium
_CHANNELS: list[str | None] = ["msedge", "chrome", None]


class Browser:
    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self.channel_used: str | None = None

    def _ensure(self):
        if self._browser is not None:
            return self._browser
        self._pw = sync_playwright().start()
        last_err = None
        for ch in _CHANNELS:
            try:
                self._browser = (
                    self._pw.chromium.launch(channel=ch, args=["--no-sandbox"])
                    if ch
                    else self._pw.chromium.launch(args=["--no-sandbox"])
                )
                self.channel_used = ch or "chromium"
                return self._browser
            except Exception as e:  # 该 channel 不可用，换下一个
                last_err = e
        raise RuntimeError(f"无法启动任何浏览器：{last_err}")

    def render(
        self,
        url: str,
        wait_ms: int = 2200,
        timeout_ms: int = 35000,
        wait_until: str = "load",
    ) -> str | None:
        try:
            b = self._ensure()
            ctx = b.new_context(
                user_agent=UA,
                viewport={"width": 1366, "height": 900},
                locale="zh-CN",
            )
            page = ctx.new_page()
            try:
                # load 比 domcontentloaded 更可靠：等资源加载完，正文才渲染出来
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                page.wait_for_timeout(wait_ms)
                return page.content()
            finally:
                ctx.close()
        except Exception as e:
            print(f"  ! 渲染失败 {url[:70]}: {type(e).__name__}", flush=True)
            return None

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()
            self._browser = None
            self._pw = None


_singleton: Browser | None = None


def get() -> Browser:
    global _singleton
    if _singleton is None:
        _singleton = Browser()
    return _singleton


def render(url: str, wait_ms: int = 2200, tries: int = 3) -> str | None:
    """带重试的渲染：首次等 load 完成，失败后退到 domcontentloaded 再试。

    上观系的页面会挂一些慢广告资源，wait_until="load" 偶发超时；
    退到 domcontentloaded + 加长等待通常仍能拿到完整正文。
    空壳页面（SPA 未渲染）很短，用长度阈值一并挡掉。
    """
    for i in range(tries):
        html = get().render(
            url,
            wait_ms=wait_ms + (600 * i),
            wait_until="load" if i == 0 else "domcontentloaded",
        )
        if html and len(html) >= 3000:
            return html
        if i < tries - 1:
            time.sleep(1.2)
    return None


def close() -> None:
    global _singleton
    if _singleton is not None:
        _singleton.close()
        _singleton = None


def available() -> bool:
    """探测当前环境能否启动浏览器（云端没装 chromium 时返回 False）。"""
    try:
        get()._ensure()
        return True
    except Exception:
        return False
