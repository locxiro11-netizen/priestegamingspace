#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news.py — 抓取多源游戏资讯，输出去重后的候选列表。

流程:
  1. 读取 config.json 决定抓哪些源
  2. 抓取 RSS / Steam API
  3. 过滤掉太旧的和已经发布过的
  4. 写入 scripts/out/candidates.json

用法:
    python scripts/fetch_news.py
    python scripts/fetch_news.py --ignore-seen   # 恢复用：忽略「已看过」状态

去重说明:
  - 「已发布」：以线上 content.json 的 source_url 为准，防止重复发布。
  - 「已看过」：由 publish.py 在发布成功后写入 scripts/state/seen.json，
    作用是避免第二天重复评估同一批已被淘汰的新闻。
    抓取阶段**不写**该状态，否则中途失败会污染候选池。
    若状态被误污染，用 --ignore-seen 恢复。
"""

import json
import os
import re
import ssl
import sys
import time
import base64
import hashlib
import urllib.request
import urllib.error
import html
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "scripts", "config.json")
OUT_DIR = os.path.join(ROOT, "scripts", "out")
STATE_DIR = os.path.join(ROOT, "scripts", "state")
CANDIDATES_PATH = os.path.join(OUT_DIR, "candidates.json")
SEEN_PATH = os.path.join(STATE_DIR, "seen.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_SSL_OK = ssl.create_default_context()
_SSL_LOOSE = ssl.create_default_context()
_SSL_LOOSE.check_hostname = False
_SSL_LOOSE.verify_mode = ssl.CERT_NONE


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def http_get(url, timeout=20, retries=2):
    """带重试的 GET，返回 str；失败返回 None。"""
    for attempt in range(retries + 1):
        for ctx in (_SSL_OK, _SSL_LOOSE):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA,
                    "Accept": "application/rss+xml, application/xml, text/xml, application/json, */*",
                })
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
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    return None


class _TextStripper(HTMLParser):
    """把 HTML 片段压成纯文本，顺带收集第一张图片。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.first_img = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "img" and not self.first_img:
            src = dict(attrs).get("src") or dict(attrs).get("data-src")
            if src and src.startswith("http"):
                self.first_img = src
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self):
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()


def html_to_text(html):
    if not html:
        return "", None
    p = _TextStripper()
    try:
        p.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip(), None
    return p.text(), p.first_img


def _local(tag):
    """去掉 XML 命名空间前缀。"""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_local(el, name):
    """在当前元素的直接子节点里按本地名查找。"""
    for child in el:
        if _local(child.tag) == name:
            return child
    return None


def _findall_local(el, name):
    return [c for c in el if _local(c.tag) == name]


def _iter_local(root, name):
    return [el for el in root.iter() if _local(el.tag) == name]


def parse_time(value):
    """把各种时间格式统一成 aware datetime，失败返回 None。"""
    if not value:
        return None
    value = value.strip()
    try:
        return parsedate_to_datetime(value)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def uid_of(url):
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# 各源解析
# --------------------------------------------------------------------------

