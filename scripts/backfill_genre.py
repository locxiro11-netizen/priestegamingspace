#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_genre.py — 给已发布的历史资讯补上分类（3A / 独立游戏 / 综合）。

新发布的条目由大模型在精选时直接打标，但之前发的条目没有 genre 字段，
前端两个子页签一上线会是空的。跑一次这个脚本把存量补齐。

判定优先用规则（scripts/genre.py），不调用大模型：
存量条目动辄上百条，规则足够，也不想为回填再烧一轮额度。

用法:
    python scripts/backfill_genre.py                # 回填并推送
    python scripts/backfill_genre.py --dry-run      # 只看会改成什么，不推送
    python scripts/backfill_genre.py --force        # 连已有合法分类的也重判一遍
    python scripts/backfill_genre.py --recheck-indie  # 只复查被打成「独立游戏」的条目

--recheck-indie 用于收紧口径后的纠偏：全量 --force 会用规则覆盖模型判断，
而规则比模型粗糙，容易把判对的独立游戏误伤成综合。这里只在命中「其实不是
独立游戏」的黑名单时才改判，其余一律保留原判断。

Token 来源同 publish.py：环境变量 GITHUB_TOKEN 或仓库根目录 .gh_token
"""

import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import genre
import publish

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "scripts", "config.json")


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    force = "--force" in sys.argv[1:]
    recheck = "--recheck-indie" in sys.argv[1:]

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

    changed, counts = [], {}
    for it in news:
        old = it.get("genre")
        oldn = genre.normalize_genre(old)
        # --force 之外，已经是合法分类的就别动了，避免把模型判断过的又改回去
        if not force and oldn in genre.VALID_GENRES:
            # 只在黑名单命中时才改判，其余保留模型判断
            if recheck and oldn == "indie" and genre.not_indie_hit(it):
                g = genre.infer_genre(it)
            else:
                g = oldn
        else:
            g = genre.infer_genre(it)
        counts[g] = counts.get(g, 0) + 1
        if g != old:
            it["genre"] = g
            changed.append((old, g, it.get("title") or ""))

    print("\n分类结果：")
    for k in genre.VALID_GENRES:
        print(f"  {genre.GENRE_LABELS[k]:<6} {counts.get(k, 0)} 条")

    if not changed:
        print("\n没有需要回填的条目。")
        return 0

    print(f"\n将修改 {len(changed)} 条：")
    for old, g, title in changed[:25]:
        print(f"  {genre.GENRE_LABELS.get(old, old or '无'):<6} → "
              f"{genre.GENRE_LABELS[g]:<6} {title[:44]}")
    if len(changed) > 25:
        print(f"  ... 另有 {len(changed) - 25} 条")

    ok = publish.push_content(
        api, token, remote.get("sha"), content,
        f"🏷️ 回填资讯分类 {len(changed)} 条（3A / 独立游戏 / 综合）- {publish.now_str()}",
        repo["branch"], dry_run)
    if ok is False:
        return 1
    if ok:
        print(f"推送成功！回填 {len(changed)} 条，约 1-2 分钟后可见。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
