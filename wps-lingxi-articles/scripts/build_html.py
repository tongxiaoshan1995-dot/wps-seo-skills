#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · HTML 图文渲染脚本
====================================
把每篇文章（Markdown + frontmatter）渲染成独立的 HTML 图文单页（CMS 独立站风格），
并生成该周的目录索引页 index.html。

文章目录约定（--articles-dir）：
    <第N周>/
    ├── index.html          # 由本脚本生成的周目录页
    └── <slug>/
        ├── article.md      # frontmatter + Markdown 正文
        └── img/            # 文章配图（正文中引用 img/xxx.jpg）

article.md frontmatter 字段：
    title       必填  文章标题
    keyword     必填  目标关键词
    group       必填  策略组别（10 组之一）
    meta_title  选填  SEO 标题（默认取 title）
    meta_desc   选填  SEO 描述（默认取正文前 80 字）
    date        选填  发布日期（默认今天）
    image       选填  封面主图，相对 article.md（如 img/cover.jpg）
    slug        选填  文件夹名，默认由关键词生成
    faq:        选填  列表：q / a 问答对
    sources:    选填  参考来源 URL 列表

用法示例：
    python build_html.py --articles-dir output/第3周 --out output/第3周
    python build_html.py --articles-dir output/第3周 --theme wps --css assets/template/article.css
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import date as _date

# ---------------------------------------------------------------------------
# 极小 Markdown -> HTML 转换（覆盖技能所用子集）
# ---------------------------------------------------------------------------
INLINE_RE = [
    (re.compile(r"!\[([^\]]*)\]\(([^)]+)\)"), r'<img src="\2" alt="\1" loading="lazy">'),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2" target="_blank" rel="noopener">\1</a>'),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\*([^*]+)\*"), r"<em>\1</em>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
]


def inline(s):
    for pat, rep in INLINE_RE:
        s = pat.sub(rep, s)
    return s


def render_table(rows):
    out = ["<table>"]
    for i, cells in enumerate(rows):
        tag = "th" if i == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}>{inline(c.strip())}</{tag}>" for c in cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def md_to_html(md):
    """把 Markdown 正文转成 HTML 片段（支持标题/段落/列表/引用/表格/分隔线/图片/代码）。"""
    lines = md.splitlines()
    out = []
    para = []
    i = 0

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        # 表格
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            flush_para()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append(render_table(rows))
            continue
        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        # 引用
        if line.startswith(">"):
            flush_para()
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(buf))}</blockquote>")
            continue
        # 无序/有序列表
        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            flush_para()
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and (
                re.match(r"^\s*[-*]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", lines[i]).strip())
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        # 分隔线
        if re.match(r"^\s*(---+|\*\*\*+)\s*$", line):
            flush_para()
            out.append("<hr>")
            i += 1
            continue
        # 空行 -> 段落结束
        if not line.strip():
            flush_para()
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Frontmatter 解析（YAML 子集：标量 / 字符串列表 / q-a 对象列表）
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
        if not line.strip():
            i += 1
            continue
        if re.match(r"^\s*-\s", line) and "faq" not in meta:
            meta.setdefault("_list_extra", []).append(line.strip()[1:].strip())
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][\w]*):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if not val:
            # 列表开始
            if key in ("faq", "sources"):
                items = []
                i += 1
                while i < len(lines) and re.match(r"^\s*-\s", lines[i]):
                    item_line = lines[i].strip()[1:].strip()
                    if key == "faq":
                        q = a = ""
                        if ":" in item_line:
                            q = item_line.split(":", 1)[1].strip().strip("\"'")
                        # 读取 a: 子行
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
# 工具
# ---------------------------------------------------------------------------
def slugify(s):
    s = re.sub(r"[^\w\u4e00-\u9fa5-]+", "-", str(s)).strip("-")
    return s or "article"


