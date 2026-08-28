#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · 上传 CMS 草稿箱（不发布）
=============================================
把 build_html 渲染好的周目录（output/第N周/）逐篇上传到 wps.cn 文章 CMS 的草稿状态。
只创建草稿，绝不发布。

流程：
    1. 读取每篇 <slug>/article.md（frontmatter）+ <slug>/index.html（已渲染正文）
    2. GET /api/category/list 拉分类，把关键词/组别映射到分类 CateID
    3. 上传封面图与正文配图 POST /api/file/upload（超 500KB 自动压缩），替换相对路径为绝对 URL
    4. POST /api/article/publish 创建草稿（Status=DRAFT）
    5. 校验 GET /api/article?status=0&title=…

实测要点（wps.cn 文章 CMS）：
    SERVER_HOST = https://www.wps.cn/article （接口基础路径为 https://www.wps.cn/article/api）
    草稿状态值 = 0（列表接口 status 0=草稿, 1=已发布）
    图片上传接口 /manage/file/upload 需后台登录凭证（--cookie），OpenAPI token 不适用；无凭证时用 --no-images 跳过

用法示例：
    python upload_cms.py --host https://www.wps.cn/article --token OpenAPIToken --articles-dir output/第3周
    python upload_cms.py --host https://www.wps.cn/article --token xxx --articles-dir output/第3周 --dry-run   # 试运行不真正上传
    python upload_cms.py --host https://www.wps.cn/article --token xxx --articles-dir output/第3周 --cookie "SESSION=..."  # 带后台登录Cookie传图
    python upload_cms.py --host https://www.wps.cn/article --token xxx --articles-dir output/第3周 --no-images   # 不传图，图片位后补
