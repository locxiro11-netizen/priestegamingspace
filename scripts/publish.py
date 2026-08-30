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
    python scripts/publish.py --repair             # 重新提取已发布但内容有问题的条目
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
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

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
    # 统一用北京时间打戳（本地跑和 GitHub Actions UTC 跑都一致）
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M")


def push_content(api, token, sha, content, message, branch, dry_run):
    """把整个 content.json 推回 GitHub。返回 True 成功 / False 失败 / None 未推送。"""
    body = json.dumps(content, ensure_ascii=False, indent=2)
    if dry_run:
        print("\n[dry-run] 未推送。")
        return None
    if not token:
        print(f"\n缺少 GitHub Token：请设置 GITHUB_TOKEN 或写入 {TOKEN_FILE}",
              file=sys.stderr)
        return False

    payload = {
        "message": message,
        "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    print("\n推送到 GitHub ...")
    result = http_json(api, "PUT", token, payload)
    if result.get("__error__"):
        print(f"推送失败: {result['__error__']}", file=sys.stderr)
        if result.get("__status__") == 401:
            print("\nToken 已过期或被撤销。请到 "
                  "https://github.com/settings/personal-access-tokens "
                  f"重新生成，并更新 {TOKEN_FILE}", file=sys.stderr)
        return False
    print(f"提交: {result.get('commit', {}).get('sha', '')[:8]}")
    return True


def mark_candidates_seen():
    """发布成功后，把本轮抓到的全部候选标记为「已看过」。

    放在发布成功之后（而不是抓取阶段）是刻意的：一轮流程只有真正走完，
    才说明这批候选已被评估过；中途失败时候选池保持干净，下次还能重新评估。
    """
    cand_path = os.path.join(ROOT, "scripts", "out", "candidates.json")
    if not os.path.exists(cand_path):
        return
    try:
        with open(cand_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        uids = [i["uid"] for i in data.get("items", []) if i.get("uid")]
        if not uids:
            return
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import fetch_news
        fetch_news.save_seen(uids)
        print(f"已把 {len(uids)} 条候选标记为「已看过」")
    except Exception as e:
        # 标记失败不影响发布结果，只是下次会重复评估
        print(f"  ! 标记已看过失败（不影响发布）: {e}", file=sys.stderr)


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

    fill_mode = "--fill-content" in sys.argv[1:]
    curated = []
    if not fill_mode:
        with open(input_path, "r", encoding="utf-8") as f:
            curated = json.load(f)
        if isinstance(curated, dict):
            curated = curated.get("items", [])
        if not isinstance(curated, list):
            print("curated.json 格式不对，应为数组", file=sys.stderr)
            return 1
        if not curated:
            # 「今天没有够分量的新闻」是正常结果，不该让定时任务报错
            print("今日无可发布内容（精选结果为空）")
            return 0

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

    # --fill-content：给已发布但缺正文的条目补齐全文和视频（不新增条目）
    if fill_mode:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        try:
            import enrich
        except Exception as e:
            print(f"无法导入 enrich.py: {e}", file=sys.stderr)
            return 1

        targets = [i for i in content["news"]
                   if i.get("source_url") and not i.get("content_html")]
        print(f"待补全正文：{len(targets)} 条")
        filled = 0
        for it in targets:
            try:
                blocks, cover = enrich.blocks_for(it)
            except Exception as e:
                print(f"  ! {(it.get('title') or '')[:30]} 提取异常: {e}", file=sys.stderr)
                blocks, cover = [], ""
            if not blocks:
                print(f"  ✗ {(it.get('title') or '')[:30]} 未取到正文")
                continue
            it["content_html"] = enrich.blocks_to_html(blocks)
            v = enrich.first_video(blocks)
            if v:
                it["video"] = v
            if not (it.get("image") or "").strip():
                it["image"] = enrich.first_image(blocks) or cover
            print(f"  ✓ {(it.get('title') or '')[:30]} "
                  f"{len(it['content_html'])}字{' 含视频' if v else ''}")
            filled += 1
            time.sleep(0.6)

        if not filled:
            print("没有补全任何条目，无需推送。")
            return 0

        ok = push_content(api, token, sha, content,
                          f"📄 补全资讯正文 {filled} 条 - {now_str()}",
                          repo["branch"], dry_run)
        if ok is False:
            return 1
        if ok:
            print(f"推送成功！补全 {filled} 条正文。")
        return 0

    # --repair：正文/封面被广告图或尾部推荐位污染时，用修复后的逻辑重新提取。
    # 典型场景：enrich 修好之后，之前已发布的条目仍是脏的，需要回刷一遍。
    if "--repair" in sys.argv[1:]:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        try:
            import enrich
        except Exception as e:
            print(f"无法导入 enrich.py: {e}", file=sys.stderr)
            return 1

        targets = [i for i in content["news"]
                   if i.get("source_url") and enrich.content_is_dirty(i)]
        print(f"待修复：{len(targets)} 条")
        for t in targets:
            print(f"  · [{t.get('source') or '?'}] {t.get('title')}")

        fixed = 0
        for it in targets:
            try:
                blocks, cover = enrich.blocks_for(it)
            except Exception as e:
                print(f"  ! {(it.get('title') or '')[:30]} 提取异常: {e}",
                      file=sys.stderr)
                continue
            if not blocks:
                print(f"  ✗ {(it.get('title') or '')[:30]} 重新提取失败，保留原文")
                continue
            it["content_html"] = enrich.blocks_to_html(blocks)
            v = enrich.first_video(blocks)
            if v:
                it["video"] = v
            # 封面若是广告图，换成正文首图或页头 meta 封面
            cur_img = (it.get("image") or "").strip()
            if not cur_img or enrich._AD_IMAGE.search(cur_img):
                it["image"] = enrich.first_image(blocks) or cover
            print(f"  ✓ {(it.get('title') or '')[:30]} "
                  f"{len(it['content_html'])}字 图：{(it.get('image') or '无')[:52]}")
            fixed += 1
            time.sleep(0.6)

        if not fixed:
            print("没有修复任何条目，无需推送。")
            return 0

        ok = push_content(api, token, sha, content,
                          f"🧹 修复资讯正文 {fixed} 条 - {now_str()}",
                          repo["branch"], dry_run)
        if ok is False:
            return 1
        if ok:
            print(f"推送成功！修复 {fixed} 条。")
        return 0

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
        # 正文全文与视频由 enrich.py 补齐，供详情页展示
        if item.get("content_html"):
            entry["content_html"] = item["content_html"]
        if item.get("video"):
            entry["video"] = item["video"]
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

    ok = push_content(api, token, sha, content,
                      f"📰 自动发布游戏资讯 {len(added)} 条 - {now_str()}",
                      repo["branch"], dry_run)
    if ok is False:
        return 1

    print(f"推送成功！共新增 {len(added)} 条资讯。")
    mark_candidates_seen()
    print("GitHub Actions 会自动部署，约 1-2 分钟后可见：")
    print("https://locxiro11-netizen.github.io/priestegamingspace/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