def read_css(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        return f.read()


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# 文章页渲染
# ---------------------------------------------------------------------------
def render_article(article_dir, meta, body_html, css, week_label, brand="WPS 官网资讯"):
    title = meta.get("title", "")
    kw = meta.get("keyword", "")
    group = meta.get("group", "")
    meta_title = meta.get("meta_title") or title
    meta_desc = meta.get("meta_desc") or ""
    date = meta.get("date") or _date.today().strftime("%Y-%m-%d")
    cover = meta.get("image", "")
    faq = meta.get("faq") or []
    sources = meta.get("sources") or []

    # FAQ
    faq_html = ""
    if faq:
        items = []
        for n, f in enumerate(faq, 1):
            q = f.get("q", "")
            a = inline(f.get("a", ""))
            items.append(
                f'<div class="faq-item"><button class="faq-q" aria-expanded="false">'
                f'<span class="faq-no">{n}</span>{esc(q)}<span class="faq-icon">+</span></button>'
                f'<div class="faq-a"><p>{a}</p></div></div>')
        faq_html = (
            '<section class="faq" id="faq"><h2>常见问题（FAQ）</h2>'
            + "".join(items) + "</section>")

    # 正文页精简：不渲染组别 tab/标题/日期/参考来源，直接图文（标题由 CMS Title 字段管理）
    cover_html = f'<figure class="cover"><img src="{esc(cover)}" alt="{esc(title)}"></figure>' if cover else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(meta_title)}</title>
<meta name="description" content="{esc(meta_desc)}">
<meta name="keywords" content="{esc(kw)}">
<meta property="og:title" content="{esc(meta_title)}">
<meta property="og:description" content="{esc(meta_desc)}">
<style>{css}</style>
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <a class="logo" href="../index.html">{esc(brand)}</a>
    <nav class="nav"><a href="../index.html">本周文章</a><a href="#faq">FAQ</a></nav>
  </div>
</header>
<div class="wrap">
<article class="post">
  {cover_html}
  <div class="post-body">
{body_html}
  </div>
  {faq_html}
</article>
</div>
<footer class="site-footer">
  <div class="wrap"><p>© {_date.today().year} WPS Office · 本页为 SEO 图文稿（{week_label}）</p></div>
