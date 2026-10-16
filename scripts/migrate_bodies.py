#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_bodies.py — 一次性迁移：把 content.json 里的正文抽到按月分片。

背景：正文原本全量塞在 content.json 里，文件涨到 1MB 后触发 GitHub contents API
的读取限制（>1MB 不返回 content），publish.py 解析失败、CI 中断，直接导致
2026-09-20 ~ 10-15 断更 26 天。

迁移后：
    website/data/content.json       只留元数据（无 content_html，有 body:true）
    website/data/news/YYYY-MM.json  按月份存正文，详情页按需 fetch

用法:
    python scripts/migrate_bodies.py            # 只写本地文件
    python scripts/migrate_bodies.py --dry-run  # 只统计，不落盘
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish  # noqa: E402

ROOT = publish.ROOT
CONTENT_PATH = os.path.join(ROOT, "website", "data", "content.json")
BODY_DIR = os.path.join(ROOT, "website", "data", "news")


def main():
    dry = "--dry-run" in sys.argv[1:]

    with open(os.path.join(ROOT, "scripts", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    max_keep = cfg.get("max_keep", 150)

    with open(CONTENT_PATH, encoding="utf-8") as f:
        content = json.load(f)

    news = content.get("news", [])
    before_bytes = os.path.getsize(CONTENT_PATH)
    print(f"当前：{len(news)} 条 / {before_bytes/1024:.0f} KB")

    # 按时间倒序，先裁剪再抽正文——被裁掉的条目不写进分片，省得留孤儿
    news.sort(key=lambda i: i.get("date", ""), reverse=True)
    dropped = max(0, len(news) - max_keep)
    if dropped:
        news = news[:max_keep]
    print(f"裁剪到 max_keep={max_keep}，丢弃最旧的 {dropped} 条")

    shards = {}
    moved = 0
    for item in news:
        html = item.get("content_html")
        if not html:
            item.pop("body", None)
            continue
        month = publish.month_of(item.get("date", ""))
        if not month or len(month) != 7:
            # 日期异常就退回全量内联，别让正文丢失
            item["content_html"] = html
            continue
        shards.setdefault(month, {})[item["id"]] = {"content_html": html}
        item.pop("content_html", None)
        item["body"] = True
        moved += 1

    content["news"] = news
    body = json.dumps(content, ensure_ascii=False, indent=2)
    after_bytes = len(body.encode("utf-8"))

    print(f"\n抽出正文 {moved} 条 -> {len(shards)} 个分片")
    for month in sorted(shards):
        size = len(json.dumps(shards[month], ensure_ascii=False).encode("utf-8"))
        print(f"  · {publish.shard_path(month)}  {len(shards[month])} 条 / {size/1024:.0f} KB")
    print(f"\ncontent.json: {before_bytes/1024:.0f} KB -> {after_bytes/1024:.0f} KB "
          f"（-{100*(1-after_bytes/before_bytes):.0f}%）")

    if dry:
        print("\n[dry-run] 未落盘。")
        return 0

    os.makedirs(BODY_DIR, exist_ok=True)
    for month, data in shards.items():
        p = os.path.join(BODY_DIR, month + ".json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(f"  写入 {publish.shard_path(month)}")

    with open(CONTENT_PATH, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"  写入 website/data/content.json（{len(news)} 条）")
    print("\n接下来用 scripts/push_files.py 推送这些文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
