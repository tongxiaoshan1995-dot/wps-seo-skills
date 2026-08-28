# CHANGELOG

本文记录 wps-seo-weekly-articles 技能的版本变更。每次发布前递增 `VERSION` 并在此追加记录，供订阅者查看更新内容。

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
