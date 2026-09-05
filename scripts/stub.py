#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stub.py — 识别「跳转壳页面」（只有跳转逻辑、没有正文的页面）。

为什么需要这个模块
------------------
游民星空有一部分 /news/YYYYMM/NNNNNNN.shtml 根本不是文章，而是跳往玩家
社区活动页的空壳。整页只有 1.5KB，长这样：

    <div id="redirectTips" data-itemid="2203715"
         data-link='https://club.gamersky.com/activity/1596845?club=163'></div>
    <script> ... window.location.href = $this.attr("data-link") ... </script>

正文全靠 JS 跳转，服务端渲染的 HTML 里一个字都没有。

后果（2026-09-05 线上事故）
--------------------------
这类链接会被当新闻一路走到发布：
  1. 列表页抓标题时，因该站 title 属性不转义内嵌双引号，正则匹配失败，
     静默借用了**相邻条目**的标题《GTA6》或将提前登陆PC；
     （该错配的根因修复见 fetch_news.link_meta）
  2. enrich 抓正文，只拿到 1.5KB 的壳页，content_html 为空；
  3. 策展模型只看到标题，凭空补了一段「因主机缺货，GTA6 可能提前登陆PC」
     的摘要——站内出现一条图文并茂、点进去却是社区活动页的鬼故事。

所以 fetch_news（候选阶段）和 enrich（正文阶段）都要过这一层。
"""

import re


# 空壳的跳转痕迹
_STUB_MARKERS = (
    re.compile(r"""id=["']redirectTips["']""", re.I),
    re.compile(r"""<meta[^>]+http-equiv=["']refresh["'][^>]+url=""", re.I),
)

# 正文（剥掉 script/style 之后）少于这个字数，才可能是空壳。
# 定 150 是保守值：正常新闻正文再短也有两三句话。
STUB_MAX_TEXT = 150


def is_stub_page(page_html):
    """页面是不是「只有跳转逻辑、没有正文」的空壳。"""
    if not page_html:
        return False

    body = re.sub(r"<(script|style)\b.*?</\1>", "", page_html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) >= STUB_MAX_TEXT:
        return False                      # 有实质内容，不是空壳

    return any(m.search(page_html) for m in _STUB_MARKERS)


def stub_target(page_html):
    """空壳页面要跳去哪儿，只用来打日志。"""
    m = re.search(r"""data-link=['"](\S+?)['"]""", page_html or "")
    if m:
        return m.group(1)
    m = re.search(r"""<meta[^>]+http-equiv=["']refresh["'][^>]*?url=(\S+?)["'\s>]""",
                  page_html or "", re.I)
    return m.group(1) if m else ""


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
    from enrich import fetch

    for u in (
        "https://www.gamersky.com/news/202609/2203715.shtml",   # 空壳
        "https://www.gamersky.com/news/202609/2203742.shtml",   # 正常文章
    ):
        p = fetch(u)
        print(("空壳 " if is_stub_page(p) else "正常 "), u, "->", stub_target(p) or "-")
