# WPS SEO Skills（多技能版本仓库）

本仓库是 WPS SEO 相关灵犀技能的统一版本源（single source of truth）。一个仓库管理多个技能，各自独立维护版本（`VERSION` / `CHANGELOG.md`）。

## 仓库结构

```
wps-seo-skills/
├── wps-seo-weekly-articles/    # 按周批量生成 WPS SEO 图文文章并上传 CMS 草稿箱
├── wps-seo-weekly-keywords/    # 按周输出 WPS SEO 组别关键词规划
└── README.md
```

新增技能：在仓库根下新建技能目录（含 `SKILL.md` + `VERSION` + `CHANGELOG.md` + `scripts/update_check.py`，复制现有技能的 `update_check.py` 即可，`SUBDIR` 会自动取目录名）。

## 更新机制

每个技能内置 `scripts/update_check.py`，经 jsDelivr CDN 读取本仓库中该技能子目录的 `VERSION` 对比本地版本：

```bash
python scripts/update_check.py            # 检查是否有新版本（结果缓存 24h）
python scripts/update_check.py --update   # 一键更新到最新版
python scripts/update_check.py --init <目录>  # 首次安装：克隆仓库到指定目录
```

## 订阅者（朋友）使用

1. 克隆仓库：`git clone https://github.com/tongxiaoshan1995-dot/wps-seo-skills.git`
2. 在灵犀「技能 → 我的技能」中从对应技能目录本地导入安装
3. 每次更新：运行该技能下的 `python scripts/update_check.py --update`

## 维护者发布

1. 修改对应技能内容
2. 递增该技能 `VERSION`，在 `CHANGELOG.md` 追加记录
3. `git add -A && git commit -m "vX.Y.Z: 变更摘要" && git push origin main`
4. 云端已部署的那份再「上传到云端」覆盖一次
5. 通知订阅者运行 `update_check.py --update`

详见各技能 `references/release.md`。
