#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · 获取真实产品截图
=====================================================
配图方式（v1.4.0 起）：一律使用真实产品截图，不再使用 AI 生成示意图。

图片获取优先级（两级数据源，优先前者）：
    1) SEO 图片资源库（金山多维表「SEO图片资源库」，默认 file_id=chojYpQQMKYh）：
       直接按关键词匹配现成的 图片url/描述/标签，拿到稳定图床链接（qpic/jsDelivr/lingxi），
       命中即下载，无需再从原文抓取。
    2) WPS 内容资源池（金山多维表「WPS资源池」，默认 file_id=cn0esSVVz7sD）：
       从命中素材的 sourceUrl 原文正文提取真实界面截图，按来源优先级
       （WPS官方公众号 > 小绿书 > WPS社区 > WPS客服中心 > WPS学堂）决定用哪篇素材的图。
       脚本抓不到正文图的来源（如公众号/小绿书/客服中心页面多为 JS 渲染），
       会提示改用 browser 打开 sourceUrl 截图兜底。

用法示例：
    # 直接给素材原文链接 + 输出目录（走第二数据源：原文提取）
    python fetch_images.py --urls "https://www.wps.cn/learning/question/detail/id/1455.html" \
        --out output/第4周/tupian-zhuan-word/img --prefix ocr
    # 按关键词自动配图：优先图片库（有则用现成稳定图），无则回退资源池原文提取
    python fetch_images.py --keywords "WPS怎么制作简历,PDF转Excel" \
        --pool-file .rundata/pool_articles.json --out output/第4周 --limit 3
    # 只看候选不下载
    python fetch_images.py --keywords "..." --out ... --dry-run
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ============ 数据源 1：SEO 图片资源库（金山多维表，默认） ============
DEFAULT_IMG_FILE_ID = "chojYpQQMKYh"     # 金山多维表「SEO图片资源库」
DEFAULT_IMG_SHEET_ID = "1"

# ============ 数据源 2：WPS 内容资源池（金山多维表） ============
DEFAULT_POOL_FILE_ID = "cn0esSVVz7sD"     # 金山多维表「WPS资源池」
DEFAULT_POOL_SHEET_ID = "1"

# 各来源正文图提取启发式：排除导航/头像/徽章/图标/装饰类
BAD_CLASS = (
    "avatar", "badge", "icon", "logo", "assistant", "emoji", "like", "user-",
    "nav", "head", "footer", "tab-", "spinner", "banner", "qrcode", "qr-code",
)
BAD_WORDS = (
    "avatar", "logo", "icon", "badge", "emoji", "user", "head", "nav", "spinner",
    "default", "bg", "deco", "banner", "qr", "loading", "thumb-avatar",
)

# 来源优先级（越小越优先）
SOURCE_ORDER = ["WPS 官方公众号", "小绿书", "WPS 社区", "WPS 客服中心", "WPS 学堂"]

def source_rank(source_type):
    st = str(source_type or "")
    for i, name in enumerate(SOURCE_ORDER, 1):
        if name in st:
            return i
    return 9

# ---------- wps_docs CLI 定位（复用 fetch_pool 逻辑） ----------
def find_wps_cli():
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

