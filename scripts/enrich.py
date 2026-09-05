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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cover

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
# 注意：这里的 .{0,6000}? 是有意设上限的。
# 若用 .*?，一旦页面里同标签嵌套（div 套 div），从噪音 div 开头可以一路匹配到
# 很远的 </div>，把整段正文一起吞掉——游民星空就踩过这个坑。
_NOISE_SECTION = re.compile(
    r"<(header|nav|aside|footer|figure|div|ul|section)\b[^>]*class=\"[^\"]*"
    r"(share|social|newsletter|related|recirc|promo|byline|author|"
    r"breadcrumb|tags?-list|most-read|trending|newsletter|affiliate|"
    r"disclaimer|comment)[^\"]*\"[^>]*>.{0,6000}?</\1>",
    re.S | re.I)

# 部分站点没有 <article> 标签，按域名给正文容器提示
_SITE_CONTAINERS = [
    (r"gamersky\.com", r'class="Mid2L_con'),
    (r"3dmgame\.com", r'class="news_warp_center|class="article-content|id="news_content'),
    (r"gcores\.com", None),      # 走 API
]

# 正文结束的标志（用于把容器尾部截掉）。
# 游民星空正文末尾固定有一句「本文由游民星空制作发布，未经允许请勿转载」，
# 其后就是评论区与相关推荐，不截掉会把大量缩略图一起收进来。
_ARTICLE_END = [
    r"禁止转载",
    r"请勿转载",
    r"class=\"comment",
    r"id=\"SOHUCS",
    r"相关阅读",
]

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

# 整段尾注的起始标记（命中就把其后内容全部截断）
_TAIL_SECTION = re.compile(
    r"^(相关资讯|相关阅读|相关推荐|推荐阅读|延伸阅读|猜你喜欢|编辑推荐|"
    r"热门推荐|本文由.{0,20}发布|标签[:：]|TAG[:：])",
    re.I)

# 封面图候选。顺序即优先级：
#   og:image        —— 通行标准，多数站点都有
#   id="coverUrl"   —— 3DM 把封面图藏在 hidden input 的 value 里
_COVER_PATTERNS = (
    r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
    r'<meta[^>]*content="([^"]+)"[^>]*property="og:image"',
    r'<input[^>]*value="(https?://[^"]+)"[^>]*id="coverUrl"',
    r'<input[^>]*id="coverUrl"[^>]*value="(https?://[^"]+)"',
)

# 商城/推广横幅：这类图常被误当成封面或正文配图
_AD_IMAGE = re.compile(
    r"(mall\.|shop\.|/ad[s_]?/|banner|advert|_gg_|1784518943_551412)",
    re.I)


