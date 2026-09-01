# CHANGELOG

本文记录 wps-seo-weekly-articles 技能的版本变更。每次发布前递增 `VERSION` 并在此追加记录，供订阅者查看更新内容。

## 1.4.0 (2026-09-01)

**资源池数据源切换为金山多维表**：素材采集默认从「WPS资源池」多维表（file_id=Rip7ZFJaJrM9wK93jQop1xyuEZfz4y28u）拉取，剔除原 workbuddy 资源库链接。
- `scripts/fetch_pool.py`：默认数据源改为金山多维表（通过 wps_docs CLI 分页拉取，支持缓存与 `--file-id`/`--sheet-id` 覆盖）；`--pool-url` 降级为回退 JSON 地址（默认留空），workbuddy 引用已全部移除
- 修复：多维表分页 token 以连字符开头（如 `-z`）时被 argparse 误判为选项导致中断，改用 `--page-token=<token>` 等号形式传参，确保全量拉取
- `SKILL.md`：素材采集相关说明同步改为金山多维表（含参数速查 `--file-id`/`--sheet-id`）

## 1.2.1 (2026-08-28)

**新增 CMS 热门标签库**：收录后台文章列表统计的 105 个真实标签（含频次）。
- `references/tag-library.md`：按高频/中频/低频分组的标签参考文档
- `assets/data/tags.json`：结构化标签数据（name + count）
- 自动化打标签时优先从本库挑选，贴合站点现状（style-guide / SKILL 已引用）

## 1.2.0 (2026-08-28)

**智能标签**：文章生成时自动打对应标签。
- 新增文风案例 5《AI 功能全解析：文字、表格、PPT、PDF 都能怎么用（2026新版）》（WPS 官网，assets/examples/case-05*）
- Agent 写作时按文章内容/关键词/组别生成 3-5 个标签，写入 frontmatter `tags`（可参考 CMS 热门标签库：办公效率/表格函数/Excel/PPT/WPS Office/在线文档 等）
- `upload_cms.py`：frontmatter 解析支持 `tags` 列表，上传时自动写入 CMS `Tags` 字段（优先级：frontmatter tags > 关键词 > --tags）
- 说明：CMS 后台“智能标签”为界面功能，OpenAPI 无对应接口；本实现为等价自动打标

## 1.1.3 (2026-08-28)

**修复**：--update 覆盖改用系统命令（robocopy/cp），临时目录清理兼容沙箱限制，避免 Python 删除被拦截导致更新失败。


## 1.1.1 (2026-08-28)

**修复**：更新检测改用 git 权威通道（`git ls-remote` 对比 HEAD）判断，绕开 jsDelivr CDN 缓存延迟导致的漏检；首次运行也对比 VERSION（防止装了旧包不提示）。


## 1.1.0 (2026-08-28)

**机制增强**：加入“自动更新提醒”——每次调用本技能先执行 `update_check.py --force`，GitHub 有新版本时向用户提示并支持一键更新（见 SKILL.md 第 0 步）。
- 工作流新增第 0 步：自动更新检查（24h 缓存，几乎无感）
- 更新检查章节改写为“用户灵犀如何收到更新提醒”
- 版本仓库统一为多技能仓库 `tongxiaoshan1995-dot/wps-seo-skills`


## 1.0.0 (2026-08-27)

首次正式发布，建立 GitHub 版本仓库 + 更新检查机制。

**工作流**：5 步（接收用户关键词 → 采素材 → 写作 → 渲染 → 上传 CMS 草稿箱不发布）。

**正文结构**（参照草稿 2666）：封面图 + 图文 + FAQ；不含组别 tab、H1 标题、日期、参考来源、下载 CTA；标题由 CMS Title 字段管理。

**素材检索**：
- 穷尽检索（全字段 title + targetKeywords + notes + sourceUrl 扫描）
- 来源优先级：WPS官方公众号 > 小绿书 > WPS社区 > WPS客服中心 > WPS学堂，同分再按 P0/P1/P2

**文风**：参考 assets/examples/ 4 篇优质案例（短疑问句连击开头、痛点场景+具体案例、功能价值优先入口收尾、短句短段）；不学文末互动。

**脚本**：
- `fetch_pool.py`：抓资源池 + 穷尽匹配 + 来源优先级排序
- `build_html.py`：渲染 HTML 图文单页（2666 结构）+ 周目录页
- `push_images.py`：git 方式传图到 GitHub 图床 + image-map.json
- `upload_cms.py`：上传 CMS 草稿（Status=0 不发布；封面/正文走图床 URL，CMS 自动转存）
- `update_check.py`：本版本起内置，检查 GitHub 仓库新版本 + 一键更新

**凭证说明**：CMS access_token 与 GitHub PAT 均不落盘，使用方自行在命令行传入。