# ---------- 数据源 1：SEO 图片资源库 ----------
def fetch_image_library(file_id=DEFAULT_IMG_FILE_ID, sheet_id=DEFAULT_IMG_SHEET_ID, cli=None, timeout=60):
    """通过 wps_docs CLI 分页拉取 SEO 图片资源库全部记录，返回图片记录列表。
    每条：{url, title, desc, tag, source, aid}"""
    if not cli:
        return None
    args_base = ["dbsheet", "list-records", "--file-id", file_id, "--sheet-id", sheet_id,
                 "--fields", "图片url,图片所属文章标题,图片描述,图片标签,素材来源,文章ID",
                 "--page-size", "1000"]
    lib = []
    token = ""
    while True:
        args = [sys.executable, cli] + args_base
        if token:
            args += [f"--page-token={token}"]
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            d = json.loads(r.stdout)
        except Exception as e:
            print(f"[重试] 拉取图片资源库失败：{e}", file=sys.stderr)
            time.sleep(2)
            break
        if not d.get("success"):
            print(f"[错误] 图片资源库拉取失败：{d.get('error')}", file=sys.stderr)
            break
        recs = d["data"]["records"]
        for rec in recs:
            f = rec.get("fields", {})
            lib.append({
                "url": f.get("图片url", ""),
                "title": f.get("图片所属文章标题", ""),
                "desc": f.get("图片描述", ""),
                "tag": f.get("图片标签", ""),
                "source": f.get("素材来源", ""),
                "aid": f.get("文章ID", ""),
            })
        token = d["data"].get("page_token", "")
        if not token:
            break
    return lib

def normalize(s):
    return (s or "").strip().lower().replace(" ", "").replace("，", ",")

def match_image_library(lib, keywords, group=None, limit=5):
    """在 SEO 图片资源库中按关键词匹配图片记录。
    匹配域：图片标签（含精准标签/泛标签）+ 图片描述 + 标题。
    打分：标签精确命中 3 分 > 描述包含 2 分 > 标题包含 1 分；同分按来源优先级、ID 排序。
    返回 [(kw, [img_rec,...]), ...]"""
    results = []
    for kw in keywords:
        k = normalize(kw)
        if not k:
            continue
        scored = []
        for img in lib:
            tag = normalize(img.get("tag") or "")
            desc = normalize(img.get("desc") or "")
            title = normalize(img.get("title") or "")
            blob = " ".join([tag, desc, title])
            sc = 0
            # 标签精确/包含命中优先
            if k and k in tag:
                sc = 3
            elif k and k in blob:
                sc = 2
            elif len(k) >= 4 and k[:4] in blob:
                sc = 1
            if sc:
                scored.append((sc, img))
        scored.sort(key=lambda x: (-x[0], source_rank(x[1].get("source")),
                                   str(x[1].get("aid", "")), str(x[1].get("url", ""))))
        results.append((kw, [img for _, img in scored[:limit]]))
    return results

# ---------- 数据源 2：WPS 资源池原文提取（原逻辑） ----------
def _abs(url):
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    return url

def _is_bitmap(url):
    return re.search(r"\.(png|jpe?g|jfif|webp|gif)([?&#]|$)", url.lower()) is not None

def _is_bad(url, img):
    low = url.lower()
    cls = " ".join(img.get("class") or []).lower()
    if any(b in cls for b in BAD_CLASS):
        return True
    if any(b in low for b in BAD_WORDS):
        return True
    return False

def extract_school(soup):
    out = []
    for im in soup.find_all("img"):
        src = (im.get("src") or im.get("data-src") or "").strip()
        if not src or src.startswith("data:") or not _is_bitmap(src):
            continue
        a = _abs(src)
        if "wpsacdm.cache.wpscdn.cn" not in a:
            continue
        if _is_bad(a, im):
            continue
        out.append(a)
    return out

def extract_community(soup):
    out = []
    for im in soup.find_all("img"):
        src = (im.get("src") or im.get("data-src") or "").strip()
        if not src or src.startswith("data:") or not _is_bitmap(src):
            continue
        a = _abs(src)
        if _is_bad(a, im):
            continue
        parent = im.find_parent()
        ctx = " ".join(parent.get("class") or []) if parent else ""
        if any(k in ctx for k in ("content", "kdocs-img", "article", "rich-text", "post-body", "detail")):
            out.append(a)
    return out

def extract_generic(soup):
    out = []
    for im in soup.find_all("img"):
        src = (im.get("src") or im.get("data-src") or "").strip()
        if not src or src.startswith("data:") or not _is_bitmap(src):
            continue
        a = _abs(src)
        if _is_bad(a, im):
            continue
        out.append(a)
    return out