def parse_rss(xml_text, source_name, limit):
    """解析 RSS 2.0 / Atom，返回标准化条目列表。"""
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        print(f"  ! {source_name} XML 解析失败: {e}", file=sys.stderr)
        return []

    items = _iter_local(root, "item") or _iter_local(root, "entry")
    out = []

    for el in items[:limit]:
        title_el = _find_local(el, "title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        title = html_to_text(title)[0]
        if not title:
            continue

        # 链接
        link = ""
        link_el = _find_local(el, "link")
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()
        if not link:
            guid_el = _find_local(el, "guid") or _find_local(el, "id")
            if guid_el is not None and (guid_el.text or "").startswith("http"):
                link = guid_el.text.strip()
        if not link:
            continue

        # 正文 / 摘要
        desc = ""
        image = None
        for tag in ("description", "summary", "content", "encoded"):
            child = _find_local(el, tag)
            if child is not None and (child.text or child.tail):
                desc, image = html_to_text(child.text or "")
                break

        # 图片：专用字段优先，其次正文首图
        if not image:
            for tag in ("thumb", "thumbnail", "content", "enclosure"):
                child = _find_local(el, tag)
                if child is not None:
                    src = child.get("url") or child.get("src") or child.text
                    if src and src.strip().startswith("http"):
                        image = src.strip()
                        break
        if not image:
            for child in el.iter():
                if _local(child.tag) == "thumbnail":
                    src = child.get("url")
                    if src and src.startswith("http"):
                        image = src
                        break

        # 时间
        published = None
        for tag in ("pubDate", "published", "updated", "date"):
            child = _find_local(el, tag)
            if child is not None and child.text:
                published = parse_time(child.text)
                if published:
                    break

        # 部分源（如 IGN）在 RSS 里就带 content:encoded 全文，留着给 enrich.py 用
        full_html = ""
        for tag in ("encoded", "content"):
            child = _find_local(el, tag)
            if child is not None and child.text and len(child.text) > len(desc):
                full_html = child.text
                break

        out.append({
            "uid": uid_of(link),
            "source": source_name,
            "source_url": link,
            "title": title,
            "raw_desc": desc[:900],
            "content_encoded": full_html[:60000],
            "image": image or "",
            "game": "",
            "published": published.astimezone(timezone.utc).isoformat() if published else "",
        })

    return out


def parse_steam(appid, game_name, limit, max_len=700):
    url = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
           f"?appid={appid}&count={limit}&maxlength={max_len}")
    text = http_get(url)
    if not text:
        return []
    try:
        data = json.loads(text).get("appnews", {}).get("newsitems", [])
    except Exception:
        return []

    out = []
    for n in data:
        link = n.get("url") or ""
        title = (n.get("title") or "").strip()
        if not link or not title:
            continue
        contents = re.sub(r"\[/?[a-zA-Z0-9=*#/\-\s]+\]", " ", n.get("contents") or "")
        contents = re.sub(r"\s+", " ", contents).strip()
        ts = n.get("date")
        published = None
        if ts:
            try:
                published = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except Exception:
                published = None
        out.append({
            "uid": uid_of(link),
            "source": "Steam",
            "source_url": link,
            "title": title,
            "raw_desc": contents[:900],
            "image": "",
            "game": game_name,
            "published": published.isoformat() if published else "",
        })
    return out


def parse_list_page(page_html, base, link_pattern, source_name, limit,
                    fetch_meta=True, exclude_pattern=None):
    """国内不少站点（游民星空、3DM）已经关掉 RSS，只能抓列表页。

    做法：用正则捞出文章链接，再在链接附近的一小段 HTML 里找标题/配图；
    标题找不到时，退一步去抓文章页的 og:title / og:description。
    """
    links = []
    for m in re.finditer(link_pattern, page_html):
        # 配置里的正则可能带捕获组也可能不带，两种都支持
        url = m.group(1) if m.re.groups else m.group(0)
        if url.startswith("/"):
            url = base.rstrip("/") + url
        elif not url.startswith("http"):
            continue
        if url not in links:
            links.append(url)

    exclude = re.compile(exclude_pattern) if exclude_pattern else None

    out = []
    for link in links[:limit]:
        idx = page_html.find(link)
        window = page_html[max(0, idx - 400): idx + 1600] if idx >= 0 else ""

        title = ""
        m = re.search(r'title="([^"]{6,90})"', window)
        if m:
            title = html.unescape(m.group(1)).strip()

        image = ""
        m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                      window, re.I)
        if m:
            image = m.group(1)

        desc = ""
        if not title and fetch_meta:
            page = http_get(link, timeout=20, retries=1)
            if page:
                mt = re.search(r'property="og:title"\s+content="([^"]*)"', page) \
                    or re.search(r"<title>(.*?)</title>", page, re.S)
                if mt:
                    title = re.sub(r"\s+", " ", html.unescape(mt.group(1))).strip()
                    title = re.sub(r"[-_|]\s*(游民星空|3DM|3DMGAME).*$", "", title).strip()
                md = re.search(r'property="og:description"\s+content="([^"]*)"', page)
                if md:
                    desc = re.sub(r"\s+", " ", html.unescape(md.group(1))).strip()

        if not title:
            continue
        if exclude and exclude.search(title):
            continue

        out.append({
            "uid": uid_of(link),
            "source": source_name,
            "source_url": link,
            "title": title,
            "raw_desc": desc[:900],
            "content_encoded": "",
            "image": image,
            "game": "",
            # 列表页拿不到精确发布时间，留空表示「按最新处理」
            "published": "",
        })
    return out


