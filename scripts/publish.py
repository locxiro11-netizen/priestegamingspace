#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish.py — 把精选好的资讯写入 website/data/content.json 并推送到 GitHub。

输入文件（默认 scripts/out/curated.json）是一个数组：
[
  {
    "title":      "中文标题",
    "desc":       "中文摘要，一两句说清重点",
    "tags":       ["GTA6", "Rockstar"],
    "image":      "https://... 配图地址，可为空",
    "game":       "涉及的游戏名，可为空",
    "source":     "机核",
    "source_url": "https://... 原文地址（用于去重，必填）"
  }
]

用法:
    python scripts/publish.py                      # 正常发布
    python scripts/publish.py --dry-run            # 只预览合并结果，不推送
    python scripts/publish.py path/to/file.json    # 指定输入文件

Token 来源（二选一）:
    1. 环境变量 GITHUB_TOKEN
    2. 仓库根目录的 .gh_token 文件（纯文本一行，已加入 .gitignore）
"""

import base64
import json
import os
import sys
import ssl
import urllib.request
import urllib.error
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "scripts", "config.json")
DEFAULT_INPUT = os.path.join(ROOT, "scripts", "out", "curated.json")
TOKEN_FILE = os.path.join(ROOT, ".gh_token")

CATS = ["news", "gameUI", "screenshots", "reflections", "life"]

_SSL_OK = ssl.create_default_context()
_SSL_LOOSE = ssl.create_default_context()
_SSL_LOOSE.check_hostname = False
_SSL_LOOSE.verify_mode = ssl.CERT_NONE


def http_json(url, method="GET", token=None, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "User-Agent": "PriesteGamingSpace-NewsBot",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if data:
        headers["Content-Type"] = "application/json; charset=utf-8"

    last_err = None
    for ctx in (_SSL_OK, _SSL_LOOSE):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}"
            return {"__error__": last_err, "__status__": e.code}
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
    return {"__error__": last_err}


def load_token():
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            tok = f.read().strip()
    return tok


def now_str():
    return datetime.now().strftime("%Y/%m/%d %H:%M")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv[1:]
    input_path = args[0] if args else DEFAULT_INPUT

    if not os.path.exists(input_path):
        print(f"找不到输入文件: {input_path}", file=sys.stderr)
        return 1

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    repo = cfg["repo"]

    with open(input_path, "r", encoding="utf-8") as f:
        curated = json.load(f)
    if isinstance(curated, dict):
        curated = curated.get("items", [])
    if not isinstance(curated, list) or not curated:
        print("精选列表为空，没有可发布的内容", file=sys.stderr)
        return 1

    api = (f"https://api.github.com/repos/{repo['owner']}/{repo['name']}"
           f"/contents/{repo['content_path']}")
    token = load_token()

    # 拉取线上最新内容（不推 token 也能读，公共仓库）
    print("读取线上 content.json ...")
    remote = http_json(api + f"?ref={repo['branch']}", "GET", token)
    if remote.get("__error__"):
        print(f"读取失败: {remote['__error__']}", file=sys.stderr)
        return 1

    sha = remote.get("sha")
    try:
        content = json.loads(base64.b64decode(remote["content"]).decode("utf-8"))
    except Exception as e:
        print(f"线上 content.json 解析失败: {e}", file=sys.stderr)
        return 1

    for cat in CATS:
        content.setdefault(cat, [])

    existing_urls = {i.get("source_url") for i in content["news"] if i.get("source_url")}
    existing_ids = {i.get("id") for i in content["news"]}

    added, skipped = [], []
    for item in curated:
        url = (item.get("source_url") or "").strip()
        title = (item.get("title") or "").strip()
        if not title:
            skipped.append("(缺少标题，已跳过)")
            continue
        if url and url in existing_urls:
            skipped.append(f"{title}（已发布过）")
            continue

        new_id = "news-" + (item.get("uid") or str(abs(hash(url or title)) % 10**10))
        if new_id in existing_ids:
            skipped.append(f"{title}（ID 重复）")
            continue

        entry = {
            "id": new_id,
            "date": now_str(),
            "title": title,
            "desc": (item.get("desc") or "").strip(),
            "tags": item.get("tags") or [],
            "image": (item.get("image") or "").strip(),
            "game": (item.get("game") or "").strip(),
            "source": (item.get("source") or "").strip(),
            "source_url": url,
            "likes": 0,
        }
        content["news"].append(entry)
        existing_ids.add(new_id)
        if url:
            existing_urls.add(url)
        added.append(entry)

    if not added:
        print("没有新增内容，无需推送。")
        for s in skipped:
            print("  -", s)
        return 0

    # 按时间倒序，并限制总条数
    content["news"].sort(key=lambda i: i.get("date", ""), reverse=True)
    max_keep = cfg.get("max_keep", 300)
    if len(content["news"]) > max_keep:
        content["news"] = content["news"][:max_keep]

    body = json.dumps(content, ensure_ascii=False, indent=2)

    print(f"\n准备发布 {len(added)} 条：")
    for e in added:
        print(f"  · [{e['source'] or '未标注'}] {e['title']}")
    if skipped:
        print(f"\n跳过 {len(skipped)} 条：")
        for s in skipped:
            print(f"  · {s}")

    if dry_run:
        print("\n[dry-run] 未推送，合并后的 news 数组预览：")
        print(json.dumps(content["news"][:len(added)], ensure_ascii=False, indent=2))
        return 0

    if not token:
        print("\n缺少 GitHub Token：请设置环境变量 GITHUB_TOKEN，"
              f"或把 Token 写入 {TOKEN_FILE}", file=sys.stderr)
        return 1

    payload = {
        "message": f"📰 自动发布游戏资讯 {len(added)} 条 - {now_str()}",
        "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
        "branch": repo["branch"],
    }
    if sha:
        payload["sha"] = sha

    print("\n推送到 GitHub ...")
    result = http_json(api, "PUT", token, payload)
    if result.get("__error__"):
        print(f"推送失败: {result['__error__']}", file=sys.stderr)
        return 1

    print(f"推送成功！共新增 {len(added)} 条资讯。")
    print(f"提交: {result.get('commit', {}).get('sha', '')[:8]}")
    print("GitHub Actions 会自动部署，约 1-2 分钟后可见：")
    print("https://locxiro11-netizen.github.io/priestegamingspace/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
