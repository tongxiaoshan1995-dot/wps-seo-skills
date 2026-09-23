---
name: wps-lingxi-articles
description: 为 wps.cn 按周批量生成聚焦 **WPS 灵犀** 的 SEO 图文文章并上传 CMS 草稿箱（只存草稿、不发布）。当用户要求"按周生成灵犀SEO文章"、"写用WPS灵犀完成xxx的文章"、"灵犀功能教程"、"生成CMS图文稿"、"SEO文章写作"等时使用。标题可与 WPS 相关，正文聚焦"用 WPS 灵犀完成 xxx"（AI 写作/表格/PPT/PDF/阅读/数据分析等）；素材优先取 WPS资源池 的灵犀/AI 资料，不足再网络搜索；配图取 SEO 图片资源库，次回退资源池原文；按 CMS 独立站风格、官方口吻、500-2000 字撰写，正文结构参照草稿 2666（封面图+图文+FAQ），输出 HTML 并上传 CMS 草稿箱（不发布）。
---

# WPS 灵犀 SEO 周度文章生成

## 概述

按周把**用户提供的关键词**批量写成聚焦 **WPS 灵犀** 的 SEO 图文文章：标题可与 WPS 相关，**正文介绍“用 WPS 灵犀完成 xxx”**（AI 写作、AI 表格、AI 演示、AI PDF、AI 阅读、AI 数据分析等能力的功能介绍与操作教程）；每个策略组别至少 1 篇（默认 10 篇 = 每组 1 篇），每篇输出为 CMS 独立站风格的 HTML 图文单页（正文结构参照草稿 2666：封面图 + 图文 + FAQ，不含组别 tab/标题/日期/参考来源/下载 CTA），并**上传到 CMS 草稿箱（只存草稿，不发布）**。素材优先从 SEO 内容资源池取**灵犀/AI 相关资料**，资源池不足或不可达时自动降级到本地词库 + 网络搜索。

## 输入：本周关键词

**关键词由用户直接提供**，例如"本周写这些词：用WPS灵犀写周报、灵犀AI生成PPT、用灵犀翻译PDF、WPS灵犀AI阅读全文、用灵犀做数据分析……"。

- 用户给词时附带策略组别，按其分组；未注明组别时，按关键词语义归入最匹配的策略组别（10 组定义见 [references/group-mapping.md](references/group-mapping.md)）
- 每个组别保证至少 1 篇：若用户提供的词集中在某几组，其余组别由 AI 依据用户意图或从词库补充，并向用户说明
- **可选兜底**：用户没有现成词表时，才用 `scripts/pick_keywords.py` 自动挑词（按组别 + 指定指标 + 跨周去重）

## 工作流（第 0 步自动更新检查 + 5 步）

### 第 0 步：自动更新检查（每次调用本技能，先执行这一步）

```bash
python scripts/update_check.py
```

- 有 24h 本地缓存，未过期直接读缓存（几乎无感）；如需强制刷新可先删除本地缓存再运行
- **输出“发现新版本 vX.Y.Z”时**：先向用户明确提示「技能有新版本 vX.Y.Z，更新内容：<CHANGELOG 摘要>」，征询是否更新；用户同意后执行 `python scripts/update_check.py --update` 完成更新，并告知已生效（灵犀下次加载即用新版）
- 输出“已是最新”或“远程不可达”（网络异常）时静默继续，不阻塞任务

### 第 1 步：整理本周关键词清单

直接以用户给出的词为准，整理成「策略组别 / 关键词 / 搜索意图」清单并回显给用户确认：

| # | 策略组别 | 关键词 | 搜索意图 |
| --- | --- | --- | --- |

- 每个关键词需确定一个策略组别（按用户指定或语义归类）
- 用户未提供组别时，从词库匹配该词补充搜索意图/价值信息（`--keywords` 手动模式已支持）

### 第 2 步：采集素材（资源池优先，网络搜索补充）

```bash
python scripts/fetch_pool.py --keywords "用WPS灵犀写周报,灵犀AI生成PPT" --group 教程操作 --out 素材匹配.md
```