</footer>
<script>
document.querySelectorAll('.faq-q').forEach(function(btn){{
  btn.addEventListener('click', function(){{
    var a = this.nextElementSibling;
    var open = a.style.maxHeight && a.style.maxHeight !== '0px';
    document.querySelectorAll('.faq-a').forEach(function(x){{x.style.maxHeight='0';x.style.padding='0 18px';}});
    document.querySelectorAll('.faq-q').forEach(function(x){{x.setAttribute('aria-expanded','false');x.querySelector('.faq-icon').textContent='+';}});
    if(!open){{a.style.maxHeight=a.scrollHeight+'px';a.style.padding='0 18px 16px';this.setAttribute('aria-expanded','true');this.querySelector('.faq-icon').textContent='−';}}
  }});
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 索引页渲染
# ---------------------------------------------------------------------------
def render_index(articles, css, week_label, brand="WPS 官网资讯"):
    groups_order = ["下载安装", "价格购买", "对比选择", "模板获取", "格式转换",
                    "故障解决", "教程操作", "功能认知", "AI认知", "品牌直达"]
    by_group = {}
    for a in articles:
        by_group.setdefault(a["group"], []).append(a)
    blocks = []
    for g in groups_order:
        if g not in by_group:
            continue
        items = "".join(
            f'<li class="card"><a href="{a["slug"]}/index.html"><h3>{esc(a["title"])}</h3>'
            f'<p>{esc(a.get("keyword",""))} · {esc(a.get("date",""))}</p></a></li>'
            for a in by_group[g])
        blocks.append(f'<section class="group"><h2>{esc(g)}</h2><ul class="cards">{items}</ul></section>')
    total = len(articles)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{week_label} · WPS SEO 文章目录</title>
<style>{css}</style>
</head>
<body>
<header class="site-header">
  <div class="wrap"><a class="logo" href="#">{esc(brand)}</a>
  <nav class="nav"><span class="cur">{week_label}</span></nav></div>
</header>
<div class="wrap">
<section class="index-hero">
  <h1>{week_label}</h1>
  <p>共 {total} 篇 · 覆盖 10 个策略组别 · 风格：CMS 独立站 · 官方口吻</p>
</section>
{''.join(blocks)}
</div>
<footer class="site-footer"><div class="wrap"><p>© {_date.today().year} WPS Office · SEO 图文稿</p></div></footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="WPS SEO 周度文章 · HTML 图文渲染")
    ap.add_argument("--articles-dir", required=True, help="文章目录（内含 <slug>/article.md）")
    ap.add_argument("--out", help="输出目录（默认与 --articles-dir 相同）")
    ap.add_argument("--css", help="CSS 模板路径（默认技能 assets/template/article.css）")
    ap.add_argument("--week-label", default=None, help="周标签，如 第3周（默认取目录名）")
    args = ap.parse_args()

    articles_dir = args.articles_dir
    if not os.path.isdir(articles_dir):
        sys.exit(f"[错误] 文章目录不存在：{articles_dir}")
    out_dir = args.out or articles_dir
    os.makedirs(out_dir, exist_ok=True)

    # CSS
    css = None
    if args.css:
        css = read_css(args.css)
    if css is None:
        skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        css_candidates = [
            os.path.join(skill_root, "assets", "template", "article.css"),
            os.path.join(articles_dir, "_template.css"),
        ]
        for c in css_candidates:
            if os.path.isfile(c):
                css = read_css(c)
                break
    if css is None:
        css = "body{font-family:'Microsoft YaHei',sans-serif;line-height:1.8;max-width:860px;margin:0 auto;padding:0 16px;color:#333}a{color:#0b6ef2}img{max-width:100%}"
    css = css.replace("{{WEEK}}", "")

    week_label = args.week_label or os.path.basename(os.path.normpath(articles_dir))

    # 遍历文章
    articles = []
    rendered = []
    for md_file in sorted(glob.glob(os.path.join(articles_dir, "*", "article.md"))):
        article_dir = os.path.dirname(md_file)
        slug = os.path.basename(article_dir)
        with open(md_file, "r", encoding="utf-8") as f:
            text = f.read()
        meta, body = parse_frontmatter(text)
        if not meta.get("title") or not meta.get("keyword"):
            print(f"[跳过] 缺少 title/keyword：{md_file}", file=sys.stderr)
            continue
        meta.setdefault("slug", slug)
        meta.setdefault("date", _date.today().strftime("%Y-%m-%d"))
        if not meta.get("meta_desc"):
            plain = re.sub(r"[#*`>\-\|\n]+", " ", body)[:80]
            meta["meta_desc"] = plain.strip()
        body_html = md_to_html(body)
        html = render_article(article_dir, meta, body_html, css, week_label)
        os.makedirs(article_dir, exist_ok=True)
        with open(os.path.join(article_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        articles.append({"title": meta["title"], "keyword": meta["keyword"],
                         "group": meta["group"], "slug": meta["slug"],
                         "date": meta["date"]})
        rendered.append(meta["slug"])
        print(f"[OK] 已生成 {os.path.join(article_dir, 'index.html')}", file=sys.stderr)

    if not articles:
        sys.exit("[错误] 未找到任何 article.md，请检查 --articles-dir")

    # 索引页
    idx_html = render_index(articles, css, week_label)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(idx_html)
    print(f"[OK] 已生成 {os.path.join(out_dir, 'index.html')}", file=sys.stderr)
    print(f"本周共生成 {len(rendered)} 篇文章：{', '.join(rendered)}")


if __name__ == "__main__":
    main()
