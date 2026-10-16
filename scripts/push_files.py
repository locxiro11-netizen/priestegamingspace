#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_files.py — 用 GitHub contents API 把本地文件推到仓库。

为什么不用 git push：本仓库用的 fine-grained token 走 git 协议会
`invalid credentials`，但 contents API 一切正常。

用法:
    python scripts/push_files.py path1 path2 ... -m "提交信息"
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish  # noqa: E402

ROOT = publish.ROOT

with open(publish.CONFIG_PATH, "r", encoding="utf-8") as _f:
    CFG = json.load(_f)
REPO = CFG["repo"]


def put_file(rel_path, body_bytes, message, branch):
    """推单个文件。返回 True/False。"""
    api = (f"https://api.github.com/repos/{REPO['owner']}/{REPO['name']}"
           f"/contents/{rel_path}")
    token = publish.load_token()
    if not token:
        print("缺少 token", file=sys.stderr)
        return False

    # 已有文件需要带 sha 才能更新
    cur = publish.http_json(api + f"?ref={branch}", "GET", token)
    sha = cur.get("sha") if not cur.get("__error__") else None

    payload = {
        "message": message,
        "content": base64.b64encode(body_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = publish.http_json(api, "PUT", token, payload)
    if r.get("__error__"):
        print(f"  ✗ {rel_path}: {r['__error__'][:160]}", file=sys.stderr)
        if r.get("__status__") == 401:
            print("    Token 过期，去 https://github.com/settings/personal-access-tokens 重新生成",
                  file=sys.stderr)
        return False
    print(f"  ✓ {rel_path} ({len(body_bytes)} 字节) -> {r.get('commit', {}).get('sha', '')[:8]}")
    return True


def main():
    argv = sys.argv[1:]
    msg = "更新文件"
    if "-m" in argv:
        msg = argv[argv.index("-m") + 1]
    args = [a for a in argv if not a.startswith("-") and a != msg]
    if not args:
        print(__doc__)
        return 1

    branch = REPO["branch"]
    print(f"推送 {len(args)} 个文件到 {branch}（{msg}）")
    ok = True
    for rel in args:
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            print(f"  ✗ 找不到 {rel}", file=sys.stderr)
            ok = False
            continue
        with open(full, "rb") as f:
            data = f.read()
        if not put_file(rel.replace("\\", "/"), data, msg, branch):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