- 抓取 SEO 内容资源池（默认数据源为**金山多维表「WPS资源池」**，file_id=`cn0esSVVz7sD`，通过 wps_docs CLI 分页拉取；本地缓存于 `.rundata/pool_articles.json`；资源池不可达时可用 `--pool-url` 回退到 JSON 地址）——**优先取灵犀/AI 相关素材**（池内 `AI教程` / `WPS AI` 栏目、含“灵犀”关键词的素材），灵犀素材不足时再覆盖同组其他办公素材
- **穷尽检索**：对全字段（title + targetKeywords + notes + sourceUrl）扫描匹配，不遗漏直接相关素材；打分：`targetKeywords 命中(4/3分) > 全文本命中(3/2.6/2.2分) > 标题包含(2分) > pool/cmsTab 命中组别(1分)`；客服中心来源对故障解决组加权
- **文章检索顺序优先级：WPS学堂 > WPS客服中心 > 小绿书 > WPS官方公众号 > WPS社区**（同分素材按此来源顺序 + P0/P1/P2 降序排列）
- 输出每个关键词的匹配素材（ID/标题/内容池/CMS Tab/优先级/来源/原文链接）
- **对高分素材**：打开 `sourceUrl`（如 bbs.wps.cn）获取原文详情作为写作参考（原文只作参考，须用自己的话重写并在 sources 注明）
- **无匹配素材或资源池不可达**：改用网络搜索补充（官方文档、客服中心、学堂等），并如实降级
- 组别 → 资源池字段映射与写作侧重：见 [references/group-mapping.md](references/group-mapping.md)

### 第 3 步：逐篇写作

对每个关键词，按 [references/article-template.md](references/article-template.md) 组织目录、按 [references/style-guide.md](references/style-guide.md) 规范撰写：

- 每篇一个文件夹 `output/第N周/<slug>/`，内含 `article.md`（frontmatter + Markdown 正文）与 `img/`（配图）
- 结构必含：封面图（frontmatter `image`）→ 正文分段（每关键段落配图）→ FAQ（3–5 条）；标题写在 frontmatter（CMS Title 字段管理，标题可与 WPS 相关，如“用WPS灵犀5分钟写完周报”），正文页不渲染标题
- **题材：正文聚焦“用 WPS 灵犀完成 xxx”**——每篇围绕灵犀的一项 AI 能力（AI 写作/表格/演示/PDF/阅读/数据分析等），写清能力价值、适用人群、操作路径（入口+步骤）、可验证的效果；不把灵犀写成万能工具，客观描述能力边界
- **灵犀能力硬性植入（红线）**：无论选题是 WPS 相关还是 AI/通用办公相关，正文都必须植入 WPS 灵犀能力（独立章节或明确段落，不能只文末一句带过）；灵犀能力的表述以资源池多维表（WPS资源池）中灵犀/AI 相关素材的官方描述为准，不得杜撰能力名称、入口路径和效果数据；实在无法自然植入的选题，须在写作前向用户说明并确认
- 风格：CMS 独立站、官方口吻、500–2000 字、严格去 AI 味（逐条对照 style-guide 的检查清单 + **参考 `assets/examples/` 下 4 篇优质案例文风**：短疑问句连击开头、痛点场景+具体案例、功能价值优先入口收尾；不学文末互动）——灵犀题材同样适用，用“写周报太慢？表格公式不会？PDF 翻不过来？”这类痛点开场
- **合规前置自查**：每篇写完后逐条对照 style-guide 第 8 节「禁用清单（发布前红线）」（含夸大 AI 能力、竞品对比、数据出处、会员体系不展开、绝对化用语等），产出即达标，避免发布后返工
- 配图：**一律使用真实产品截图**（禁用 AI 示意图，规范见 style-guide 第 7 节），并遵守以下硬性约束：
  1. **唯一来源**：配图只从 **SEO 图片资源库**（金山多维表「SEO图片资源库」，file_id=`chojYpQQMKYh`，经 `scripts/fetch_images.py` 按关键词匹配）获取；图片库无合适命中时**允许不配图**（宁缺毋滥），不再回退资源池原文提取和 browser 截图兑底；
  2. **匹配度门槛**：图片与文章主题的匹配度需超过 80%（图片描述/标签与关键词及正文主题直接相关）才可使用，低于门槛视为无合适图片；
  3. **数量与位置**：每篇配 1–2 张图；**开头（第一段/封面图之后紧邻的第一屏）不放配图**，图片放在中部操作步骤或效果展示段落；封面图（frontmatter `image`）可从命中图片中选，但不得与正文图重复计算配图数；
  4. **当天去重**：同一天产出的多篇文章之间，配图重复度不超过 20%（即 10 篇中同一张图最多出现 2 次；1–2 图/篇时，优先保证每篇核心配图不与其他篇重复）；fetch_images 按篇分配关键词时须错开，写作前先盘点当天已用图片再选图；
  5. 正文图用 `![alt](img/xxx.jpg)` 引用，alt 含关键词。