def url_month_stale(url, max_months=1):
    """用 URL 里的年月判断条目是否明显过期。

    列表页（3DM / 游民星空）的条目拿不到发布时间，而列表页往往混着
    「热门推荐」板块的老文章 —— 实测 3DM 首页带了 5 条 2023-11 的旧闻。
    这类条目 published 为空，天数过滤器拦不住，会被当成新闻发出去。
    这两家的正文 URL 都带 /YYYYMM/ 段，拿它做兜底校验。

    返回 True 表示该丢弃。识别不出年月时返回 False（保守保留）。
    """
    m = re.search(r"/(20\d{2})(\d{2})/", url or "")
    if not m:
        return False
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return False
    now = datetime.now()
    return (now.year * 12 + now.month) - (year * 12 + month) > max_months


# --------------------------------------------------------------------------
# 去重
# --------------------------------------------------------------------------

def _collect_published(data):
    urls = set()
    for item in data.get("news", []) or []:
        if item.get("source_url"):
            urls.add(item["source_url"])
        if item.get("uid"):
            urls.add("uid:" + item["uid"])
    return urls


def load_published(cfg):
    """读取已发布内容用于去重。

    优先走 GitHub API 读仓库里真正的 content.json（权威来源），读不到再退回公开网址。
    公开网址可能落后于仓库，且部署来源变动时可能读到完全不同的文件，
    拿它做去重依据会导致重复发布。
    """
    repo = cfg.get("repo") or {}
    api = (f"https://api.github.com/repos/{repo.get('owner')}/{repo.get('name')}"
           f"/contents/{repo.get('content_path')}?ref={repo.get('branch', 'main')}")

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        try:
            token = open(os.path.join(ROOT, ".gh_token"), encoding="utf-8").read().strip()
        except Exception:
            token = ""

    if token and repo.get("owner"):
        req = urllib.request.Request(api, headers={
            "Authorization": "Bearer " + token,
            "User-Agent": "PriesteGamingSpace-NewsBot",
            "Accept": "application/vnd.github+json",
        })
        for ctx in (_SSL_OK, _SSL_LOOSE):
            try:
                with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                data = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
                urls = _collect_published(data)
                print(f"  仓库内已发布 {len(urls)} 条，用于去重（来源：GitHub API）")
                return urls
            except Exception:
                continue
        print("  ! GitHub API 读取失败，改用公开网址", file=sys.stderr)

    text = http_get(cfg.get("live_content_url", ""), timeout=20, retries=1)
    if not text:
        print("  ! 无法读取已发布内容，跳过去重", file=sys.stderr)
        return set()
    try:
        urls = _collect_published(json.loads(text))
        print(f"  线上已发布 {len(urls)} 条，用于去重（来源：公开网址）")
        return urls
    except Exception as e:
        print(f"  ! content.json 解析失败: {e}", file=sys.stderr)
        return set()


def load_seen():
    if not os.path.exists(SEEN_PATH):
        return set()
    try:
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f).get("uids", []))
    except Exception:
        return set()