def extract_from_url(url, source_type=""):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        return [], f"抓取失败：{e}"
    soup = BeautifulSoup(r.text, "html.parser")
    if "学堂" in (source_type or ""):
        cands = extract_school(soup)
    elif "社区" in (source_type or ""):
        cands = extract_community(soup)
    else:
        cands = extract_generic(soup)
    if not cands and "客服中心" in (source_type or ""):
        cands = extract_generic(soup)
    seen, uniq = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    note = ""
    if not uniq:
        note = "未提取到正文图（页面可能为 JS 渲染/无图），建议 browser 打开 sourceUrl 截图"
    return uniq, note

def download(img_url, out_dir, prefix, url_idx, idx, referer=None, timeout=20):
    try:
        hdrs = dict(HEADERS)
        if referer:
            hdrs["Referer"] = urllib.parse.urljoin(referer, "/")
        r = requests.get(img_url, headers=hdrs, timeout=timeout)
        r.raise_for_status()
        if len(r.content) < 3000:
            return None, "图太小(<3KB)，跳过"
        ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1] or ".png"
        ext = ext.lower()
        if ext in (".jfif", ".jpeg"):
            ext = ".jpg"
        if ext not in (".png", ".jpg", ".webp", ".gif"):
            ext = ".png"
        name = f"{prefix}-{url_idx}-{idx}{ext}"
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(r.content)
        return name, "OK"
    except Exception as e:
        return None, str(e)