- **正文页不含下载 CTA**（结构最终参照草稿 2666：封面图 + 图文 + FAQ）
- **智能标签**：Agent 按文章内容/关键词/组别生成 3-5 个标签，写入 frontmatter `tags`；**优先从 `references/tag-library.md` 的 105 个 CMS 真实热门标签挑选**（结构化数据 `assets/data/tags.json`）；`upload_cms` 自动写入 CMS `Tags` 字段（后台智能标签为界面功能，OpenAPI 不提供，本方案为等价自动打标）

### 第 4 步：渲染 HTML 图文单页

```bash
python scripts/build_html.py --articles-dir output/第3周
```

- 每篇生成 `<slug>/index.html`（自包含单页，内联 CSS，**正文页直接图文：不渲染组别 tab/标题/日期/参考来源/下载 CTA**，结构参照 2666：封面图 + 图文 + FAQ；标题由 CMS Title 字段管理）
- 自动生成周目录页 `output/第3周/index.html`（目录页保留标题/组别/日期用于导航）
- 浏览器打开 `output/第3周/index.html` 即可预览全部图文稿

### 第 5 步：上传 CMS 草稿箱（不发布）

配图方案：外部 GitHub 图床 + jsDelivr CDN（`raw.githubusercontent` 在本网络不可达，用 `cdn.jsdelivr.net`）。

```bash
# 5a. 先把配图上传到 GitHub 图床并生成 URL 映射（需 GitHub PAT）
python scripts/push_images.py --token <PAT> --images-dir output/第3周 --out output/image-map.json
# 5b. 上传草稿（Status=0；正文配图用 --image-map 替换为图床 URL）
python scripts/upload_cms.py --host https://www.wps.cn/article --token <TOKEN> --articles-dir output/第3周 --image-map output/image-map.json
# 预览不上传
python scripts/upload_cms.py --host https://www.wps.cn/article --token <TOKEN> --articles-dir output/第3周 --dry-run
```

- 把每篇文章（`<slug>/index.html` + `img/`）上传到 **CMS 后台的草稿箱/草稿状态**
- **只创建草稿，绝不发布**：发布动作由用户手动完成（实测 wps.cn CMS：SERVER_HOST=`https://www.wps.cn/article`，`Status=0` 即草稿）
- 图片：`push_images.py` 上传 GitHub 图床生成 jsDelivr URL 映射 → `upload_cms.py --image-map` 自动替换正文配图
- 完整接口说明见 [references/cms-upload.md](references/cms-upload.md)；后台界面 `https://www.wps.cn/article/admin#/login` 需登录
- 若 CMS 后台需要登录/验证码，按 browser 技能规则用 `ask_user_question` 征询用户接管
- 完成后向用户汇报：已创建 N 篇草稿（链接列表）、均为草稿未发布

## 自动更新检查机制（用户灵犀如何收到更新提醒）

**核心：技能每次被调用时自动检查 GitHub 版本仓库，有新版本即向用户提示并可一键更新。**（技能无后台推送通道，提醒发生在“调用技能”时，见第 0 步）

- **版本仓库**：`tongxiaoshan1995-dot/wps-seo-skills`（多技能统一仓库，本技能为子目录，SUBDIR 自动适配）
- 手动命令：
  ```bash
  python scripts/update_check.py            # 仅检查
  python scripts/update_check.py --update   # 一键更新
  python scripts/update_check.py --init <目录>  # 首次安装克隆
  ```
- **维护者每次发布**：递增 `VERSION` → `CHANGELOG.md` 追加记录 → `git commit && git push` →（云端已部署那份再“上传到云端”覆盖一次）
- 发布/订阅完整流程见 `references/release.md`

## 快速开始

```bash
# 1. 关键词由用户提供（直接录入清单）
# 2. 采集素材
python scripts/fetch_pool.py --keywords "关键词1,关键词2" --out 素材匹配.md
# 3-4. 写作（agent 逐篇撰写）+ 渲染
python scripts/build_html.py --articles-dir output/第3周
# 5. 上传 CMS 草稿箱（不发布）——见 references/cms-upload.md
```

## 参数速查

