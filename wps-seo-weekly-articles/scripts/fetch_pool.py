#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · 素材采集脚本
================================
抓取 WPS SEO 内容资源池（金山多维表「WPS资源池」，file_id 见 DEFAULT_FILE_ID），
并为本周选题关键词匹配素材文章。数据源默认走金山多维表（wps_docs CLI），
资源池不可达时可回退到 --pool-url 指定的 JSON 地址。

匹配逻辑（按相关性打分）：
    3 分 = targetKeywords 与关键词命中（相等 / 互相包含）
    2 分 = 文章标题包含关键词（或关键词包含于标题）
    1 分 = 文章的 pool/cmsTab 命中该策略组别的映射范围
素材来源字段（sourceType）：WPS 社区 / WPS 官方公众号 / WPS 学堂 / WPS 客服中心 / 小绿书素材

用法示例：
    python fetch_pool.py                                  # 抓取多维表+全部关键词匹配（从最近选题清单）
    python fetch_pool.py --kw-file 第3周选题.md            # 指定选题清单
    python fetch_pool.py --keywords "wps下载,PDF转Word"     # 直接给关键词
    python fetch_pool.py --cache ./pool.json --refresh     # 强制刷新本地缓存
    python fetch_pool.py --out 素材匹配.md
    python fetch_pool.py --pool-url https://xxx/articles_data.json   # 资源池回退地址
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

# ============ 数据源：金山多维表（默认） ============
DEFAULT_FILE_ID = "Rip7ZFJaJrM9wK93jQop1xyuEZfz4y28u"   # 金山多维表「WPS资源池」
DEFAULT_SHEET_ID = "1"

# ============ 回退数据源：JSON 地址（可选） ============
DEFAULT_POOL_URL = ""      # 留空表示默认不使用 URL 源；需回退时用 --pool-url 指定
DEFAULT_DATA_PATH = "articles_data.json"

# 10 策略组别 -> (可命中的 pool 集合, 可命中的 cmsTab 集合)
GROUP_POOL_MAP = {
    "下载安装": (set(), set()),          # 无 pool 直接对应：靠关键词全文 + 网络搜索官方下载页
    "价格购买": ({"办公选型"}, set()),
    "对比选择": ({"竞品对比", "办公选型"}, set()),
    "模板获取": (set(), set()),          # 靠关键词（含“模板”字样）匹配
    "格式转换": ({"功能教程"}, {"PDF"}),
    "故障解决": ({"功能教程"}, set()),   # 结合 sourceType=WPS 客服中心 强化
    "教程操作": ({"功能教程"}, {"Excel", "Word", "PPT", "在线文档", "office"}),
    "功能认知": ({"功能教程"}, {"WPS教程"}),
    "AI认知": ({"AI教程"}, {"WPS AI"}),
    "品牌直达": (set(), set()),          # 靠关键词（品牌词）匹配
}

# 故障解决组在资源池中优先看客服中心素材
FAQ_SOURCE_TYPES = {"WPS 客服中心"}