def extract_cover(page):
    """从整页里找文章封面图（正文容器外也可能有，比如 3DM 的 hidden input）。"""
    for pat in _COVER_PATTERNS:
        m = re.search(pat, page, re.I)
        if m:
            src = html.unescape(m.group(1)).strip()
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("http") and not _AD_IMAGE.search(src):
                return src
    return ""


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

        # 图片常被包在 <p align="center"> 里，切出来的块是以 <p> 开头的，
        # 用 re.match("<img") 去认就全漏了——3DM、游民星空的配图都是这种写法。
        # 判据改成「这段除了 img 标签没有别的文字」：既能认出包在 p 里的图，
        # 又不会把「图+说明文字」这类混排段误判成纯图片块。
        m_img = re.search(r"<img\b([^>]*)>", part, re.I | re.S)
        if m_img and not re.sub(r"<[^>]+>", "", part).strip():
            attrs = "<img " + m_img.group(1) + ">"
            src = _attr(attrs, "src")
            if src.startswith("http"):
                blocks.append({"type": "image", "src": src,
                               "alt": _attr(attrs, "alt")})
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
        # 剥掉标签后几乎没有文字 => 多半是空链接/装饰性标签，直接丢弃
        if len(re.sub(r"<[^>]+>", "", inline).strip()) < 8:
            continue
        # 页脚「Best PC games / Best RPGs / Best co-op games...」这类导航串，
        # 位置不定，只能按内容特征识别。正常段落很少连着出现 3 个 "Best "
        if len(re.findall(r"\bbest\s", inline, re.I)) >= 3:
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
            # referrerpolicy 是必须的：游民星空 / 3DM 等站点有防盗链，
            # 带外站 Referer 请求图片会 403，不发送才正常
            out.append('<img src="%s" alt="%s" loading="lazy" referrerpolicy="no-referrer">'
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


def first_image(blocks):
    for b in blocks:
        if b["type"] == "image" and b.get("src"):
            return b["src"]
    return ""


def slice_balanced_div(page, pos):
    """从属性位置 pos 回退到所属的 <div>，按 div 嵌套配平切出整个容器。

    为什么必须配平：3DM 的正文容器 news_warp_center 在正文最后一段就 </div> 闭合了，
    文末的商城广告横幅、「相关资讯」推荐列表都在容器外面。早先直接切
    page[start:start+45000] 不看闭合位置，于是把广告图（785×92 的细长横幅）
    和一堆 2023 年的推荐链接全当成了正文。配平后这些自然被排除。

    返回 None 表示配平失败，调用方需回退到定长切片。
    """
    lt = page.rfind("<div", 0, pos)
    if lt < 0:
        return None
    depth = 0
    for m in re.finditer(r"<div\b[^>]*?(/?)>|</div\s*>", page[lt:], re.I):
        tok = m.group(0)
        if tok.startswith("</"):
            depth -= 1
            if depth <= 0:
                return page[lt: lt + m.end()]
        elif m.group(1) != "/":        # 自闭合 <div .../> 不计入深度
            depth += 1
    return None


def pick_container(page, url=""):
    """从整页里挑出正文容器。

    按文档顺序取第一个段落数够多的 <article>——正文通常是最先出现的那个，
    一味挑「段落最多」反而会选中页尾的推荐位（GameSpot 有 17 个 article 标签）。
    """
    for m in re.finditer(r"<article\b[^>]*>(.*?)</article>", page, re.S | re.I):
        seg = m.group(1)
        if 0 < len(seg) < 400000 and len(re.findall(r"<p[ >]", seg)) >= 2:
            return seg

    # 站点专属容器（游民星空、3DM 等没有 article 标签）
    for host, hint in _SITE_CONTAINERS:
        if hint and re.search(host, url):
            m = re.search(hint, page)
            if m:
                # 优先按 div 配平切出容器本体；配不出来才退回定长切片
                seg = slice_balanced_div(page, m.start())
                if seg is None:
                    seg = page[m.start(): m.start() + 45000]
                # 截到正文结束处为止，避免把评论区/相关推荐的缩略图收进来
                cut = -1
                for pat in _ARTICLE_END:
                    em = re.search(pat, seg)
                    if em and em.start() > 500:
                        cut = em.start() if cut < 0 else min(cut, em.start())
                if cut > 0:
                    seg = seg[:cut]
                if len(re.findall(r"<p[ >]", seg)) >= 2:
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
    """通用网页：挑正文容器后走白名单序列化。

    返回 (blocks, cover)：cover 是从页头 meta / hidden input 里挖到的封面图，
    正文没图时可以拿它顶上，避免列表页卡片开天窗。
    """
    page = fetch(url)
    if not page:
        return [], ""
    cover = extract_cover(page)
    container = pick_container(page, url)
    if not container:
        return [], cover

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

    # 正文结束后常常还跟着一串图片/视频（侧边栏推荐位缩略图）和
    # 「相关阅读 / 订阅引导」文字。这两类残留是**交替出现**的，必须放在同一个
    # 循环里反复处理：pop 掉若干文字块后，底下可能又露出图片块；pop 掉图片后，
    # 下面可能还有文字。
    # 早先写成「先循环 pop 图片、再循环 pop 文字」两个独立的循环，一旦末尾是
    # 「文字→图片→文字」的夹心结构，第二个循环一遇到图片就停住，后面整串残留
    # 全都清不掉——GameSpot 的 "Follow Us / Featured In This Story" 和 3DM 的
    # 商城横幅 + 相关资讯都是这么漏进来的。
    while blocks:
        b = blocks[-1]
        if b["type"] in ("image", "video"):
            blocks.pop()
            continue
        if b["type"] != "text":
            break
        t = b["text"]
        # 编号链接条目，形如 "3 <a href=...>Star Wars Zero Company review</a>"
        numbered_link = bool(re.match(r"^\d+\s+<a\s", t))
        # 页脚导航空列，形如 "Best gunplay Best RPGs : ... Best co-op games : ..."
        nav_list = len(re.findall(r"\bbest\s", t, re.I)) >= 3
        # 剥掉标签后没剩几个字 => 链接占位，同样丢掉
        hollow = len(re.sub(r"<[^>]+>", "", t).strip()) < 20
        if len(t) < 50 or _TAIL_JUNK.search(t) or numbered_link or nav_list or hollow:
            blocks.pop()
            continue
        break

    # 第二道防线：3DM 这类站点正文后会整段挂「相关资讯 / 标签：...」推荐列表，
    # 而且推荐列表前还夹着一张广告图，上面「从末尾逐个丢弃」的写法会在广告图
    # 处断掉、清不干净。这里再从后往前找明确的尾注起点，命中就整段截断。
    for i in range(len(blocks) - 1, 0, -1):
        b = blocks[i]
        if b["type"] != "text":
            continue
        plain = re.sub(r"<[^>]+>", "", b["text"]).strip()
        if _TAIL_SECTION.match(plain):
            del blocks[i:]
            break

    return blocks, cover


def from_ign_feed(content_encoded):
    """IGN 的 RSS 自带 content:encoded 全文。"""
    if not content_encoded:
        return [], ""
    return html_to_blocks(content_encoded), ""


# 尾部推荐位残留的常见字样（用于回检已发布条目是否「脏」了）
_TAIL_HINT = re.compile(
    r"(相关资讯|相关阅读|相关推荐|热门推荐|推荐阅读|延伸阅读|猜你喜欢|"
    r"标签[:：]|TAG[:：]|已有\s*\d+\s*人评分|您还未评分|"
    r"follow us|featured in this story|advertisement|more from|read next)",
    re.I)


def content_is_dirty(item):
    """判断一条已发布内容是否需要重新提取。

    两类问题都只在 enrich 修好之后才回检得出来：
      1. 封面图或正文配图是商城推广横幅；
      2. 正文尾部残留「相关资讯 / 评分 / Follow Us」推荐位。
    """
    h = item.get("content_html") or ""
    img = (item.get("image") or "").strip()
    if _AD_IMAGE.search(img):
        return True
    # 只检查图片地址。直接对整段 HTML 跑 _AD_IMAGE 会误判：GameSpot 正文里
    # 出现 "Advertisement" 这个词就会被当成广告图。
    for src in re.findall(r'<img[^>]+src="([^"]+)"', h):
        if _AD_IMAGE.search(src):
            return True
    plain = re.sub(r"<[^>]+>", "", h)
    return bool(plain) and bool(_TAIL_HINT.search(plain[-300:]))


def blocks_for(item):
    """返回 (blocks, cover)。各源处理器失败时自动降级到下一个。"""
    source = (item.get("source") or "").lower()
    url = item.get("source_url") or ""

    if "gcores" in url or source == "机核":
        blocks = from_gcores(url)
        if blocks:
            return blocks, ""

    blocks, _ = from_ign_feed(item.get("content_encoded"))
    if blocks:
        return blocks, ""

    return from_generic_page(url)


# --------------------------------------------------------------------------

CJK = re.compile(r"[\u4e00-\u9fff]")


def is_chinese(text, threshold=0.15):
    """判断一段文字是否已经是中文（避免对中文源做无谓翻译）。"""
    if not text:
        return True
    sample = text[:3000]
    letters = [c for c in sample if c.isalpha()]
    if not letters:
        return True
    return sum(1 for c in letters if CJK.match(c)) / len(letters) >= threshold


def write_translate_task(items, path):
    """把需要翻译的段落抽成纯文本清单，交给 AI 逐段翻译。

    输出结构：{ uid: { "title": ..., "texts": [段落1, 段落2, ...] } }
    AI 翻译后写回 scripts/out/translated.json，格式相同（值换成译文数组）。
    """
    task = {}
    for it in items:
        if is_chinese(it.get("content_html", "")):
            continue
        texts = [b["text"] for b in (it.get("content_blocks") or [])
                 if b["type"] == "text" and b.get("text")]
        if not texts:
            continue
        task[it.get("uid") or it.get("source_url")] = {
            "title": it.get("title", ""),
            "source": it.get("source", ""),
            "texts": texts,
        }
    out_path = os.path.join(os.path.dirname(path), "to_translate.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    if task:
        total = sum(len(v["texts"]) for v in task.values())
        print("\n待翻译：%d 篇 / %d 段 -> %s" % (len(task), total, out_path))
    else:
        print("\n全部为中文，无需翻译")
    return out_path


def apply_translations(items, path):
    """把 scripts/out/translated.json 的译文填回 content_blocks 并重序列化。"""
    tr_path = os.path.join(os.path.dirname(path), "translated.json")
    if not os.path.exists(tr_path):
        return 0
    try:
        with open(tr_path, "r", encoding="utf-8") as f:
            trans = json.load(f)
    except Exception as e:
        print("  ! translated.json 解析失败: %s" % e, file=sys.stderr)
        return 0

    n = 0
    for it in items:
        key = it.get("uid") or it.get("source_url")
        entry = trans.get(key)
        if not entry:
            continue
        texts = entry.get("texts") if isinstance(entry, dict) else entry
        if not texts:
            continue
        i = 0
        for b in (it.get("content_blocks") or []):
            if b["type"] == "text" and b.get("text"):
                if i < len(texts) and texts[i]:
                    b["text"] = texts[i]
                i += 1
        it["content_html"] = blocks_to_html(it["content_blocks"])
        it["translated"] = True
        n += 1
    if n:
        print("已应用译文：%d 篇" % n)

    # 翻译黑名单：正文仍是英文的篇目直接剔除，不发布
    ut_path = os.path.join(os.path.dirname(path), "untranslated.json")
    if os.path.exists(ut_path):
        try:
            with open(ut_path, "r", encoding="utf-8") as f:
                blocked = set(json.load(f))
        except Exception:
            blocked = set()
        if blocked:
            kept = []
            for it in items:
                key = it.get("uid") or it.get("source_url")
                if key in blocked and not is_chinese(it.get("content_html", "")):
                    print("  ✗ 剔除未翻译篇目: %s" % (it.get("title") or "")[:40])
                    continue
                kept.append(it)
            items[:] = kept
            os.remove(ut_path)
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DEFAULT_INPUT
    apply_only = "--apply-translation" in sys.argv[1:]

    if not os.path.exists(path):
        print("找不到输入文件: %s" % path, file=sys.stderr)
        return 1

    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if isinstance(items, dict):
        items = items.get("items", [])

    # 只把译文填回并重序列化，不重新抓原文
    if apply_only:
        apply_translations(items, path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return 0

    ok = failed = 0
    for it in items:
        title = (it.get("title") or "")[:34]
        # 变量名不能叫 cover —— 会盖掉同名的 cover 模块
        page_cover = ""
        try:
            blocks, page_cover = blocks_for(it)
        except Exception as e:
            print("  ! %s 提取异常: %s" % (title, e), file=sys.stderr)
            blocks = []

        if not blocks:
            print("  ✗ %-36s 未取到正文（将只显示摘要+原文链接）" % title)
            failed += 1
            continue

        it["content_html"] = blocks_to_html(blocks)
        # 结构化段落留一份，供 AI 逐段翻译后重新拼装
        it["content_blocks"] = blocks
        video = first_video(blocks)
        if video:
            it["video"] = video
        # 封面图三件事，按优先级处理：
        #   1. 列表页源（3DM/游民星空）常拿不到缩略图，卡片会开天窗；
        #   2. 有时又把文末的商城推广横幅当成封面（3DM 那张 785×92 的细长广告图）；
        #   3. 拿到了但是 196×118 的列表缩略图——铺满卡片会糊成一团。
        # 第 3 种要挑一下：正文首图和 og:image 哪个够大用哪个。3DM 的
        # og:image 就是列表缩略图本体（196×118），但正文首图是 1080×602；
        # 反过来有些站的正文首图是图标，得靠 og:image 兜底。
        filled_cover = False
        cur_img = (it.get("image") or "").strip()
        if not cur_img or _AD_IMAGE.search(cur_img):
            fallback = first_image(blocks) or page_cover
            if fallback:
                it["image"] = fallback
                filled_cover = True
            elif _AD_IMAGE.search(cur_img):
                # 拿不到替代图时宁可留空，也别把广告横幅挂到卡片上
                it["image"] = ""
        else:
            it["image"], filled_cover = cover.pick_bigger(
                cur_img, [first_image(blocks), page_cover])

        # 最后统一把缩略图参数换成大图档位，并把能推断出的原图尺寸记下来，
        # 前端靠它提前占位、避免图片加载完再跳版
        if (it.get("image") or "").strip():
            it["image"], w, h = cover.cover_fields(it["image"].strip())
            if w:
                it["image_w"], it["image_h"] = w, h
            if cover.is_lowres(it["image"]):
                print("    (封面图仍是缩略图，前端会降级显示)")

        n_img = sum(1 for b in blocks if b["type"] == "image")
        chars = len(it["content_html"])
        print("  ✓ %-36s %5d字 %2d图 %s%s"
              % (title, chars, n_img, "含视频" if video else "",
                 " 卡片图取自正文" if filled_cover else ""))
        ok += 1
        time.sleep(0.6)  # 对源站友好一点

    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("\n补全正文 %d 条，失败 %d 条 -> %s" % (ok, failed, path))
    write_translate_task(items, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
