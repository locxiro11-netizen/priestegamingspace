#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_curate.py — 调用大模型完成「爆点判断 + 中文重写 + 正文翻译」。

两种模式：
  默认          读 candidates.json，挑出最有爆点的几条，写出 curated.json
  --translate   读 to_translate.json，把非中文正文逐段译成中文，写出 translated.json

接口用 OpenAI 兼容的 chat/completions，默认 DeepSeek，可用环境变量覆盖：
  LLM_API_KEY    必填（也可放仓库根目录 .llm_key）
  LLM_ENDPOINT   默认 https://api.deepseek.com/chat/completions
  LLM_MODEL      默认 deepseek-chat

用法:
    python scripts/ai_curate.py
    python scripts/ai_curate.py --translate
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "scripts", "out")
CANDIDATES_PATH = os.path.join(OUT_DIR, "candidates.json")
CURATED_PATH = os.path.join(OUT_DIR, "curated.json")
TRANSLATE_TASK_PATH = os.path.join(OUT_DIR, "to_translate.json")
TRANSLATED_PATH = os.path.join(OUT_DIR, "translated.json")

ENDPOINT = os.environ.get("LLM_ENDPOINT", "https://api.deepseek.com/chat/completions")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

_SSL_OK = ssl.create_default_context()
_SSL_LOOSE = ssl.create_default_context()
_SSL_LOOSE.check_hostname = False
_SSL_LOOSE.verify_mode = ssl.CERT_NONE

PICK_MIN = int(os.environ.get("PICK_MIN", "4"))
PICK_MAX = int(os.environ.get("PICK_MAX", "6"))

SELECT_SYSTEM = """你是资深游戏资讯主编，为一个游戏自媒体站点挑选每日要闻。

判断标准只有一条：这条新闻会不会让玩家在群里讨论起来？

优先选（爆点）：
- 3A 大作的重磅公布 / 发售 / 跳票 / 取消
- 重大泄露、实机演示首曝、预告片引爆讨论
- 行业级事件：大裁员、工作室收购或关闭、高层变动、平台政策巨变
- 现象级话题：破圈争议、销量纪录、现象级爆款
- 顶级 IP 的关键动向（GTA、塞尔达、宝可梦、黑神话等）

明确排除：
- 小众独立游戏的常规消息（除非本身成了话题）
- 普通版本更新、小补丁、常规 DLC 上架
- 单纯的评分 / 评测 / 榜单 / 周报汇总
- 促销折扣、硬件降价
- 娱乐八卦、明星、手机数码
- 同一事件的多家重复报道只留信息量最大的一条

宁缺毋滥：凑不够 {pmin} 条就少发，绝不为了凑数降低标准。"""

SELECT_USER = """下面是今天的候选资讯（共 {n} 条）。请挑出 {pmin}-{pmax} 条最有爆点的。

{candidates}

输出严格的 JSON 数组，不要任何解释文字、不要 markdown 代码块，格式：
[
  {{"i": <候选编号>, "title": "<中文标题，20-28字，爆点前置>", "desc": "<中文摘要1-2句，60-120字，说清发生了什么+为什么炸>", "tags": ["标签1","标签2"], "game": "<涉及的游戏名，没有就空字符串>"}}
]

要求：
- i 必须是上面给出的编号
- 标题一律写成中文，英文原标题要翻译，不要保留英文
- 国内源优先，中文内容应占一半以上
- 如果确实没有够分量的，就少选，不要硬凑"""


def load_key():
    key = os.environ.get("LLM_API_KEY", "").strip()
    if key:
        return key
    p = os.path.join(ROOT, ".llm_key")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def chat(messages, max_tokens=4096, temperature=0.3, retries=3):
    key = load_key()
    if not key:
        raise RuntimeError(
            "缺少大模型 API Key：请设置环境变量 LLM_API_KEY，"
            "或写入 %s" % os.path.join(ROOT, ".llm_key"))

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_err = None
    for attempt in range(retries):
        for ctx in (_SSL_OK, _SSL_LOOSE):
            try:
                req = urllib.request.Request(ENDPOINT, data=data, headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                })
                with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
                    resp = json.loads(r.read().decode("utf-8"))
                return resp["choices"][0]["message"]["content"]
            except Exception as e:
                last_err = e
                continue
        if attempt < retries - 1:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("调用大模型失败: %s" % last_err)


