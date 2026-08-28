# 文章结构与渲染约定

写作完成后由 `scripts/build_html.py` 渲染成 HTML 图文单页。先按本文件组织每篇文章的文件夹与内容。

## 目录约定

```
output/第N周/
├── index.html                # 周目录页（build_html 自动生成）
└── <slug>/
    ├── article.md            # frontmatter + Markdown 正文（手写）
    ├── index.html            # 本篇文章页（build_html 自动生成）
    └── img/                  # 本篇文章配图
```

## article.md frontmatter

```markdown
---
title: "一篇能解决××问题的标题（含关键词）"
keyword: "本周关键词"
tags:                     # 智能标签：Agent 按文章内容/关键词/组别生成 3-5 个，upload 时自动写入 CMS Tags 字段
  - "标签1"
  - "标签2"
  - "标签3"
group: "教程操作"            # 10 组之一：下载安装/价格购买/对比选择/模板获取/格式转换/故障解决/教程操作/功能认知/AI认知/品牌直达
meta_title: "SEO 标题（可不填，默认取 title）"
meta_desc: "SEO 描述，80 字内（可不填，自动截取正文）"
date: "2026-08-27"        # 仅内部记录，正文页不渲染日期
image: "img/cover.jpg"        # 封面主图（可不填）
faq:
  - q: "问题一"
    a: "直接给结论的回答。"
  - q: "问题二"
    a: "先结论后依据。"
sources:
  - "https://bbs.wps.cn/topic/xxxx"   # 仅内部溯源，正文页文末不渲染参考来源
---

正文 Markdown 从这里开始……
```

## 正文结构骨架（按组别微调）

> 正文页（CMS Content）渲染时**不含组别 tab、不含 H1 标题、不含日期、文末不含参考来源、不含下载 CTA**（结构最终参照草稿 2666），直接图文；标题由 CMS Title 字段管理。

```markdown
# 开头：3 句内抓人（给结论 / 数字 / 痛点场景），自然带出关键词与本文要解决的问题

## 这块内容是什么 / 解决什么问题
（功能认知、品牌直达侧重；一句话讲清价值与适用人群）

## 具体怎么做（分步 + 配图）
（教程操作、格式转换、故障解决侧重；每步配 img/ 截图）

## 用 X 场景对比 / 如何选择
（对比选择、价格购买侧重；客观表格对比，不贬低对手）

## 常见疑问（正文内先答 1–2 条，展开的放 FAQ）

## 小结
（3–5 句收束 + 引导下一步动作）
```

## 配图插入

配图**一律使用真实产品截图**（来源与取图步骤见 style-guide 第 7 节：先用 `scripts/fetch_images.py` 从资源池素材原文提取，提取不到用 browser 截图兑底，禁用 AI 示意图）。

正文中直接使用相对路径引用：

```markdown
![WPS 表格如何冻结前两行](img/freeze-pane.png)
```

- 封面图在 frontmatter `image` 字段声明，渲染为文章头图。
- 关键段落图放正文，渲染在对应标题下方。

## 渲染调用

```bash
python scripts/build_html.py --articles-dir output/第3周
```

- 每篇输出 `<slug>/index.html`（自包含单页，内联 CSS），周目录输出 `index.html`。
- 浏览器直接打开 `index.html` 即可预览完整图文效果。

## 上传 CMS 草稿箱（不发布）

- 把每篇 `<slug>/` 整目录（`index.html` + `img/`）上传到 CMS 后台的草稿箱/草稿状态，**只存草稿、不发布**。
- 平台与操作方式见 `references/cms-upload.md`。
