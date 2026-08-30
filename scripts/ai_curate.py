#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_curate.py — 调用大模型完成「爆点判断 + 中文重写 + 正文翻译」。

两种模式：
  默认          读 candidates.json，挑出最有爆点的几条，写出 curated.json
  --translate   读 to_translate.json，把非中文正文逐段译成中文，写出 translated.json

接口用 OpenAI 兼容的 chat/completions，默认智谱 GLM，可用环境变量覆盖：
  LLM_API_KEY    必填（也可放仓库根目录 .llm_key）
  LLM_ENDPOINT   默认 https://open.bigmodel.cn/api/paas/v4/chat/completions
  LLM_MODEL      默认 glm-4-flash（智谱免费模型）

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
UNTRANSLATED_PATH = os.path.join(OUT_DIR, "untranslated.json")

ENDPOINT = os.environ.get("LLM_ENDPOINT", "").strip() or "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("LLM_MODEL", "").strip() or "glm-4-flash"

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


CN_SOURCES = {"机核", "游民星空", "3DM"}


def _title_grams(title, n=3):
    """标题归一化后取字符 n-gram 集合，用于跨源撞题检测。"""
    t = re.sub(r"[《》「』「『\"'：:，,。.!！?？\-—_\s\[\]（）()]", "", (title or "").lower())
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def dedupe_curated(curated):
    """同一事件的多源报道只留一条（模型的漏网之鱼在这里兜底）。
    保留优先级：国内源 > 模型排序靠前。"""
    kept = []
    for c in curated:
        g = _title_grams(c.get("title"))
        dup_of = None
        for k in kept:
            kg = _title_grams(k.get("title"))
            if not g or not kg:
                continue
            inter = len(g & kg)
            union = len(g | kg)
            if union and inter / union >= 0.45:
                dup_of = k
                break
        if dup_of is None:
            kept.append(c)
            continue
        # 撞题：国内源顶替国外源，否则保留先来的（模型眼里更重要的）
        if c.get("source") in CN_SOURCES and dup_of.get("source") not in CN_SOURCES:
            print("  ~ 去重：[%s] 顶替 [%s]《%s》"
                  % (c["source"], dup_of["source"], (dup_of.get("title") or "")[:30]))
            kept[kept.index(dup_of)] = c
        else:
            print("  ~ 去重：丢弃 [%s]《%s》（与 [%s] 撞题）"
                  % (c["source"], (c.get("title") or "")[:30], dup_of["source"]))
    return kept


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

    curated = dedupe_curated(curated)

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


def translate_chunk(chunk, total, ci, nchunks, depth=0):
    """翻译一批段落。返回译文列表；长度对不上时递归拆半重试，
    拆到单段仍失败才放弃（返回 None，由调用方决定保留原文）。"""
    payload = json.dumps(chunk, ensure_ascii=False)
    resp = chat([
        {"role": "system", "content": TRANSLATE_SYSTEM},
        {"role": "user", "content":
            "共 %d 段（第 %d/%d 批）。严格按同样顺序输出 JSON 数组：\n%s"
            % (total, ci + 1, nchunks, payload)},
    ], max_tokens=8192, temperature=0.2)
    arr = extract_json(resp)
    if arr and len(arr) == len(chunk):
        # 长度对但模型偶尔返回嵌套数组/对象，逐元素校验并尽量修复
        fixed = []
        for a in arr:
            if isinstance(a, str):
                fixed.append(a)
            elif isinstance(a, list) and a and isinstance(a[0], str):
                fixed.append(a[0])
            else:
                fixed = None
                break
        if fixed is not None:
            return fixed
    # 长度不符：拆半重试（最多拆到单段）
    if len(chunk) > 1 and depth < 4:
        print("  ! 第 %d 批返回长度不符（期望 %d，实际 %s），拆半重试"
              % (ci + 1, len(chunk), len(arr) if arr else "无法解析"), file=sys.stderr)
        mid = len(chunk) // 2
        left = translate_chunk(chunk[:mid], total, ci, nchunks, depth + 1)
        right = translate_chunk(chunk[mid:], total, ci, nchunks, depth + 1)
        if left is not None and right is not None:
            return left + right
        return None
    print("  ! 单段翻译仍无法对齐，保留原文: %s..." % chunk[0][:40], file=sys.stderr)
    return None


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
    untranslated_uids = []
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
        failed = False
        for ci, chunk in enumerate(chunks):
            arr = translate_chunk(chunk, len(texts), ci, len(chunks))
            if arr is None:
                failed = True
                arr = chunk  # 该批保留原文
            translated.extend(arr)

        if len(translated) != len(texts):
            print("  ! 译文总数对不上，保留原文", file=sys.stderr)
            translated = texts
            failed = True
        if failed:
            untranslated_uids.append(uid)
        result[uid] = translated

    with open(TRANSLATED_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("译文已写入 %s（%d 篇）" % (TRANSLATED_PATH, len(result)))
    # 翻译失败的篇目记入黑名单，回填阶段直接剔除，绝不发布英文原文
    with open(UNTRANSLATED_PATH, "w", encoding="utf-8") as f:
        json.dump(untranslated_uids, f, ensure_ascii=False)
    if untranslated_uids:
        print("注意：%d 篇正文翻译失败，将在回填阶段被剔除（不会发布英文原文）"
              % len(untranslated_uids), file=sys.stderr)
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