def load_pool(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def find_pool_sources(pool, keywords, group=None, limit=3):
    arts = []
    for kw in keywords:
        best = []
        for a in pool:
            blob = " ".join([
                str(a.get("title") or ""),
                " ".join(str(t) for t in (a.get("targetKeywords") or []) if not isinstance(t, (list, dict))),
                str(a.get("notes") or ""),
            ]).lower()
            sc = 0
            k = kw.lower()
            if k in blob:
                sc = 3
            elif len(k) >= 4 and k[:4] in blob:
                sc = 2
            if sc:
                best.append((sc, a))
        best.sort(key=lambda x: (-x[0], source_rank(x[1].get("sourceType")),
                                 {"P0": 0, "P1": 1, "P2": 2}.get(str(x[1].get("priority")), 9),
                                 str(x[1].get("id", ""))))
        for sc, a in best[:limit]:
            arts.append((kw, a))
    return arts

def main():
    ap = argparse.ArgumentParser(description="获取真实产品截图：优先 SEO 图片资源库，回退 WPS 资源池原文")
    ap.add_argument("--urls", default="", help="素材原文 URL 列表，逗号分隔（走第二数据源：原文提取）")
    ap.add_argument("--source-type", default="", help="URL 的来源类型（WPS学堂/社区/客服中心/公众号/小绿书），用','对应 urls")
    ap.add_argument("--keywords", default="", help="关键词，逗号分隔（优先匹配图片资源库，回退 pool-file）")
    ap.add_argument("--pool-file", default="", help="WPS资源池缓存 JSON（.rundata/pool_articles.json，回退原文提取用）")
    ap.add_argument("--group", default="", help="策略组别（可选，配合 keywords）")
    ap.add_argument("--img-file-id", default=DEFAULT_IMG_FILE_ID, help="SEO图片资源库多维表 file_id")
    ap.add_argument("--img-sheet-id", default=DEFAULT_IMG_SHEET_ID, help="SEO图片资源库 sheet ID")
    ap.add_argument("--out", required=True, help="图片输出目录（如 output/第4周/<slug>/img）")
    ap.add_argument("--prefix", default="shot", help="下载图片文件名前缀（如 ocr / resume）")
    ap.add_argument("--limit", type=int, default=5, help="每个关键词/URL 最多下载图片数")
    ap.add_argument("--dry-run", action="store_true", help="只列出候选图 URL，不下载")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    all_map = {}
    used_source = None

    # ---- 数据源 1：SEO 图片资源库（按关键词优先） ----
    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
        cli = find_wps_cli()
        lib = None
        if cli:
            print("[数据] 尝试从 SEO 图片资源库匹配图片…", file=sys.stderr)
            lib = fetch_image_library(args.img_file_id, args.img_sheet_id, cli)
        if lib:
            print(f"[数据] SEO 图片资源库共 {len(lib)} 条图片记录", file=sys.stderr)
            used_source = f"SEO图片资源库(file_id={args.img_file_id})"
            for kw, matches in match_image_library(lib, kws, group=args.group, limit=args.limit):
                if matches:
                    print(f"  [关键词] {kw} → 命中 {len(matches)} 张图片")
                    for idx, img in enumerate(matches, 1):
                        print(f"      - {img['url'][:90]}  （{img.get('tag') or ''}）")
                        if args.dry_run:
                            all_map[img["url"]] = img["title"]
                            continue
                        name, msg = download(img["url"], args.out, args.prefix, 1, idx)
                        if name:
                            print(f"      [已下载] {name}  <- {img['url'][:90]}")
                            all_map[os.path.join(args.out, name)] = img["title"]
                        else:
                            print(f"      [跳过] {img['url'][:80]} （{msg}）")
                else:
                    print(f"  [关键词] {kw} → 图片资源库无命中，待回退原文提取")

    # ---- 数据源 2：原文提取（--urls 直给 或 图片库未命中时回退 pool-file） ----
    tasks = []
    if args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
        sts = [s.strip() for s in args.source_type.split(",")] if args.source_type else []
        for i, u in enumerate(urls):
            tasks.append((u, sts[i] if i < len(sts) else ""))
    elif args.keywords and args.pool_file:
        pool = load_pool(args.pool_file)
        for kw, a in find_pool_sources(pool, [k.strip() for k in args.keywords.split(",") if k.strip()],
                                       group=args.group, limit=3):
            tasks.append((a.get("sourceUrl", ""), a.get("sourceType", "")))

    if tasks:
        if not used_source:
            used_source = "WPS资源池素材原文提取"
        print(f"\n[数据] 第二数据源（{used_source}）：共 {len(tasks)} 个素材原文待提取")
        ui_offset = 2
        for ui, (url, st) in enumerate(tasks, 1):
            if not url:
                print(f"  [跳过] 无 sourceUrl（来源 {st or '未知'}）")
                continue
            print(f"  [素材] ({st or '未知'}) {url}")
            cands, note = extract_from_url(url, st)
            print(f"    候选图 {len(cands)} 张 {note}")
            if not cands:
                continue
            idx = 0
            for cu in cands:
                if idx >= args.limit:
                    break
                idx += 1
                if args.dry_run:
                    print(f"      - {cu}")
                    all_map[cu] = url
                    continue
                name, msg = download(cu, args.out, args.prefix, ui + ui_offset, idx, referer=url)
                if name:
                    print(f"      [已下载] {name}  <- {cu[:90]}")
                    all_map[os.path.join(args.out, name)] = url
                else:
                    print(f"      [跳过] {cu[:80]} （{msg}）")

    if not tasks and args.keywords and not args.pool_file:
        # 只有图片库数据源，无回退
        if used_source:
            pass
        else:
            sys.exit("[提示] 未找到 wps_docs CLI，且未提供 --pool-file 回退，无法获取图片")

    out_json = os.path.join(args.out, "_image_sources.json")
    if all_map and not args.dry_run:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(all_map, f, ensure_ascii=False, indent=2)
        print(f"\n[已导出] 图片来源映射 {out_json}（供溯源）")
    print("\n提示：图片获取优先级为 SEO图片资源库 > WPS资源池原文。若两级均无图/抓取失败，"
          "请用 browser 打开对应 sourceUrl 截图作为兜底。")

if __name__ == "__main__":
    main()
