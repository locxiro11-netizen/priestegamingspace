#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich.py — 给精选条目补上「全文正文」和「视频」。

设计原则：
  - 不直接把别人的 HTML 塞进我们的页面，而是**用白名单重新序列化**，
    只保留 p/h2/h3/blockquote/ul/ol/li/img/iframe/a/strong/em/br。
  - iframe 只允许 YouTube / Vimeo / Bilibili / 腾讯视频，其余一律丢弃。
  - 每个源单独处理，某个源挂了只影响该源，不影响整体。

输入：scripts/out/curated.json
输出：原地写回，为每条补上 content_html 与 video 字段

用法:
    python scripts/enrich.py
    python scripts/enrich.py path/to/curated.json
"""

import html
import json
import os
import re
import ssl
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INPUT = os.path.join(ROOT, "scripts", "out", "curated.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_SSL_OK = ssl.create_default_context()
_SSL_LOOSE = ssl.create_default_context()
_SSL_LOOSE.check_hostname = False
_SSL_LOOSE.verify_mode = ssl.CERT_NONE

# 允许内嵌的视频域名（前缀匹配）
VIDEO_HOSTS = (
    "www.youtube.com/embed/", "youtube.com/embed/",
    "www.youtube-nocookie.com/embed/", "youtube-nocookie.com/embed/",
    "player.vimeo.com/video/",
    "player.bilibili.com/player.html",
    "v.qq.com/txp/iframe/",
)

MAX_CHARS = 12000


def fetch(url, accept=None, timeout=25):
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    for ctx in (_SSL_OK, _SSL_LOOSE):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# 白名单序列化
# --------------------------------------------------------------------------

_ALLOWED_TAGS = {"p", "h2", "h3", "h4", "br", "strong", "b", "em", "i",
                 "ul", "ol", "li", "blockquote", "img", "iframe", "a"}


def _attr(tag_text, name):
    m = re.search(r'\b%s\s*=\s*"([^"]*)"' % name, tag_text)
    if m:
        return html.unescape(m.group(1))
    m = re.search(r"\b%s\s*=\s*'([^']*)'" % name, tag_text)
    return html.unescape(m.group(1)) if m else ""


def _clean_inline(fragment):
    """只保留行内强调/链接标签，其余标签全部剥掉。"""
    keep = {"strong", "b", "em", "i", "br", "a"}
    out = re.sub(r"<script.*?</script>", "", fragment, flags=re.S | re.I)
    out = re.sub(r"<style.*?</style>", "", out, flags=re.S | re.I)
    tokens = re.split(r"(<[^>]+>)", out)
    buf = []
    open_tags = []
    for t in tokens:
        if not t.startswith("<"):
            buf.append(html.unescape(t))
            continue
        m = re.match(r"</?\s*([a-zA-Z0-9]+)", t)
        if not m:
            continue
        name = m.group(1).lower()
        if name not in keep:
            continue
        if t.startswith("</"):
            if open_tags and open_tags[-1] == name:
                open_tags.pop()
                buf.append("</%s>" % name)
            continue
        if name == "a":
            href = _attr(t, "href")
            if href.startswith("http"):
                buf.append('<a href="%s" target="_blank" rel="noopener">'
                           % html.escape(href, quote=True))
                open_tags.append("a")
        else:
            buf.append("<%s>" % name)
            if name != "br":
                open_tags.append(name)
    while open_tags:
        buf.append("</%s>" % open_tags.pop())
    text = "".join(buf)
    return re.sub(r"\s+", " ", text).strip()


def _is_video_src(src):
    return any(h in src for h in VIDEO_HOSTS)


# 正文里常见的噪音片段（分享按钮、推荐位、署名行等）
_NOISE_SECTION = re.compile(
    r"<(header|nav|aside|footer|figure|div|ul|section)\b[^>]*class=\"[^\"]*"
    r"(share|social|newsletter|related|recirc|promo|byline|author|"
    r"breadcrumb|tags?-list|most-read|trending|newsletter|affiliate|"
    r"disclaimer|comment)[^\"]*\"[^>]*>.*?</\1>",
    re.S | re.I)

_JUNK_TEXT = re.compile(
    r"^(share(?:\s+this)?(?:\s+article)?|join the conversation|"
    r"when you purchase through links|here'?s how it works|advertisement|"
    r"read more|more from|sign up|subscribe|follow us|facebook|whatsapp|"
    r"reddit|pinterest|flipboard|email|copy link|by\s+[\w\s.]{0,30}$|"
    r"published[\s\d\w,]{0,30}$|image credit[:：].*)$",
    re.I)


# 正文首尾常见的推广/导航残留
_TAIL_JUNK = re.compile(
    r"(preferred source|love eurogamer|view game hub|first released|"
    r"more from|read next|related\b|subscribe|newsletter|follow us|"
    r"watch on|listen to|tags?\s*:)",
    re.I)


def strip_noise(fragment):
    """去掉页头、分享栏、推荐位、评论区等非正文区块。"""
    fragment = re.sub(r"<header\b[^>]*>.*?</header>", "", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<nav\b[^>]*>.*?</nav>", "", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<aside\b[^>]*>.*?</aside>", "", fragment, flags=re.S | re.I)
    prev = None
    while prev != fragment:          # 反复清理，处理嵌套同标签
        prev = fragment
        fragment = _NOISE_SECTION.sub("", fragment)
    return fragment


def html_to_blocks(fragment):
    """把一段 HTML 转成安全的段落 / 标题 / 图片 / 视频块列表。"""
    blocks = []
    if not fragment:
        return blocks

    # 先去掉脚本、样式、导航等噪音
    for pat in (r"<script.*?</script>", r"<style.*?</style>", r"<noscript.*?</noscript>",
                r"<svg.*?</svg>", r"<form.*?</form>", r"<button.*?</button>"):
        fragment = re.sub(pat, "", fragment, flags=re.S | re.I)

    total = 0
    # 按块级标签切分
    parts = re.split(r"(<(?:p|h2|h3|h4|li|blockquote|img|iframe)\b[^>]*>.*?"
                     r"(?:</(?:p|h2|h3|h4|li|blockquote)>|>))",
                     fragment, flags=re.S | re.I)

    for part in parts:
        if total >= MAX_CHARS:
            break
        low = part[:220].lower()
        inline = ""
        tag = None

        m_img = re.match(r"<img\b([^>]*)>", part.strip(), re.I | re.S)
        if m_img:
            src = _attr("<img " + m_img.group(1) + ">", "src")
            if src.startswith("http"):
                blocks.append({"type": "image", "src": src,
                               "alt": _attr("<img " + m_img.group(1) + ">", "alt")})
                total += 60
            continue

        m_if = re.match(r"<iframe\b([^>]*)>", part.strip(), re.I | re.S)
        if m_if:
            src = _attr("<iframe " + m_if.group(1) + ">", "src")
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http") and _is_video_src(src):
                blocks.append({"type": "video", "src": src})
                total += 80
            continue

        m = re.match(r"<(p|h2|h3|h4|li|blockquote)\b[^>]*>(.*)"
                     r"(?:</\1>)$", part.strip(), re.I | re.S)
        if m:
            tag, inner = m.group(1).lower(), m.group(2)
        else:
            inner = part
            tag = "p"

        inline = _clean_inline(inner)
        if not inline or len(inline) < 2:
            continue
        if _JUNK_TEXT.match(inline.strip()):
            continue
        # 短块里出现这些词，几乎必定是分享/关注/订阅控件
        if len(inline) < 60:
            low = inline.lower()
            if any(w in low for w in (
                    "share this article", "join the conversation", "follow us",
                    "preferred source", "subscribe to our newsletter",
                    "terminally online", "read more", "advertisement",
                    "copy link", "sign up to")):
                continue
        # 过短且不成句的，多半是导航碎片
        if len(inline) < 20 and not re.search(r"[。.!？?？]", inline):
            continue
        blocks.append({"type": "text", "tag": tag, "text": inline})
        total += len(inline)

    return blocks


def blocks_to_html(blocks):
    out = []
    for b in blocks:
        if b["type"] == "text":
            out.append("<%s>%s</%s>" % (b["tag"], b["text"], b["tag"]))
        elif b["type"] == "image":
            out.append('<img src="%s" alt="%s" loading="lazy">'
                       % (html.escape(b["src"], quote=True),
                          html.escape(b.get("alt", ""), quote=True)))
        elif b["type"] == "video":
            out.append('<div class="news-video">'
                       '<iframe src="%s" frameborder="0" allow="autoplay; '
                       'encrypted-media; picture-in-picture" allowfullscreen '
                       'loading="lazy"></iframe></div>'
                       % html.escape(b["src"], quote=True))
    return "\n".join(out)


def first_video(blocks):
    for b in blocks:
        if b["type"] == "video":
            return b["src"]
    return ""


def pick_container(page):
    """从整页里挑出正文容器。

    按文档顺序取第一个段落数够多的 <article>——正文通常是最先出现的那个，
    一味挑「段落最多」反而会选中页尾的推荐位（GameSpot 有 17 个 article 标签）。
    """
    for m in re.finditer(r"<article\b[^>]*>(.*?)</article>", page, re.S | re.I):
        seg = m.group(1)
        if 0 < len(seg) < 400000 and len(re.findall(r"<p[ >]", seg)) >= 2:
            return seg

    best, best_score = "", 0
    for m in list(re.finditer(r"<div\b[^>]*>(.*?)</div>", page, re.S | re.I))[:200]:
        seg = m.group(1)
        if len(seg) > 400000:
            continue
        score = len(re.findall(r"<p[ >]", seg))
        if score > best_score:
            best, best_score = seg, score
    return best if best_score >= 3 else ""


# --------------------------------------------------------------------------
# 各源处理器：返回 blocks 列表
# --------------------------------------------------------------------------

def from_gcores(url):
    """机核：走 JSON:API，正文是 Draft.js 结构。"""
    m = re.search(r"gcores\.com/(?:articles|radios|videos)/(\d+)", url)
    if not m:
        return []
    api = "https://www.gcores.com/gapi/v1/articles/%s" % m.group(1)
    text = fetch(api, accept="application/vnd.api+json")
    if not text:
        return []
    try:
        content = json.loads(json.loads(text)["data"]["attributes"]["content"])
    except Exception:
        return []

    em = content.get("entityMap", {})
    blocks = []
    total = 0
    for b in content.get("blocks", []):
        if total >= MAX_CHARS:
            break
        btype = b.get("type")
        text_val = (b.get("text") or "").strip()

        if btype == "atomic":
            for r in b.get("entityRanges", []):
                ent = em.get(str(r.get("key")))
                if not ent:
                    continue
                data = ent.get("data") or {}
                if ent.get("type") == "IMAGE":
                    # data.file 可能是完整 URL，也可能是 False；
                    # data.path 通常是纯文件名，需要拼上 CDN 前缀
                    src = ""
                    for cand in (data.get("file"), data.get("path")):
                        if isinstance(cand, str) and cand.strip():
                            src = cand.strip()
                            break
                    if not src:
                        continue
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = "https://image.gcores.com/" + src.lstrip("/")
                    blocks.append({"type": "image", "src": src,
                                   "alt": data.get("caption", "")})
                elif "video" in (ent.get("type") or "").lower():
                    src = data.get("url") or data.get("src") or ""
                    if src.startswith("http"):
                        blocks.append({"type": "video", "src": src})
            continue

        if not text_val:
            continue
        tag = {"header-one": "h2", "header-two": "h3",
               "blockquote": "blockquote"}.get(btype, "p")
        blocks.append({"type": "text", "tag": tag, "text": text_val})
        total += len(text_val)
    return blocks


def from_generic_page(url):
    """通用网页：挑正文容器后走白名单序列化。"""
    page = fetch(url)
    if not page:
        return []
    container = pick_container(page)
    if not container:
        return []

    # og:description 基本就是正文首段，用它定位起点，切掉前面的页头/分享控件
    m = (re.search(r'property="og:description"\s+content="([^"]{20,})"', page)
         or re.search(r'content="([^"]{20,})"\s+property="og:description"', page))
    if m:
        desc = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
        for n in (60, 40, 25):
            probe = desc[:n]
            idx = container.find(probe)
            if idx > 0:
                container = container[idx:]
                break

    blocks = html_to_blocks(strip_noise(container))

    # 开头常残留署名行 / 关注按钮
    while blocks and blocks[0]["type"] == "text":
        t = blocks[0]["text"]
        if len(t) < 45 or _TAIL_JUNK.search(t) or re.match(r"^By\s+[\w\s.]{0,40}on\b", t):
            blocks.pop(0)
        else:
            break

    # 页尾常挂「相关阅读 / 测评列表 / 订阅引导」，从末尾逐个丢弃
    while blocks and blocks[-1]["type"] == "text":
        t = blocks[-1]["text"]
        # 编号链接条目，形如 "3 <a href=...>Star Wars Zero Company review</a>"
        numbered_link = bool(re.match(r"^\d+\s+<a\s", t))
        if len(t) < 50 or _TAIL_JUNK.search(t) or numbered_link:
            blocks.pop()
        else:
            break
    return blocks


def from_ign_feed(content_encoded):
    """IGN 的 RSS 自带 content:encoded 全文。"""
    if not content_encoded:
        return []
    return html_to_blocks(content_encoded)


def blocks_for(item):
    source = (item.get("source") or "").lower()
    url = item.get("source_url") or ""

    if "gcores" in url or source == "机核":
        blocks = from_gcores(url)
        if blocks:
            return blocks

    blocks = from_ign_feed(item.get("content_encoded"))
    if blocks:
        return blocks

    return from_generic_page(url)


# --------------------------------------------------------------------------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DEFAULT_INPUT

    if not os.path.exists(path):
        print("找不到输入文件: %s" % path, file=sys.stderr)
        return 1

    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if isinstance(items, dict):
        items = items.get("items", [])

    ok = failed = 0
    for it in items:
        title = (it.get("title") or "")[:34]
        try:
            blocks = blocks_for(it)
        except Exception as e:
            print("  ! %s 提取异常: %s" % (title, e), file=sys.stderr)
            blocks = []

        if not blocks:
            print("  ✗ %-36s 未取到正文（将只显示摘要+原文链接）" % title)
            failed += 1
            continue

        it["content_html"] = blocks_to_html(blocks)
        video = first_video(blocks)
        if video:
            it["video"] = video
        n_img = sum(1 for b in blocks if b["type"] == "image")
        chars = len(it["content_html"])
        print("  ✓ %-36s %5d字 %2d图 %s"
              % (title, chars, n_img, "含视频" if video else ""))
        ok += 1
        time.sleep(0.6)  # 对源站友好一点

    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("\n补全正文 %d 条，失败 %d 条 -> %s" % (ok, failed, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