def extract_json(text):
    """从模型回复里抠出 JSON，兼容 ```json 代码块和前后废话。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # 退一步找第一个数组
    m = re.search(r"\[.*\]", t, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------
# 模式一：精选
# --------------------------------------------------------------------------

def build_candidate_brief(items):
    lines = []
    for i, it in enumerate(items):
        desc = re.sub(r"\s+", " ", (it.get("raw_desc") or ""))[:220]
        lines.append("[%d] 来源：%s\n    标题：%s\n    摘要：%s"
                     % (i, it.get("source", ""), it.get("title", ""), desc or "（无）"))
    return "\n".join(lines)


def do_select():
    with open(CANDIDATES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        print("候选列表为空，跳过。")
        with open(CURATED_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return 0

    print("候选 %d 条，交给大模型精选 ..." % len(items))
    resp = chat([
        {"role": "system", "content": SELECT_SYSTEM.format(pmin=PICK_MIN)},
        {"role": "user", "content": SELECT_USER.format(
            n=len(items), pmin=PICK_MIN, pmax=PICK_MAX,
            candidates=build_candidate_brief(items))},
    ], max_tokens=4096)

    picks = extract_json(resp)
    if not picks:
        print("模型返回无法解析：\n%s" % (resp or "")[:500], file=sys.stderr)
        return 1

    curated, seen_idx = [], set()
    for p in picks:
        try:
            i = int(p.get("i"))
        except Exception:
            continue
        if i < 0 or i >= len(items) or i in seen_idx:
            continue
        src = items[i]
        seen_idx.add(i)
        curated.append({
            "uid": src.get("uid", ""),
            "title": (p.get("title") or src.get("title", "")).strip(),
            "desc": (p.get("desc") or "").strip(),
            "tags": p.get("tags") or [],
            "game": (p.get("game") or "").strip(),
            "image": src.get("image", ""),
            "source": src.get("source", ""),
            "source_url": src.get("source_url", ""),
            "content_encoded": src.get("content_encoded", ""),
        })

    # 兜底：模型一条都没选出来时，退回按来源取前几条，保证流程不空转
    if not curated:
        print("模型未选出任何条目，回退：取最新的 %d 条" % PICK_MIN)
        for src in items[:PICK_MIN]:
            curated.append({
                "uid": src.get("uid", ""),
                "title": src.get("title", ""),
                "desc": re.sub(r"\s+", " ", src.get("raw_desc", ""))[:120],
                "tags": [src.get("source", "")],
                "game": src.get("game", ""),
                "image": src.get("image", ""),
                "source": src.get("source", ""),
                "source_url": src.get("source_url", ""),
                "content_encoded": src.get("content_encoded", ""),
            })

    with open(CURATED_PATH, "w", encoding="utf-8") as f:
        json.dump(curated, f, ensure_ascii=False, indent=2)

    print("精选完成，共 %d 条：" % len(curated))
    for c in curated:
        print("  · [%s] %s" % (c["source"], c["title"][:48]))
    return 0


# --------------------------------------------------------------------------
# 模式二：翻译
# --------------------------------------------------------------------------

TRANSLATE_SYSTEM = """你是游戏资讯译者。把英文段落逐段译成简体中文。

铁律：
- 输出必须是严格的 JSON 数组，长度和顺序与输入完全一致，一段对一个元素
- 只翻译可见文字，<a href="...">、<strong>、<em>、<br> 等标签原样保留，
  且绝不改动 href 里的网址
- 不要合并、拆分、漏译任何一段
- 游戏名、工作室名用通用中文译法，没有通用译法就保留原文
- 译文通顺自然，不要机翻腔，不要添加原文没有的内容"""

CHUNK_CHARS = 5000


def do_translate():
    if not os.path.exists(TRANSLATE_TASK_PATH):
        print("没有待翻译内容。")
        return 0
    with open(TRANSLATE_TASK_PATH, encoding="utf-8") as f:
        task = json.load(f)
    if not task:
        print("没有待翻译内容。")
        return 0

    result = {}
    for uid, entry in task.items():
        texts = entry.get("texts") or []
        if not texts:
            continue
        print("翻译 %s（%d 段）..." % ((entry.get("title") or uid)[:40], len(texts)))

        chunks, cur, cur_len = [], [], 0
        for t in texts:
            if cur_len + len(t) > CHUNK_CHARS and cur:
                chunks.append(cur)
                cur, cur_len = [], 0
            cur.append(t)
            cur_len += len(t)
        if cur:
            chunks.append(cur)

        translated = []
        offset = 0
        for ci, chunk in enumerate(chunks):
            payload = json.dumps(chunk, ensure_ascii=False)
            resp = chat([
                {"role": "system", "content": TRANSLATE_SYSTEM},
                {"role": "user", "content":
                    "共 %d 段（第 %d/%d 批）。严格按同样顺序输出 JSON 数组：\n%s"
                    % (len(texts), ci + 1, len(chunks), payload)},
            ], max_tokens=8192, temperature=0.2)
            arr = extract_json(resp)
            if not arr or len(arr) != len(chunk):
                print("  ! 第 %d 批返回长度不符（期望 %d，实际 %s），该批保留原文"
                      % (ci + 1, len(chunk), len(arr) if arr else "无法解析"), file=sys.stderr)
                arr = chunk
            translated.extend(arr)
            offset += len(chunk)

        if len(translated) != len(texts):
            print("  ! 译文总数对不上，保留原文", file=sys.stderr)
            translated = texts
        result[uid] = translated

    with open(TRANSLATED_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("译文已写入 %s（%d 篇）" % (TRANSLATED_PATH, len(result)))
    return 0


def main():
    mode = "--translate" if "--translate" in sys.argv[1:] else "--select"
    try:
        return do_translate() if mode == "--translate" else do_select()
    except RuntimeError as e:
        # 缺 Key、接口调不通这类问题直接讲清楚，别甩一屏堆栈
        print("错误：%s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