def find_wps_cli():
    """定位 wps_docs_cli.py：环境变量 > 常见安装路径。找不到返回 None。"""
    env = os.environ.get("WPS_DOCS_CLI")
    if env and os.path.isfile(env):
        return env
    cands = [
        os.path.join(os.path.expanduser("~"), "skills", "wps-docs", "scripts", "wps_docs_cli.py"),
        "/home/lingxi/skills/wps-docs/scripts/wps_docs_cli.py",
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def fetch_from_dbsheet(file_id, sheet_id, cli, timeout=60):
    """通过 wps_docs CLI 分页拉取金山多维表全部记录，转换为文章列表。"""
    if not cli:
        return None
    args_base = ["dbsheet", "list-records", "--file-id", file_id, "--sheet-id", sheet_id,
                 "--fields", "文章ID,标题,素材池,CMS栏目,优先级,素材来源,原始链接,目标关键词,备注,素材生产时间,收录时间",
                 "--page-size", "1000"]
    arts = []
    token = ""
    while True:
        args = [sys.executable, cli] + args_base
        if token:
            # 用等号形式传 token：token 可能以连字符开头（如 -z），会被 argparse 误判为选项
            args += [f"--page-token={token}"]
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            d = json.loads(r.stdout)
        except Exception as e:
            print(f"[重试] 拉取多维表失败：{e}", file=sys.stderr)
            time.sleep(2)
            break
        if not d.get("success"):
            print(f"[错误] 多维表拉取失败：{d.get('error')}", file=sys.stderr)
            break
        recs = d["data"]["records"]
        for rec in recs:
            f = rec.get("fields", {})
            tks = f.get("目标关键词") or ""
            tks = [t.strip() for t in str(tks).split(";") if t.strip()] if isinstance(tks, str) else list(tks or [])
            arts.append({
                "id": f.get("文章ID", ""),
                "title": f.get("标题", ""),
                "pool": f.get("素材池", ""),
                "cmsTab": f.get("CMS栏目", ""),
                "priority": f.get("优先级", ""),
                "sourceType": f.get("素材来源", ""),
                "sourceUrl": f.get("原始链接", ""),
                "targetKeywords": tks,
                "notes": f.get("备注", ""),
                "sourceDate": (f.get("素材生产时间") or "").replace("/", "-"),
                "collectedDate": (f.get("收录时间") or "").replace("/", "-"),
            })
        token = d["data"].get("page_token", "")
        if not token:
            break
    return arts


def fetch_pool(file_id=DEFAULT_FILE_ID, sheet_id=DEFAULT_SHEET_ID, url=DEFAULT_POOL_URL,
               data_path=DEFAULT_DATA_PATH, timeout=30, retries=2, cache=None, refresh=False):
    """抓取资源池：优先金山多维表，回退 JSON URL。返回文章列表。"""
    if cache and os.path.isfile(cache) and not refresh:
        with open(cache, "r", encoding="utf-8") as f:
            arts = json.load(f)
        print(f"[缓存] 读取本地资源池缓存：{cache}（{len(arts)} 篇）", file=sys.stderr)
        return arts

    arts = None
    # 1) 金山多维表（默认数据源）
    cli = find_wps_cli()
    if cli:
        arts = fetch_from_dbsheet(file_id, sheet_id, cli)
        if arts:
            print(f"[数据] 已从金山多维表拉取 {len(arts)} 篇", file=sys.stderr)
    else:
        print("[提示] 未找到 wps_docs CLI，回退到 --pool-url 数据源", file=sys.stderr)

    # 2) 回退：JSON URL
    if not arts and url:
        import requests
        base = url.rstrip("/")
        full = f"{base}/{data_path}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/146.0 Safari/537.36"}
        last_err = None
        for attempt in range(1, retries + 2):
            try:
                r = requests.get(full, headers=headers, timeout=timeout)
                r.raise_for_status()
                arts = r.json()
                if not isinstance(arts, list):
                    raise ValueError("返回内容不是文章列表 JSON")
                break
            except Exception as e:
                last_err = e
                print(f"[重试 {attempt}] 抓取 {full} 失败：{e}", file=sys.stderr)
                time.sleep(2)
        if not arts:
            sys.exit(f"[错误] 资源池抓取失败：{last_err}\n请检查网络、wps_docs CLI 配置或改用 --pool-url 指定可达地址；"
                     f"不可达时本脚本自动降级（素材仅依赖词库+网络搜索）。")

    if not arts:
        sys.exit("[错误] 未获取到资源池数据：既未找到 wps_docs CLI，也未提供 --pool-url。")

    if cache:
        os.makedirs(os.path.dirname(os.path.abspath(cache)) or ".", exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(arts, f, ensure_ascii=False, indent=1)
        print(f"[缓存] 已保存资源池缓存：{cache}（{len(arts)} 篇）", file=sys.stderr)
    return arts


def normalize(s):
    return (s or "").strip().lower().replace(" ", "").replace("，", ",")

BRAND_WORDS = ["wps", "word", "office", "excel", "ppt", "pdf", "wps文字", "wps表格", "wps演示", "wps文档"]
QUEST_WORDS = ["怎么", "如何", "怎样", "为什么", "为啥", "请问", "咋", "一下", "怎么办", "能否", "能不能", "可以吗", "吗", "的", "呢", "呀", "啊"]

def strip_noise(kw):
    """剥离品牌词与疑问虚词，得到关键词核心片段（如 'WPS怎么删除空白页' -> '删除空白页'）。"""
    k = normalize(kw)
    for w in sorted(BRAND_WORDS, key=len, reverse=True):
        k = k.replace(w, "")
    for w in sorted(QUEST_WORDS, key=len, reverse=True):
        k = k.replace(w, "")
    return k.strip(" ，,?？！。、的了吗吧")

def fulltext_blob(a):
    """穷尽检索用全文本：title + targetKeywords + notes（notes 常含完整口语标题，如 '所以空白页在WPS里到底怎么删'）。"""
    tks = a.get("targetKeywords") or []
    if isinstance(tks, str):
        tks = [tks]
    return normalize(" ".join([
        str(a.get("title") or ""),
        " ".join(str(t) for t in tks),
        str(a.get("notes") or ""),
    ]))

def fulltext_hit(kw, a):
    """穷尽检索：全文本包含关键词或其核心词/核心词二元子串（bigram）覆盖度>=50%。
    返回 0/2.2/2.6/3.0。用于找出 targetKeywords 未精确命中、但 title/notes 语义相关的素材（如口语化长词）。"""
    blob = fulltext_blob(a)
    k = normalize(kw)
    if not k or not blob:
        return 0
    if k in blob:
        return 3.0
    core = strip_noise(kw)
    if len(core) >= 4 and core in blob:
        return 2.6
    if len(core) >= 4:
        grams = list(set(core[i:i + 2] for i in range(len(core) - 1)))
        hit = sum(1 for g in grams if g in blob)
        if grams and hit / len(grams) >= 0.5:
            return 2.2
    return 0

def kw_hit_score(kw, target_kws):
    """targetKeywords 与关键词的命中分：4=精确相等；3=互相包含（要求较短词 >=4 字符，过滤 WPS 等泛词）
    返回 0-4。"""
    k = normalize(kw)
    best = 0
    for t in target_kws or []:
        t = normalize(t)
        if not t:
            continue
        if k == t:
            return 4
        if k and t:
            shorter = min(k, t, key=len)
            if len(shorter) >= 4 and (k in t or t in k):
                best = max(best, 3)
    return best

def title_hit(kw, title):
    k = normalize(kw)
    t = normalize(title)
    if not k or not t:
        return False
    return k in t or t in k

def group_hit(group, pool, cms_tab):
    pools, tabs = GROUP_POOL_MAP.get(group, (set(), set()))
    hit_pool = (pool or "") in pools
    hit_tab = (cms_tab or "") in tabs
    return hit_pool or hit_tab

# 文章检索顺序优先级：WPS官方公众号 > 小绿书 > WPS社区 > WPS客服中心 > WPS学堂
SOURCE_ORDER = ["WPS 官方公众号", "小绿书", "WPS 社区", "WPS 客服中心", "WPS 学堂"]

def source_rank(a):
    """返回素材来源的排序优先级（越小越靠前），未列出的来源排最后。"""
    st = str(a.get("sourceType") or "")
    for i, name in enumerate(SOURCE_ORDER, 1):
        if name in st:
            return i
    return 9

def match_keyword(kw, arts, group=None):
    """返回该关键词的匹配素材列表，按分数降序；同分时按来源优先级（公众号>小绿书>社区>客服>学堂）、P0/P1/P2、ID 排序。
    穷尽检索：targetKeywords 命中 > 全文本（title+targetKeywords+notes）命中 > title 命中 > 组别命中。"""
    res = []
    for a in arts:
        sc = kw_hit_score(kw, a.get("targetKeywords"))
        if sc == 0:
            sc = fulltext_hit(kw, a)   # 全文本穷尽（含 notes 口语标题 / 核心词 / bigram 覆盖）
        if sc == 0 and title_hit(kw, a.get("title")):
            sc = 2
        if sc == 0 and group and group_hit(group, a.get("pool"), a.get("cmsTab")):
            sc = 1
        if sc == 0:
            continue
        # 故障解决组：客服中心来源加权
        if group == "故障解决" and a.get("sourceType") in FAQ_SOURCE_TYPES:
            sc += 0.5
        res.append((sc, a))
    prio = {"P0": 0, "P1": 1, "P2": 2}
    res.sort(key=lambda x: (-x[0], source_rank(x[1]), prio.get(str(x[1].get("priority")), 9), str(x[1].get("id", ""))))
    return res

def find_rundata_dir():
    """定位工作区 .rundata 目录：最近 lingxi-claw 工作区 > 当前目录。"""
    home = os.path.expanduser("~")
    base = os.path.join(home, "Documents", "lingxi-claw")
    if os.path.isdir(base):
        wss = sorted([d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d)],
                     key=os.path.getmtime, reverse=True)
        if wss:
            return os.path.join(wss[0], ".rundata")
    return os.path.join(os.getcwd(), ".rundata")

