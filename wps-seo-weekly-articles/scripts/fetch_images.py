#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · 从资源池素材原文提取真实产品截图
=====================================================
配图方式（v1.3.0 起）：一律使用真实产品截图，不再使用 AI 生成示意图。

优先从资源池命中素材的 sourceUrl 原文提取正文里的真实界面截图；素材来源
优先级（WPS官方公众号 > 小绿书 > WPS社区 > WPS客服中心 > WPS学堂）决定
优先用哪篇素材的图。脚本抓不到正文图的来源（如公众号/小绿书/客服中心页面
多为 JS 渲染），会提示改用 browser 打开 sourceUrl 截图兜底。

用法示例：
    # 直接给素材原文链接 + 输出目录
    python fetch_images.py --urls "https://www.wps.cn/learning/question/detail/id/1455.html" \
        --out output/第4周/tupian-zhuan-word/img --prefix ocr
    # 复用资源池：按关键词自动找高分素材并提取其配图
    python fetch_images.py --keywords "WPS怎么制作简历,PDF转Excel" \
        --pool-file .rundata/pool_articles.json --out output/第4周 --limit 3
    # 只看候选不下载
    python fetch_images.py --urls "..." --out ... --dry-run
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.parse
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

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
    """WPS学堂：正文图为 res1.wpsacdm.cache.wpscdn.cn 位图（auto/*.png 或 images/*.jpg/gif），过滤 svg/装饰。"""
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
    """WPS社区：正文图在内容容器里（parent class 含 content / kdocs-img / article / rich-text）。"""
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
    """通用兜底：非 svg 位图，且排除明显装饰。"""
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
    """按来源类型提取正文图 URL 列表（去重保序）。返回 (list, note)。"""
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
    # 去重保序
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
    """在资源池中按关键词（含组别映射，逻辑对齐 fetch_pool）找高分素材的 sourceUrl。"""
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
    ap = argparse.ArgumentParser(description="从资源池素材原文提取真实产品截图")
    ap.add_argument("--urls", default="", help="素材原文 URL 列表，逗号分隔")
    ap.add_argument("--source-type", default="", help="URL 的来源类型（WPS学堂/社区/客服中心/公众号/小绿书），用','对应 urls")
    ap.add_argument("--keywords", default="", help="关键词，逗号分隔（配合 --pool-file 自动找素材）")
    ap.add_argument("--pool-file", default="", help="资源池缓存 JSON（.rundata/pool_articles.json）")
    ap.add_argument("--group", default="", help="策略组别（可选，配合 keywords）")
    ap.add_argument("--out", required=True, help="图片输出目录（如 output/第4周/<slug>/img）")
    ap.add_argument("--prefix", default="shot", help="下载图片文件名前缀（如 ocr / resume）")
    ap.add_argument("--limit", type=int, default=5, help="每个 URL 最多下载图片数")
    ap.add_argument("--dry-run", action="store_true", help="只列出候选图 URL，不下载")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

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
    else:
        sys.exit("请提供 --urls 或 --keywords+--pool-file")

    if not tasks:
        sys.exit("[提示] 未找到可提取的素材链接")

    print(f"共 {len(tasks)} 个素材原文待提取：")
    all_map = {}
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
            name, msg = download(cu, args.out, args.prefix, ui, idx, referer=url)
            if name:
                print(f"      [已下载] {name}  <- {cu[:90]}")
                all_map[os.path.join(args.out, name)] = url
            else:
                print(f"      [跳过] {cu[:80]} （{msg}）")

    out_json = os.path.join(args.out, "_image_sources.json")
    if all_map and not args.dry_run:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(all_map, f, ensure_ascii=False, indent=2)
        print(f"\n[已导出] 图片来源映射 {out_json}（供溯源）")
    print("\n提示：以上为从资源池素材原文提取的真实截图。若某来源无图/抓取失败，"
          "请用 browser 打开对应 sourceUrl 截图作为兜底。")


if __name__ == "__main__":
    main()