def save_seen(uids):
    os.makedirs(STATE_DIR, exist_ok=True)
    existing = load_seen()
    existing.update(uids)
    # 只保留最近 3000 条，避免无限膨胀
    trimmed = list(existing)[-3000:]
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"uids": trimmed, "updated": datetime.now().isoformat(timespec="seconds")},
                  f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    ignore_seen = "--ignore-seen" in sys.argv[1:]

    max_age_days = cfg.get("max_age_days", 3)
    max_per_source = cfg.get("max_per_source", 15)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    print("读取已发布内容（去重依据）...")
    published = load_published(cfg)
    seen = set() if ignore_seen else load_seen()
    if ignore_seen:
        print("  --ignore-seen：本次忽略「已看过」状态，只按已发布去重")

    all_items = []
    sources = cfg.get("sources", {})

    for key, sc in sources.items():
        if not sc.get("enabled"):
            continue
        name = sc.get("name", key)
        print(f"抓取 {name} ...")

        stype = sc.get("type")
        if stype == "steam":
            items = []
            for appid, gname in (cfg.get("steam_games") or {}).items():
                items.extend(parse_steam(appid, gname, max(3, max_per_source // 3)))
        else:
            text = http_get(sc.get("url", ""))
            if not text:
                print(f"  ! {name} 抓取失败，跳过", file=sys.stderr)
                items = []
            elif stype == "list":
                items = parse_list_page(text, sc.get("url", ""),
                                        sc.get("link_pattern", ""),
                                        name, max_per_source,
                                        exclude_pattern=sc.get("exclude_pattern"))
            else:
                items = parse_rss(text, name, max_per_source)

        # 按 URL 过滤（如机核 /radios/ 电台节目没有文章正文）
        excl_url = sc.get("exclude_url_pattern")
        if excl_url:
            rx_url = re.compile(excl_url)
            n0 = len(items)
            items = [it for it in items if not rx_url.search(it.get("source_url", ""))]
            if n0 != len(items):
                print(f"  URL 规则过滤掉 {n0 - len(items)} 条")

        fresh = []
        stale_by_url = 0
        for it in items:
            pub = parse_time(it["published"]) if it["published"] else None
            if pub and pub < cutoff:
                continue
            # 没有发布时间的（列表页源）用 URL 年月兜底，挡掉推荐位里的老文章
            if not pub and url_month_stale(it["source_url"]):
                stale_by_url += 1
                continue
            fresh.append(it)
        extra = f"，URL 年月判定过期 {stale_by_url} 条" if stale_by_url else ""
        print(f"  得到 {len(items)} 条，{max_age_days} 天内 {len(fresh)} 条{extra}")
        all_items.extend(fresh)

    # 去重：源内重复 + 已发布 + 历史上已看过
    deduped = []
    seen_now = set()
    for it in all_items:
        key = it["source_url"]
        if key in seen_now:
            continue
        if key in published or ("uid:" + it["uid"]) in published:
            continue
        if it["uid"] in seen:
            continue
        seen_now.add(key)
        deduped.append(it)

    # 新旧的排序：有时间在前，按时间倒序
    def sort_key(it):
        return parse_time(it["published"]) or datetime.min.replace(tzinfo=timezone.utc)

    deduped.sort(key=sort_key, reverse=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "count": len(deduped),
            "items": deduped,
        }, f, ensure_ascii=False, indent=2)

    # 注意：这里**不能**把候选标记为「已看过」。
    # 抓取阶段就标记的话，只要后续（精选/补正文/发布）中途失败，
    # 当天候选池就被永久污染，之后每天都会误报「今日无新闻」。
    # 已看过状态改由 publish.py 在**发布成功后**写入，见 publish.py:mark_candidates_seen()。

    print(f"\n共 {len(all_items)} 条原始资讯，去重后 {len(deduped)} 条候选")
    print(f"已写入: {CANDIDATES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
