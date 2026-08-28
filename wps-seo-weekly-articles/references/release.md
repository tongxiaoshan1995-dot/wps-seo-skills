# 技能发布与订阅更新流程

本技能使用 **GitHub 仓库作为唯一版本源**（single source of truth），实现「维护者发布 → 云端/朋友同步」的版本管理。

- 版本仓库：`https://github.com/tongxiaoshan1995-dot/wps-seo-weekly-articles`（分支 `main`）
- 仓库内容：技能全部源文件 + `VERSION`（版本号）+ `CHANGELOG.md`（更新记录）
- 更新检查脚本：`scripts/update_check.py`（经 jsDelivr CDN 读远程 VERSION，git 拉取更新）

---

## 角色与三份副本

| 角色 | 位置 | 说明 |
|---|---|---|
| **维护者开发副本** | 本地工作区 `wps-seo-weekly-articles/`（已 `git init`） | 改技能在这里，改完 push 到 GitHub |
| **GitHub 版本仓库** | 远端 `main` 分支 | 唯一版本源，发布即 push |
| **维护者灵犀已安装副本** | `user_skills/wps-seo-weekly-articles/` | 灵犀实际调用的那份，改完同步/重装 |
| **云端已部署** | 灵犀「我的技能—云端管理」 | 上传到云端的那份，供分享下载 |
| **订阅者（朋友）本地副本** | 朋友自己的 `user_skills/` | 通过 `update_check.py --update` 同步 |

---

## 一、维护者：发布新版本

```bash
# 1. 修改技能内容（在工作区开发副本上）
# 2. 递增版本号（如 1.0.0 -> 1.1.0）
#    编辑 VERSION 文件，写入新版本号
# 3. 在 CHANGELOG.md 顶部追加本次变更说明
# 4. 提交并推送
cd wps-seo-weekly-articles
git add -A
git -c user.name="你的名字" -c user.email="你的邮箱" commit -m "v1.1.0: 本次变更摘要"
git push origin main
```

> 首次推送前需仓库存在且本地有凭据（Windows 凭据管理器或 `git push https://<TOKEN>@github.com/...`）。

发布后，云端与朋友的技能即"发现新版本"。

## 二、维护者：云端那份也要更新

GitHub 推送后，灵犀云端不会自动同步。请在界面操作一次：

1. 打开 **技能 → 我的技能**
2. 找到 `wps-seo-weekly-articles` → 点击 **... → 上传到云端**（覆盖旧版本）
3. 完成后云端即与 GitHub 一致

> 云端无法通过脚本更新，只能手动「上传到云端」覆盖。

## 三、订阅者（朋友）：首次安装

```bash
# 1. 下载版本仓库到本地目录（需可访问 github.com）
git clone https://github.com/tongxiaoshan1995-dot/wps-seo-weekly-articles.git <本地目录>
# 或使用脚本：
python <本地目录>/scripts/update_check.py --init <本地目录>

# 2. 在灵犀「技能 → 我的技能」中，从该目录导入安装（本地路径导入）
#    （导入后即拥有当前最新版本）
```

## 四、订阅者：日常更新（收到"更新提示"后）

每次调用技能前建议运行检查（结果缓存 24h，几乎无感）：

```bash
python scripts/update_check.py            # 检查：显示本地/远程版本，有新版会提示
python scripts/update_check.py --update   # 一键更新到最新版（git 拉取覆盖本地技能目录）
```

更新后灵犀需重新加载该技能（重新导入/刷新），新逻辑即生效。

## 五、脚本参数速查

| 参数 | 作用 |
|---|---|
| （无） | 仅检查是否有新版本，结果缓存 24h |
| `--force` | 跳过缓存，强制重新检查 |
| `--update` | 检查并自动更新到最新版 |
| `--init <目录>` | 首次安装：克隆版本仓库到指定目录 |
| `--repo owner/repo` | 覆盖默认远程仓库 |
| `--branch main` | 覆盖默认分支 |

## 六、故障排查

| 现象 | 处理 |
|---|---|
| `远程仓库不可达` | 检查网络能否访问 github.com / cdn.jsdelivr.net；确认仓库存在且分支为 `main` |
| `git clone 失败` | 网络受限时改用 `--repo` 指向可达的镜像仓库，或手动下载 zip 解压覆盖 |
| 更新后技能没变化 | 灵犀需重新导入/刷新技能目录；确认本地 `VERSION` 已更新 |
| 想回退版本 | 从 CHANGELOG 找到旧版 commit，`git checkout <旧commit> -- <技能目录>` 后重新导入 |

## 七、发布清单（每次发布核对）

- [ ] 本地开发副本测试通过（各脚本可运行）
- [ ] `VERSION` 已递增
- [ ] `CHANGELOG.md` 已追加记录
- [ ] `git push origin main` 成功
- [ ] 云端「上传到云端」已覆盖
- [ ] 已通知订阅者运行 `update_check.py --update`