def load_keywords(kw_file=None, keywords=None):
    """从选题清单 md 或命令行解析关键词列表。返回 [(group, kw)] 列表。"""
    if keywords:
        return [(None, k.strip()) for k in keywords.split(",") if k.strip()]
    if kw_file and os.path.isfile(kw_file):
        items = []
        with open(kw_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("|") or "关键词" in line:
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 3:
                    group = cells[1].split(" · ")[0]  # 策略组别（去掉“ · 教程内容页”等后缀）
                    kw = cells[2]             # 关键词
                    if kw and kw != "---":
                        items.append((group, kw))
        if items:
            return items
    # 兜底：尝试最近选题清单
    home = os.path.expanduser("~")
    base = os.path.join(home, "Documents", "lingxi-claw")
    if os.path.isdir(base):
        cands = sorted(glob.glob(os.path.join(base, "*", "*周度文章选题*.md")),
                       key=os.path.getmtime, reverse=True)
        if cands:
            return load_keywords(cands[0])
    sys.exit("[错误] 未找到关键词来源：请用 --kw-file 指定选题清单，或用 --keywords 直接给关键词。")

def main():
    ap = argparse.ArgumentParser(description="WPS SEO 周度文章 · 素材采集")
    ap.add_argument("--file-id", default=DEFAULT_FILE_ID, help="金山多维表文件 ID（默认 WPS资源池）")
    ap.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="多维表 sheet ID（默认 1）")
    ap.add_argument("--pool-url", default=DEFAULT_POOL_URL, help="回退资源池 JSON 地址（默认不使用）")
    ap.add_argument("--data", default=DEFAULT_DATA_PATH, help="回退资源池数据文件路径（默认 articles_data.json）")
    ap.add_argument("--cache", help="本地缓存 JSON 路径（默认自动定位到工作区 .rundata/）")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存强制重新抓取")
    ap.add_argument("--kw-file", help="选题清单 .md（含 | 组别 | 关键词 | 表格）")
    ap.add_argument("--keywords", help="直接给关键词，逗号分隔（可用 --group 统一分组）")
    ap.add_argument("--group", default=None, help="给 --keywords 统一指定策略组别")
    ap.add_argument("--top", type=int, default=15, help="每个关键词最多展示素材条数（默认 15，穷尽检索）")
    ap.add_argument("--out", help="输出素材匹配清单路径（.md）")
    args = ap.parse_args()

    # 缓存路径
    cache = args.cache
    if not cache:
        cache = os.path.join(find_rundata_dir(), "pool_articles.json")

    arts = fetch_pool(args.file_id, args.sheet_id, url=args.pool_url, data_path=args.data,
                      cache=cache, refresh=args.refresh)
    print(f"[数据] 资源池共 {len(arts)} 篇文章", file=sys.stderr)

    items = load_keywords(args.kw_file, args.keywords)
    if not items:
        sys.exit("[错误] 关键词为空")
    # 手动关键词时应用 --group
    if args.keywords and args.group:
        items = [(args.group, k) for _, k in items]

    lines = []
    lines.append("# WPS SEO 周度文章 · 素材匹配")
    lines.append("")
    src_desc = f"金山多维表（file_id={args.file_id}）" if args.pool_url == DEFAULT_POOL_URL else f"资源池 JSON（{args.pool_url}）"
    lines.append(f"资源池：{src_desc} · {len(arts)} 篇 · 关键词 {len(items)} 个")
    lines.append("")
    no_match = []
    for idx, (group, kw) in enumerate(items, 1):
        lines.append(f"## {idx}. {kw}  （组别：{group or '未指定'}）")
        matches = match_keyword(kw, arts, group=group)
        if not matches:
            no_match.append((group, kw))
            lines.append("> 无匹配素材：本篇将主要依赖词库搜索意图 + 网络搜索补充。")
            lines.append("")
            continue
        lines.append("| 分 | 素材ID | 文章标题 | 内容池 | CMS Tab | 优先级 | 来源 | 原文链接 | 目标关键词 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for sc, a in matches[: args.top]:
            src = a.get("sourceUrl") or ""
            lines.append(f"| {sc:.1f} | {a.get('id')} | {a.get('title')} | {a.get('pool')} | "
                         f"{a.get('cmsTab')} | {a.get('priority')} | {a.get('sourceType')} | {src} | "
                         f"{'，'.join(a.get('targetKeywords') or [])} |")
        lines.append("")

    lines.append("---")
    lines.append("## 无直接素材的关键词（需网络搜索补充）")
    for g, kw in no_match:
        lines.append(f"- {kw}（{g or '未指定'}）")
    lines.append("")
    lines.append("> 提示：对高分素材，可进一步打开 sourceUrl 原文获取详情；无法访问时改用网络搜索。")

    text = "\n".join(lines)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n[已导出] {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
