#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover.py — 封面图分辨率处理：把源站给的缩略图 URL 换回大图，并尽量推断原图尺寸。

为什么需要这个模块
------------------
RSS/列表页给的封面图基本都是缩略图，直接铺到 ~1100px 宽的卡片上会被浏览器
放大 2-5 倍，看起来就是一团糊。各家的缩图参数都写在 URL 里，改参数就能拿到
大图，不用下载、不用转码、不用额外请求。

取值（写进 content.json 的字段）：
    image          升级后的大图 URL
    image_w/h      能从 URL 推断出的原图像素尺寸，推断不出来就不写

单独成模块的原因同 genre.py：enrich.py（新条目选图）、publish.py（兜底）、
backfill_cover.py（存量回填）都要用同一套规则。

python scripts/cover.py 可跑自检，会打印几条真实 URL 的升级前后对比。
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 目标宽度。卡片最宽约 1100 CSS px，2x 屏要 2200；但再大就是白烧流量，
# 各家图床的档位也大多止步 1600-1920，取 1600 是性价比拐点。
TARGET_W = 1600
# 但「目标宽度」只能用来放大缩略图，不能用来缩小已经是高清的原图。
# IGN 的原图常常就是 1920 甚至 3840，套 width=1600 反而把清晰度砍掉了
# （实测 1920x1080 → 1600x900），所以给原图站点单独留一个更高的上限。
MAX_W = 1920
# futurecdn 的档位是写在路径里的（-宽-质量），只能整档替换
FUTURECDN_W = 1920
FUTURECDN_Q = 90

# 拿到也白搭的图：这些是列表页专用的小缩略图目录，URL 上没有可用的放大参数，
# 只能回文章页取 og:image 替换掉（见 enrich.py）
LOWRES_PATTERNS = (
    re.compile(r"img\.3dmgame\.com/uploads/images/thumbnews/", re.I),
    re.compile(r"imgs\.gamersky\.com/upimg/new_preview/", re.I),
    # 别加 /small_ 这类「看起来像缩略图」的通配规则：
    # 游民星空正文图都叫 small_xxx.png，实际有 550px，是它们能给的最大尺寸。
    # 一刀切判死反而会把 550 的图换成 200 的封面，越换越糊。
)

# 已知会拿到极小图的尺寸提示：命中就说明这张图不能当封面用
MIN_COVER_W = 640


def _split(url):
    return urlsplit(url or "")


def _join(scheme, netloc, path, query, fragment=""):
    return urlunsplit((scheme, netloc, path, query, fragment))


def _set_query(url, updates):
    """替换/追加查询参数，保持其他参数不变。"""
    s = _split(url)
    if not s.scheme:
        return url
    q = dict(parse_qsl(s.query, keep_blank_values=True))
    q.update(updates)
    return _join(s.scheme, s.netloc, s.path, urlencode(q), s.fragment)


# ---------------------------------------------------------------- 升级规则
# 每条规则是 (匹配 host 的正则, 处理函数)。函数返回新 URL，处理不了就原样返回。


def _gcores(url):
    """机核：x-oss-process 里的 m_fill,w_626,h_292 把原图压成了 626 宽的横幅。

    去掉整个查询串就是原图；文件名里的 -1268-727 还直接给了原图尺寸。
    注意别去改成更大的 w_：OSS 会真的把 1268 的原图插值到 1600，
    体积涨了但一个像素的细节都没多。
    """
    s = _split(url)
    if not s.query:
        return url
    return _join(s.scheme, s.netloc, s.path, "", s.fragment)


def _gnwcdn(url):
    """GameSpot 图床（assetsio.gnwcdn.com）：width=690 → 1600。"""
    return _set_query(url, {"width": TARGET_W, "quality": 90})


def _ign(url):
    """IGN 图床（imgix）：默认给的是原图，1920-3840 宽、200KB-1MB 的 JPEG。

    只做两件事：转成 webp（同样清晰度体积减半），以及把超宽的封顶到 1920。
    imgix 不会把小图插值放大，这条规则因此是纯赚。
    """
    return _set_query(url, {"width": MAX_W, "format": "webp"})


def _futurecdn(url):
    """Future 系（PC Gamer / GamesRadar）：路径末尾的 -宽-质量 就是档位。
    -1280-80 → -1920-90。没有档位后缀的说明本来就是原图，不动。"""
    return re.sub(r"-(\d{2,4})-(\d{1,3})(?=\.[a-z]{3,5}(?:[?#]|$))",
                  "-%d-%d" % (FUTURECDN_W, FUTURECDN_Q), url, count=1)


def _wordpress(url):
    """WordPress 附件：?w=636 → 1200，或者把 -1024x436 这类尺寸后缀去掉取原图。

    先处理查询串里的 w=，因为它最常见也最安全；没有再尝试剥尺寸后缀
    （剥了可能 404，但只在明确认出是 WP 尺寸格式时才动手）。
    """
    s = _split(url)
    q = dict(parse_qsl(s.query, keep_blank_values=True))
    if any(k in q for k in ("w", "width")):
        key = "w" if "w" in q else "width"
        return _set_query(url, {key: TARGET_W})
    new_path = re.sub(r"-\d{2,4}x\d{2,4}(?=\.[a-z]{3,5}$)", "", s.path)
    if new_path != s.path:
        return _join(s.scheme, s.netloc, new_path, s.query, s.fragment)
    return url


