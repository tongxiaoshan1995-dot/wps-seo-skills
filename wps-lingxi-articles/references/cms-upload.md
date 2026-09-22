# 上传 CMS 草稿箱（不发布）

目标：把每周渲染好的 HTML 图文单页上传到 wps.cn 文章 CMS 的**草稿箱/草稿状态**，**只存草稿，不发布**（发布由用户手动完成）。

## 接口概要（来源：CMS Open API 文档 open-api.md + 实测）

- **实测 SERVER_HOST = `https://www.wps.cn/article`**，接口基础路径为 `https://www.wps.cn/article/api`（不是 www.wps.cn/api，后者 404）
- 认证：API 接口通过 **`access_token` 参数**传递 `OpenAPIToken`，无 token 返回 401；**图片上传接口除外**（见下）
- 参数命名：publish/category/tag 接口支持 PascalCase 与 snake_case 两种命名，响应为 PascalCase
- **实测草稿状态值 = `0`**（publish 的 `Status` 传 0 即创建草稿；列表接口 status 0=草稿, 1=已发布）

### 关键接口

| 接口 | 方法/路径 | 说明 |
| --- | --- | --- |
| 发布/更新文章 | `POST /api/article/publish` | 核心：创建或更新文章（含草稿） |
| 上传图片 | `POST /article/manage/file/upload` | **需要后台登录 Cookie**（OpenAPI token 不适用，401）；form 传 `file`，query 传 `space`；限 PNG/JPEG/GIF/WebP ≤500KB |
| 分类列表 | `GET /api/category/list` | 文章模块下的分类（拿 CateID） |
| 标签列表 | `GET /api/tag/list` | 标签（按名称匹配/创建） |
| 作者列表 | `GET /api/author/list` | 作者 |
| 文章列表 | `GET /api/article/` | 支持 `status`（**0=草稿, 1=已发布**）、`title` 模糊搜索，用于校验草稿 |
| 文章详情 | `GET /api/article/{id}` | 按 id/slug 查单篇 |

### `POST /api/article/publish` 请求体（OpenPublishArticleReq）

| 字段 | 别名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | `id` | int? | — | 传入则更新已有文章 |
| `Title` | `title` | str | ✓ | 标题 |
| `Type` | `type` | any | — | 类型 |
| `Content` | `content` | str | ✓ | 正文 HTML |
| `CateID` | `cate_id` | int | ✓ | 分类 ID（从 /category/list 获取） |
| `Status` | `status` | ArticleStatus? | — | 默认 PUBLISH；**草稿需传 DRAFT/0**（见下） |
| `Author` | `author` | str? | — | 作者名 |
| `ModuleIDList` | `module_id_list` | int[] | — | 关联模块 ID |
| `Image` | `image` | str? | — | 封面图 URL（先用 /file/upload 上传得到） |
| `Tags` | `tags` | str[] | — | 标签列表 |
| `SeoTitle` | `seo_title` | str? | — | SEO 标题 |
| `SeoBrief` | `seo_brief` | str? | — | SEO 描述 |

> 草稿状态取值待实测确认：列表接口用 `status=0` 表示草稿；publish 的 `Status` 字段文档标注默认 `PUBLISH`，草稿一般传 `DRAFT` 或 `0`，脚本用 `--status` 可配，默认先试 `DRAFT`。

## 上传流程（由 scripts/upload_cms.py 执行）

1. 读取周目录下各 `<slug>/article.md`（frontmatter：title/keyword/group/meta_title/meta_desc/image/faq）+ 已渲染的 `<slug>/index.html`
2. 拉取分类列表（`/article/api/article/category/list`，9 分类：office/word/Excel/PPT/PDF/在线文档/WPS AI/WPS教程/行业知识），把组别/关键词映射到分类（CateID）
3. 上传封面图与正文配图（`POST /article/manage/file/upload`，需 `--cookie` 后台登录凭证），把正文相对图片路径替换为绝对 URL；无凭证可用 `--no-images` 跳过（发布前补图）
4. 组装正文 HTML（取 `.post` 区块：正文 + FAQ），调 `POST /article/api/article/publish` 创建**草稿**（`Status=0`）
5. 校验：`GET /article/api/article/{id}` 确认草稿已创建

## 实测记录

- `POST /article/api/article/publish` + `Status=0` 创建草稿成功（响应含 id/link）
- 图片上传 `/article/manage/file/upload` 返回 401，需后台登录态（`Bearer` 与 `access_token` 均无效）
- 后台管理界面 `https://www.wps.cn/article/admin#/login` 需账号密码登录
- **关键发现：CMS 会自动把正文中的外部图片 URL 抓取转存到自己服务器（`/article/manage/file/{id}`）**——因此配图只要以可访问的 URL 放进 content（如 GitHub 图床 + jsDelivr），CMS 发布/草稿保存时会自动托管，无需后台上传接口
- 已验证：jsDelivr URL 图片经 publish 后转存为 CMS 自身地址且可访问（200）
- 转存可能额外附带 CMS 默认图（如 PC.png），不影响正文配图

## 图片方案（外部图床 + jsDelivr）

1. `push_images.py --token <PAT> --images-dir <周目录>` 把 `img/` 图片推到 GitHub 图床仓库，生成 image-map.json（键=相对周目录路径，值=`https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{路径}`）
2. `upload_cms.py --image-map image-map.json` 创建草稿时自动把正文相对图片替换为图床 URL，CMS 端自动转存托管
- 图床仓库：`tongxiaoshan1995-dot/wps-seo-images`（main），jsDelivr 在本网络可达，`raw.githubusercontent.com` 不可达
- 建议生产环境将图片压缩到 500KB 内再上传图床（减小体积、加快加载）

## 安全与边界

- `SERVER_HOST` 与 `access_token` 由用户提供，不写入长期记忆；运行时通过参数/环境变量传入
- 只创建草稿，绝不触发发布（Status 恒为 0/草稿）
- 正文页不含下载 CTA（结构参照 2666：封面图 + 图文 + FAQ），下载落地页后续可在 CMS 后台自行补充
- 上传为外部写操作：执行前向用户说明将创建 N 篇草稿；`--dry-run` 可先预览不上传
- 图片上传涉及后台登录态（Cookie），属敏感凭据，不写入长期记忆