"""
import argparse
import glob
import io
import json
import os
import re
import sys

# 组别/关键词 -> 默认分类名（可在运行时按实际分类列表自动匹配，命中优先）
GROUP_DEFAULT_CATEGORY = {
    "下载安装": "WPS教程",
    "价格购买": "office",
    "对比选择": "office",
    "模板获取": "office",
    "格式转换": "PDF",
    "故障解决": "WPS教程",
    "教程操作": "WPS教程",
    "功能认知": "WPS教程",
    "AI认知": "WPS AI",
    "品牌直达": "WPS教程",
}
# 关键词中包含这些词时优先归到对应分类
CATEGORY_KEYWORDS = [
    ("Excel", ["excel", "表格", "vlookup", "xlookup", "透视", "数据", "单元格", "函数"]),
    ("Word", ["word", "文字", "文档", "页眉", "页脚", "目录", "正文"]),
    ("PPT", ["ppt", "演示", "幻灯片", "放映"]),
    ("PDF", ["pdf", "转换", "pdf转"]),
    ("WPS AI", ["ai", "灵犀", "智能", "一键生成"]),
    ("在线文档", ["在线", "协作", "云文档", "wps365"]),
    ("WPS教程", ["wps", "教程", "技巧", "怎么"]),
]


def infer_category(group, kw, categories):
    """从关键词+组别推断分类，返回分类名（若无匹配返回 None）。"""
    kw_l = (kw or "").lower()
    for cname, words in CATEGORY_KEYWORDS:
        if any(w in kw_l for w in words) and cname in categories:
            return cname
    default = GROUP_DEFAULT_CATEGORY.get(group)
    if default and default in categories:
        return default
    # 兜底：取第一个分类
    return categories[0] if categories else None


# ---------------------------------------------------------------------------
# frontmatter 解析（与 build_html.py 保持一致的子集）
# ---------------------------------------------------------------------------
def parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip()
    body = text[end + 4:].strip()
    meta = {}
    lines = fm.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w]*):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if not val:
            if key in ("faq", "sources", "tags"):
                items = []
                i += 1
                while i < len(lines) and re.match(r"^\s*-\s", lines[i]):
                    item_line = lines[i].strip()[1:].strip()
                    if key == "faq":
                        q = a = ""
                        if ":" in item_line:
                            q = item_line.split(":", 1)[1].strip().strip("\"'")
                        i += 1
                        while i < len(lines) and re.match(r"^\s+a:\s*", lines[i]):
                            a = lines[i].strip()[3:].strip().strip("\"'")
                            i += 1
                        items.append({"q": q, "a": a})
                    else:
                        items.append(item_line.strip("\"'"))
                        i += 1
                meta[key] = items
                continue
            meta[key] = None
            i += 1
            continue
        meta[key] = val.strip("\"'")
        i += 1
    return meta, body


# ---------------------------------------------------------------------------
# API 客户端
# ---------------------------------------------------------------------------
class CmsClient:
    def __init__(self, host, token, dry_run=False, timeout=30, cookie=""):
        self.base = host.rstrip("/") + "/api"
        self.root = host.rstrip("/")   # 用于 /manage/file/upload 等非 /api 前缀接口
        self.token = token
        self.cookie = cookie
        self.dry_run = dry_run
        self.timeout = timeout

    def _auth(self):
        return {"access_token": self.token}

    def get(self, path, **params):
        import requests
        params = {**params, **self._auth()}
        r = requests.get(self.base + path, params=params, timeout=self.timeout)
        return self._check(r)

    def post(self, path, json_body=None, data=None, files=None, params=None):
        import requests
        params = {**(params or {}), **self._auth()}
        if self.dry_run:
            print(f"  [dry-run] POST {self.base + path} {json.dumps(json_body, ensure_ascii=False)}")
            return {"result": True}
        r = requests.post(self.base + path, json=json_body, data=data, files=files,
                          params=params, timeout=self.timeout)
        return self._check(r)

    def _check(self, r):
        try:
            return r.json()
        except Exception:
            sys.exit(f"[错误] 接口返回非 JSON（HTTP {r.status_code}）：{r.text[:300]}")


def upload_image(client, file_path):
    """上传单张图片（走 {root}/manage/file/upload，需后台登录 Cookie），超 500KB 自动压缩。
    返回 (path, link)。"""
    data = _read_bytes(file_path)
    if len(data) > 500 * 1024:
        data = _compress(file_path, data)
    if client.dry_run:
        return ("/dryrun/" + os.path.basename(file_path),
                "https://dryrun/" + os.path.basename(file_path))
    import requests as _req
    headers = {"User-Agent": "Mozilla/5.0"}
    if client.cookie:
        headers["Cookie"] = client.cookie
    files = {"file": (os.path.basename(file_path), data, _mime(file_path))}
    url = client.root + "/manage/file/upload"
    r = _req.post(url, params={"space": 1}, files=files, headers=headers, timeout=client.timeout)
    try:
        j = r.json()
    except Exception:
        sys.exit(f"[错误] 图片上传接口异常（HTTP {r.status_code}），需后台登录 Cookie：{r.text[:200]}")
    if r.status_code != 200 or not (j.get("path") or j.get("link")):
        sys.exit(f"[错误] 图片上传失败（HTTP {r.status_code}）：{j}")
    return j.get("path"), j.get("link")


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _mime(path):
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
    }.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def _compress(file_path, data):
    """用 PIL 压缩图片到 <500KB（缩放 + 降质），返回新字节。"""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")
    # 缩放：宽不超过 1200
    if im.width > 1200:
        im = im.resize((1200, int(im.height * 1200 / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    quality = 85
    while True:
        buf.seek(0)
        buf.truncate()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= 500 * 1024 or quality <= 40:
            break
        quality -= 10
    print(f"  [压缩] {os.path.basename(file_path)} 超 500KB，已压缩为 JPEG {quality}q / {buf.tell()//1024}KB")
    return buf.getvalue()


def extract_post_html(page_html):
    """从渲染好的文章页提取 <article class="post"> 区块（正文+FAQ）。结构最终按 2666：封面图+图文+FAQ，不含下载 CTA。"""
    m = re.search(r'<article class="post">(.*?)</article>', page_html, re.S)
    if not m:
        return None
    return m.group(1)


def load_image_map(path):
    """读取图床 URL 映射：JSON（本地路径->公网URL）或 两列文本（路径 空格 URL）。"""
    if not path or not os.path.isfile(path):
        return {}
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    m = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 2 and not cells[1].startswith("公"):
                    m[cells[0]] = cells[1]
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith("img") or "." in parts[0]:
                m[parts[0]] = parts[1]
    return m


def upload_article_images(client, slug_dir, post_html, skip=False, image_map=None, base_dir=None):
    """把正文中的相对图片路径替换为绝对 URL。
    优先级：图床 URL 映射（--image-map，键为相对 base_dir 的路径）> 后台 Cookie 上传 > 保留相对路径。"""
    image_map = image_map or {}
    base_dir = os.path.abspath(base_dir or os.path.dirname(slug_dir))
    basename_map = {os.path.basename(k): v for k, v in image_map.items()}

    def repl(m):
        src = m.group(1)
        if src.startswith("http"):
            return m.group(0)
        local = os.path.join(slug_dir, src)
        if os.path.isfile(local):
            key = os.path.relpath(local, base_dir).replace("\\", "/")
            if key in image_map:
                return f'src="{image_map[key]}"'
        # 兜底：按文件名命中
        if os.path.basename(src) in basename_map:
            return f'src="{basename_map[os.path.basename(src)]}"'
        if skip or not client.cookie:
            return m.group(0)  # 保留相对路径，发布前需补图
        if os.path.isfile(local):
            path, link = upload_image(client, local)
            return f'src="{link}"'
        return m.group(0)

    return re.sub(r'src="([^"]+)"', repl, post_html)


def main():
    from pathlib import Path

    ap = argparse.ArgumentParser(description="WPS SEO 周度文章 · 上传 CMS 草稿箱")
    ap.add_argument("--host", required=True, help="CMS SERVER_HOST（如 https://example.com）")
    ap.add_argument("--token", required=True, help="OpenAPIToken（access_token）")
    ap.add_argument("--articles-dir", required=True, help="周目录（含各 <slug>/article.md 与 index.html）")
    ap.add_argument("--status", default="0", help="草稿状态值（实测 wps.cn 用 0=草稿；默认 0）")
    ap.add_argument("--author", default="", help="作者名（可选）")
    ap.add_argument("--tags", default="", help="附加标签，逗号分隔（可选）")
    ap.add_argument("--cookie", default="", help="后台登录 Cookie（上传图片用，如 SESSION=xxx）")
    ap.add_argument("--image-map", default="", help="图床 URL 映射文件：JSON(本地路径->公网URL) 或 两列文本")
    ap.add_argument("--no-images", action="store_true", help="跳过图片上传（正文图片位后补）")
    ap.add_argument("--dry-run", action="store_true", help="试运行：打印将上传的内容，不真正调用")
    args = ap.parse_args()

    image_map = load_image_map(args.image_map)
    if image_map:
        print(f"[数据] 图床 URL 映射 {len(image_map)} 条")

    client = CmsClient(args.host, args.token, dry_run=args.dry_run, cookie=args.cookie)

    # 1. 拉分类
    categories = {}
    try:
        r = client.get("/article/category/list", page=1, perpage=200)
        data = r.get("data") or []
        for c in data:
            cid = c.get("id")
            name = c.get("name")
            if cid is not None and name:
                categories[name] = cid
    except SystemExit as e:
        sys.exit(f"[错误] 拉取分类失败（检查 host/token）：{e}")
    if not categories:
        print("[警告] 未获取到分类列表，CateID 将由 --category-name 指定或使用默认", file=sys.stderr)
    print(f"[数据] 分类 {len(categories)} 个：{', '.join(list(categories)[:12])}")

    # 2. 遍历文章
    results = []
    for md_file in sorted(glob.glob(os.path.join(args.articles_dir, "*", "article.md"))):
        slug_dir = os.path.dirname(md_file)
        slug = os.path.basename(slug_dir)
        index_html = os.path.join(slug_dir, "index.html")
        if not os.path.isfile(index_html):
            print(f"[跳过] 缺少 index.html：{slug_dir}")
            continue
        with open(md_file, "r", encoding="utf-8") as f:
            meta, _body = parse_frontmatter(f.read())
        with open(index_html, "r", encoding="utf-8") as f:
            page_html = f.read()

        title = meta.get("title") or os.path.basename(slug_dir)
        kw = meta.get("keyword", "")
        group = meta.get("group", "")
        seo_title = meta.get("meta_title") or title
        seo_brief = meta.get("meta_desc") or ""
        post_html = extract_post_html(page_html)
        if post_html is None:
            print(f"[跳过] 无法提取正文区块：{slug_dir}")
            continue

        print(f"\n=== {slug} ===\n  标题：{title}\n  关键词：{kw} | 组别：{group}")

        # 3. 处理图片：图床映射 > 后台 Cookie 上传 > 保留相对路径
        replaced = upload_article_images(client, slug_dir, post_html, skip=args.no_images,
                                         image_map=image_map, base_dir=args.articles_dir)
        if replaced == post_html and not args.no_images and not args.cookie and not image_map:
            print("  [提示] 未配置图片方案（--image-map 或 --cookie），正文图片保持相对路径（发布前需补图）")
        post_html = replaced

        # 封面图：优先用图床 URL（image-map 按文件名匹配），否则尝试 CMS 上传；失败降级留空不阻断草稿
        cover_url = None
        if meta.get("image"):
            cover_src = meta["image"]
            bmap = {os.path.basename(k): v for k, v in image_map.items()}
            if image_map and os.path.basename(cover_src) in bmap:
                cover_url = bmap[os.path.basename(cover_src)]
            else:
                local_cover = os.path.join(slug_dir, cover_src)
                if os.path.isfile(local_cover):
                    try:
                        _p, cover_url = upload_image(client, local_cover)
                    except SystemExit:
                        print("  [提示] 封面图上传失败，封面留空（CMS 图片接口需后台登录态，已改用图床 URL 更佳）")

        # 4. 分类
        cate_name = infer_category(group, kw, categories)
        cate_id = categories.get(cate_name)
        if not cate_id:
            print(f"  [警告] 未找到分类 {cate_name}，跳过本篇（需先确认 CMS 分类）")
            continue

        # 标签：frontmatter tags（Agent 写作时按内容生成）> 关键词 > --tags 附加，合并去重
        tags = []
        ft = meta.get("tags")
        if isinstance(ft, list):
            tags = [str(t).strip() for t in ft if str(t).strip()]
        elif isinstance(ft, str) and ft.strip():
            tags = [t.strip() for t in ft.split(",") if t.strip()]
        if kw and kw not in tags:
            tags.append(kw)
        if args.tags:
            for t in args.tags.split(","):
                t = t.strip()
                if t and t not in tags:
                    tags.append(t)

        payload = {
            "Title": title,
            "Content": post_html,
            "CateID": cate_id,
            "Status": args.status,
            "Image": cover_url or "",
            "Tags": tags,
            "SeoTitle": seo_title,
            "SeoBrief": seo_brief,
        }
        if args.author:
            payload["Author"] = args.author

        print(f"  [上传] 分类={cate_name}({cate_id}) 状态={args.status} 封面={cover_url or '无'} 图片{post_html.count('<img')}张")
        r = client.post("/article/publish", json_body=payload)
        if isinstance(r, dict) and r.get("result") is False:
            print(f"  [失败] {r.get('error_message') or r}")
            continue
        article_id = r.get("id") if isinstance(r, dict) else None
        link = r.get("link") if isinstance(r, dict) else None
        results.append({"slug": slug, "title": title, "id": article_id, "link": link, "status": args.status})
        print(f"  [OK] id={article_id} link={link}")

    # 5. 汇总
    print("\n" + "=" * 50)
    print(f"共处理 {len(results)} 篇草稿（{'试运行，未实际上传' if args.dry_run else '已创建草稿，未发布'}）")
    for r in results:
        print(f"  - {r['title']}  id={r['id']}  {r['link'] or ''}")


if __name__ == "__main__":
    main()
