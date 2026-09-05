#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_cover.py — 把已发布资讯的封面图从缩略图换成大图。

新条目由 enrich.py / publish.py 走 cover.py 自动升级，但存量条目的 image 字段
还是源站给的缩略图 URL。这个脚本负责把存量也换掉，并把能推断出的原图尺寸补上。

两种模式：
    默认            纯字符串替换，不联网，几秒钟跑完
    --refetch       对「换参数也救不回来」的小图（3DM thumbnews、游民星空
                    new_preview 之类），回文章页重新抓 og:image 顶掉
                    ——要联网，每条慢 1-2 秒

用法:
    python scripts/backfill_cover.py                 # 替换 + 推送
    python scripts/backfill_cover.py --dry-run       # 只看会改成什么
    python scripts/backfill_cover.py --refetch       # 连小缩略图一起回源重抓

Token 来源同 publish.py：环境变量 GITHUB_TOKEN 或仓库根目录 .gh_token
"""

import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cover
import enrich
import publish

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "scripts", "config.json")


def refetch_cover(item):
    """回文章页重新抓封面图。抓不到返回空字符串。

    只用于「URL 上没有放大参数、只能回源」的缩略图，默认不跑——要联网。
    """
    url = (item.get("source_url") or "").strip()
    if not url:
        return ""
    try:
        _, page_cover = enrich.blocks_for(item)
    except Exception as e:
        print(f"    ! 回源异常: {type(e).__name__}: {e}", file=sys.stderr)
        return ""
    try:
        blocks = enrich.blocks_for(item)[0]
    except Exception:
        blocks = []
    # 正文首图和 og:image 都试，谁大用谁：3DM 的 og:image 本身就是
    # 缩略图，只有正文首图是 1080 宽的大图
    picked, _ = cover.pick_bigger(
        item.get("image") or "",
        [enrich.first_image(blocks), page_cover])
    if not picked:
        return ""
    big, w, h = cover.cover_fields(picked)
    item["image"] = big
    if w:
        item["image_w"], item["image_h"] = w, h
    return big


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    refetch = "--refetch" in sys.argv[1:]

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    repo = cfg["repo"]
    api = (f"https://api.github.com/repos/{repo['owner']}/{repo['name']}"
           f"/contents/{repo['content_path']}")

    token = publish.load_token()
    print("读取线上 content.json ...")
    remote = publish.http_json(api + f"?ref={repo['branch']}", "GET", token)
    if remote.get("__error__"):
        print(f"读取失败: {remote['__error__']}", file=sys.stderr)
        return 1
    try:
        content = json.loads(base64.b64decode(remote["content"]).decode("utf-8"))
    except Exception as e:
        print(f"content.json 解析失败: {e}", file=sys.stderr)
        return 1

    news = content.get("news") or []
    print(f"共 {len(news)} 条资讯")

    changed, upgraded, refetched = [], 0, 0
    for it in news:
        old = (it.get("image") or "").strip()
        if not old:
            continue
        new, w, h = cover.cover_fields(old)
        if new != old:
            it["image"] = new
            upgraded += 1
        if w and not it.get("image_w"):
            it["image_w"], it["image_h"] = w, h

        # 换参数没救的缩略图：回文章页重新抓
        if refetch and cover.is_thumb_only(it["image"]):
            title = (it.get("title") or "")[:30]
            print(f"  回源重抓 {title}")
            got = refetch_cover(it)
            if got:
                refetched += 1
                print(f"    → {got[:88]}")
            time.sleep(0.6)

        if it.get("image") != old:
            changed.append((old, it.get("image") or ""))

    print(f"\n换大图 {upgraded} 条"
          + (f"，回源重抓 {refetched} 条" if refetch else "")
          + f"，共 {len(changed)} 条 URL 变化")

    for old, new in changed[:20]:
        print(f"  {old[:70]}\n  → {new[:70]}")
    if len(changed) > 20:
        print(f"  ... 另有 {len(changed) - 20} 条")

    if not changed:
        print("\n没有需要替换的封面图。")
        return 0

    ok = publish.push_content(
        api, token, remote.get("sha"), content,
        f"🖼️ 封面图换大图 {len(changed)} 张 - {publish.now_str()}",
        repo["branch"], dry_run)
    if ok is False:
        return 1
    if ok:
        print(f"推送成功！替换 {len(changed)} 张封面图，约 1-2 分钟后可见。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