_RULES = (
    (re.compile(r"(?:^|\.)gcores\.com$", re.I), _gcores),
    (re.compile(r"assetsio\.gnwcdn\.com$", re.I), _gnwcdn),
    (re.compile(r"assets-prd\.ignimgs\.com$", re.I), _ign),
    (re.compile(r"cdn\.mos\.cms\.futurecdn\.net$", re.I), _futurecdn),
    (re.compile(r"(?:^|\.)gamespot\.com$", re.I), _wordpress),
    # gamelook 别套 WordPress 规则：它的 -1024x436 后缀是必需的，
    # 剥掉就 403（实测）。何况它的证书也不匹配域名，图根本加载不出来。
)


def upgrade(url):
    """把封面图 URL 升到能拿到的最高清版本。认不出的图床原样返回。

    幂等：对已经升级过的 URL 再跑一次结果不变。
    """
    if not url or not url.startswith(("http://", "https://")):
        return url
    s = _split(url)
    host = s.netloc.split(":")[0].lower()
    for pat, fn in _RULES:
        if pat.search(host):
            try:
                new = fn(url)
            except Exception:
                continue
            if new and new != url:
                return new
            return url
    return url


# ---------------------------------------------------------------- 尺寸推断


def _size_from_gcores(path):
    """机核文件名里带原图尺寸：...-1268-727.jpg"""
    m = re.search(r"-(\d{2,4})-(\d{2,4})\.[a-z]{3,5}$", path, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _size_from_futurecdn(path):
    """futurecdn 只有宽度：-1280-80.jpg"""
    m = re.search(r"-(\d{2,4})-\d{1,3}\.[a-z]{3,5}$", path, re.I)
    return (int(m.group(1)), 0) if m else None


def _size_from_wp(path):
    """WordPress 尺寸后缀：...-1024x436.png"""
    m = re.search(r"-(\d{2,4})x(\d{2,4})\.[a-z]{3,5}$", path, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def intrinsic_size(url):
    """从 URL 推断原图尺寸，返回 (w, h)；高度未知时 h=0，推断不出返回 None。

    只做字符串解析，不发请求——CI 里逐条下载图片太慢了。
    """
    if not url:
        return None
    s = _split(url)
    path = s.path
    host = s.netloc.split(":")[0].lower()

    if "gcores.com" in host:
        return _size_from_gcores(path)
    if "futurecdn.net" in host:
        return _size_from_futurecdn(path)
    size = _size_from_wp(path)
    if size:
        return size

    # 明确指定了输出宽度的，我们就知道它会是多大
    q = dict(parse_qsl(s.query, keep_blank_values=True))
    for key in ("width", "w"):
        if q.get(key, "").isdigit():
            return (int(q[key]), 0)
    return None


def is_lowres(url):
    """这张图当封面会糊吗？

    注意要拿「升级之后」的 URL 去判尺寸：GameSpot 的 ?w=636 看着小，
    但改成 ?w=1600 就能拿到大图，不能因为它原始参数小而判死。
    """
    if not url:
        return False
    if any(p.search(url) for p in LOWRES_PATTERNS):
        return True
    size = intrinsic_size(upgrade(url))
    return bool(size and 0 < size[0] < MIN_COVER_W)


def pick_bigger(current, candidates):
    """从候选封面图里挑一张「够大」的，返回 (选中的 URL, 是否换了图)。

    当前这张够用就直接留着；否则按候选顺序找第一张够大的。
    全都救不回来时返回升过级的原图——总比换成一张更小的强。

    候选顺序有讲究：3DM 的 og:image 就是列表缩略图本体（196×118），
    但它的正文首图有 1080×602；反过来有些站正文首图是图标，得靠 og:image。
    所以调用方要把两个候选都传进来，让尺寸说话。
    """
    if current and not is_lowres(current):
        return upgrade(current), False
    for cand in candidates:
        if cand and not is_lowres(cand):
            return upgrade(cand), True
    return upgrade(current or ""), False


def is_thumb_only(url):
    """这张图是不是只能回文章页重抓、改 URL 参数救不回来的那种？

    比 is_lowres 窄得多：只认那些「缩略图专用目录」（3DM 的 thumbnews、
    游民星空的 new_preview），它们的 URL 上压根没有可用的放大参数。
    机核那种 555 宽的小原图虽然也不够看，但改地址只会拿到同一张，
    没必要为它回源。
    """
    return bool(url) and any(p.search(url) for p in LOWRES_PATTERNS)


def cover_fields(url):
    """返回 (升级后的 URL, 宽度, 高度)，供写入 content.json。"""
    big = upgrade(url)
    size = intrinsic_size(big) or (0, 0)
    return big, size[0], size[1]


if __name__ == "__main__":
    samples = [
        "https://image.gcores.com/5adb1b2fc521dc8eb74ba67584c8e4c0-1268-727.jpg"
        "?x-oss-process=image/resize,limit_1,m_fill,w_626,h_292/quality,q_90",
        "https://assetsio.gnwcdn.com/VINTAGE_VICE_CITY_PACK_04.jpg"
        "?width=690&quality=85&format=jpg&auto=webp",
        "https://assets-prd.ignimgs.com/2026/09/03/jason-and-lucia-04-1788457455588.jpg",
        "https://cdn.mos.cms.futurecdn.net/iUgDptF7wAUvtumkMBTvee-1280-80.jpg",
        "https://www.gamespot.com/wp-content/uploads/2026/09/Jason_and_Lucia_11.jpg?w=636",
        "https://img.3dmgame.com/uploads/images/thumbnews/2026/0830/1788053528951.jpg",
        "https://imgs.gamersky.com/upimg/new_preview/2026/08/30/origin_b_202608.jpg",
        "https://example.com/unknown-cdn/pic.jpg",
    ]
    for u in samples:
        big, w, h = cover_fields(u)
        flag = "低分辨率" if is_lowres(u) else "  ok  "
        print(f"[{flag}] {w or '?':>4}x{h or '?':<4}\n  原 {u[:100]}\n  新 {big[:100]}")