| 脚本 | 关键参数 | 说明 |
| --- | --- | --- |
| fetch_pool.py | `--keywords`,`--group` | 直接给关键词（用户提供）/ 统一分组 |
| | `--kw-file` | 从关键词清单 .md 读取 |
| | `--file-id` / `--sheet-id` | 金山多维表文件 ID（默认 WPS资源池 `cn0esSVVz7sD`）/ sheet ID |
| | `--pool-url` / `--data` | 回退资源池 JSON 地址（默认不用）/ 数据文件路径 |
| | `--cache` / `--refresh` | 本地缓存 / 强制刷新 |
| | `--out` | 导出素材匹配 .md |
| build_html.py | `--articles-dir` | 文章目录（含各 `<slug>/article.md`） |
| | `--css` / `--out` | 自定义 CSS / 输出目录 |
| upload_cms.py | `--host` / `--token` | CMS SERVER_HOST（`https://www.wps.cn/article`）/ OpenAPIToken |
| | `--status` | 草稿状态值（实测 `0`=草稿） |
| | `--image-map` / `--no-images` | 图床 URL 映射（json）/ 跳过图片上传 |
| | `--dry-run` | 试运行，不真正上传 |
| fetch_images.py | `--urls` / `--source-type` | 素材原文链接列表 / 对应来源类型（WPS学堂/社区/客服中心/公众号/小绿书） |
| | `--keywords` / `--img-file-id` / `--img-sheet-id` | 按关键词优先匹配 **SEO 图片资源库**（默认 `chojYpQQMKYh`）/ 图片库 file_id / sheet ID |
| | `--keywords` / `--pool-file` | 按关键词从资源池自动找素材（配合 fetch_pool 输出） |
| | `--out` / `--prefix` / `--limit` | 输出目录 / 下载前缀 / 每 URL 最多图数 |
| | `--dry-run` | 只列候选不下载 |
| push_images.py | `--token` / `--images-dir` | GitHub PAT / 周目录（含各 `<slug>/img/`） |
| | `--repo` / `--branch` | 图床仓库 owner/repo / 分支（默认 main） |
| | `--out` / `--dry-run` | 生成 image-map.json / 试运行 |
| pick_keywords.py（可选） | `--count` / `--per-group` | 自动挑词：总数（默认10，每组≥1）/ 每组固定数 |
| | `--metric 列名` | 排序指标（GEO机会值等） |
| | `--keywords`,`--group` | 手动指定关键词/分组 |
| | `--week N` / `--reset` | 指定周次 / 清空去重历史 |

## 资源

### scripts/
- `pick_keywords.py` — 从词库按 10 组别 + 指定指标挑词、跨周去重（**仅用户没有现成词表时兜底用**）
- `fetch_pool.py` — 抓取 SEO 内容资源池并按关键词穷尽匹配素材（全字段扫描；来源优先级 WPS官方公众号>小绿书>WPS社区>WPS客服中心>WPS学堂）
- `fetch_images.py` — 获取真实产品截图：**优先按关键词匹配 SEO 图片资源库**（取现成稳定图床链接），无命中回退从 WPS资源池 素材原文提取（按来源优先级选素材，自动过滤头像/图标/SVG 并处理防盗链；抓不到提示 browser 截图兑底）
- `build_html.py` — 把文章渲染为 HTML 图文单页 + 周目录页
- `push_images.py` — 把配图上传 GitHub 图床并生成 jsDelivr URL 映射（image-map.json）
- `upload_cms.py` — 把渲染好的文章上传为 CMS 草稿（不发布，配图走图床 URL）

### references/
- `group-mapping.md` — 10 策略组别 → 词库/资源池字段/落地页/写作侧重映射，及**组别 → 内容策略模板映射表**（写作前必读）
- `style-guide.md` — CMS 独立站风格、官方口吻、去 AI 味检查清单、**内容策略三档（高/中/低关联）写作要点**、FAQ/配图规范、正文页 2666 结构、优质案例文风参考（写作时必读）
- `article-template.md` — 文章目录与 frontmatter 约定、**正文结构骨架三套模板（A高关联/B中关联/C低关联）**、渲染方法（写作时必读）
- `cms-upload.md` — 上传 CMS 草稿箱的平台与操作说明（按用户指定平台维护）

### assets/
- `template/article.css` — 文章 HTML 页样式模板（build_html 自动内联）
- `data/wps_final_kw.csv` — 词库（12166 词，内置兜底）
- `examples/` — 优质案例原文 4 篇（文风参考语料，写作前通读）
