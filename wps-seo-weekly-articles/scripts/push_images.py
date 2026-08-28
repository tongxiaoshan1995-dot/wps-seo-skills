#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · 图片上传 GitHub 图床 + 生成 jsDelivr URL 映射
================================================================
把周目录（output/第N周/）下各文章的 img/ 图片上传到 GitHub 图床仓库，
生成 image-map.json（键=相对周目录路径，值=jsDelivr CDN URL），
供 upload_cms.py --image-map 使用（正文配图自动替换为图床链接）。

上传方式：默认 git push（走 github.com，本网络更稳定）；可 --method api 用 GitHub Contents API。
URL 形式：https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{相对路径}

用法示例：
    python push_images.py --token <PAT> --images-dir output/第3周 --out output/image-map.json
    python push_images.py --token <PAT> --images-dir output/第3周 --repo owner/repo --branch main
    python push_images.py --token <PAT> --images-dir output/第3周 --dry-run    # 只预览不上传
    python push_images.py --token <PAT> --images-dir output/第3周 --method api # 改用 Contents API
"""
import argparse
import base64
import glob
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_REPO = "tongxiaoshan1995-dot/wps-seo-images"
DEFAULT_BRANCH = "main"
IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def collect_images(images_dir):
    files = []
    for ext in IMG_EXTS:
        files += glob.glob(os.path.join(images_dir, "*", "img", f"*{ext}"))
        files += glob.glob(os.path.join(images_dir, "*", "*", f"*{ext}"))
    seen = set()
    out = []
    for f in sorted(files):
        if f in seen:
            continue
        seen.add(f)
        out.append(f)
    return out


def run(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.exit(f"[错误] 命令失败：{' '.join(cmd)}\n{r.stderr[:500]}")
    return r


def push_by_git(owner, repo, token, branch, images_dir, rel_files, prefix):
    """git 方式：临时浅克隆仓库 → 复制图片 → commit → push。"""
    tmp = tempfile.mkdtemp(prefix="wpsimg_")
    repo_dir = os.path.join(tmp, "repo")
    run(["git", "clone", "--depth", "1", "-b", branch,
         f"https://github.com/{owner}/{repo}.git", repo_dir])
    for rel in rel_files:
        src = os.path.join(images_dir, rel)
        dst = os.path.join(repo_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as f, open(dst, "wb") as g:
            g.write(f.read())
        print(f"  [复制] {rel}")
    subprocess.run(["git", "-C", repo_dir, "add", "-A"], check=True, capture_output=True)
    # 用临时身份提交（避免依赖全局 user.name/email 配置）
    subprocess.run(["git", "-C", repo_dir, "-c", "user.name=wps-seo-images",
                    "-c", "user.email=wps-seo-images@users.noreply.github.com",
                    "commit", "-m", "add wps seo images"],
                   check=True, capture_output=True)
    push_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    subprocess.run(["git", "-C", repo_dir, "push", push_url, branch],
                   check=True, capture_output=True, timeout=180)
    print("  [OK] git push 成功")


def push_by_api(owner, repo, token, branch, images_dir, rel_files, prefix, force=False):
    import requests
    for rel in rel_files:
        repo_path = f"{prefix}/{rel}" if prefix else rel
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{repo_path}"
        headers = {"Authorization": f"token {token}",
                   "Accept": "application/vnd.github+json", "User-Agent": "wps-seo-images"}
        # 检查是否已存在；覆盖时需带旧文件 sha
        r = requests.get(url, headers=headers, timeout=60)
        sha = None
        if r.status_code == 200:
            sha = (r.json() or {}).get("sha")
            if not force:
                print(f"  [跳过] {rel} 已存在")
                continue
        with open(os.path.join(images_dir, rel), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        body = {"message": f"add {repo_path}", "content": content, "branch": branch}
        if sha:
            body["sha"] = sha
        r2 = requests.put(url, json=body, headers=headers, timeout=120)
        if r2.status_code in (200, 201):
            print(f"  [OK] {rel}")
        else:
            print(f"  [失败] {rel} HTTP {r2.status_code}: {r2.text[:200]}")


def main():
    ap = argparse.ArgumentParser(description="WPS SEO 周度文章 · 图片上传 GitHub 图床")
    ap.add_argument("--token", required=True, help="GitHub PAT（repo 权限）")
    ap.add_argument("--images-dir", required=True, help="周目录（含各 <slug>/img/* 图片）")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"仓库 owner/repo（默认 {DEFAULT_REPO}）")
    ap.add_argument("--branch", default=DEFAULT_BRANCH, help=f"分支（默认 {DEFAULT_BRANCH}）")
    ap.add_argument("--prefix", default="", help="仓库内路径前缀（可选，如 seo/）")
    ap.add_argument("--out", default="", help="image-map.json 输出路径（默认 <images-dir>/image-map.json）")
    ap.add_argument("--method", default="git", choices=["git", "api"], help="上传方式（默认 git，更稳定）")
    ap.add_argument("--force", action="store_true", help="已存在的同名图片也覆盖上传")
    ap.add_argument("--dry-run", action="store_true", help="试运行：打印将上传的图片与 URL，不真正上传")
    args = ap.parse_args()

    owner, repo = args.repo.split("/") if "/" in args.repo else (args.repo, args.repo)
    images_dir = os.path.abspath(args.images_dir)
    images = collect_images(images_dir)
    if not images:
        sys.exit(f"[错误] {images_dir} 下未找到图片（<slug>/img/*.png 等）")
    print(f"[数据] 待上传图片 {len(images)} 张（{args.repo}@{args.branch}，方式={args.method}）")

    prefix = args.prefix.strip("/")
    image_map = {}
    rel_files = []
    for img in images:
        rel = os.path.relpath(img, images_dir).replace("\\", "/")
        rel_files.append(rel)
        repo_path = f"{prefix}/{rel}" if prefix else rel
        url = f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{args.branch}/{repo_path}"
        image_map[rel] = url
        print(f"  - {rel}  ->  {url}")

    if not args.dry_run:
        if args.method == "git":
            push_by_git(owner, repo, args.token, args.branch, images_dir, rel_files, prefix)
        else:
            push_by_api(owner, repo, args.token, args.branch, images_dir, rel_files, prefix, force=args.force)

    out_path = args.out or os.path.join(images_dir, "image-map.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(image_map, f, ensure_ascii=False, indent=2)
    print(f"\n[已导出] {out_path}（{len(image_map)} 条映射）")


if __name__ == "__main__":
    main()
