#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wps-seo-weekly-articles 技能：版本更新检查 / 一键更新。

用法:
  python scripts/update_check.py              # 仅检查是否有新版本（结果缓存 24h）
  python scripts/update_check.py --force      # 跳过缓存，强制重新检查
  python scripts/update_check.py --update     # 检查 + 自动更新到最新版
  python scripts/update_check.py --init       # 首次安装：把版本仓库克隆到当前目录（朋友装机用）
  python scripts/update_check.py --repo owner/repo --branch main   # 覆盖默认远程配置

原理:
  - 远程仓库保存技能全部源文件 + VERSION（如 1.0.0）+ CHANGELOG.md
  - 检查：经 jsDelivr CDN 读取远程 VERSION，与本地 VERSION 对比（jsDelivr 失败时回退 git clone）
  - 更新：git clone --depth 1 拉取远程最新，覆盖本地技能目录（保留 .rundata / __pycache__ 等运行态）
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# ---------- 默认远程配置 ----------
OWNER = "tongxiaoshan1995-dot"
REPO = "wps-seo-weekly-articles"
BRANCH = "main"

# 技能根目录 = 本脚本的上级目录（scripts/ 的父目录）
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 本技能在版本仓库内的子目录（多技能共用一个仓库；仓库根直接放本技能时为空）
SUBDIR = os.path.basename(SKILL_DIR)
CACHE_DIR = os.path.join(SKILL_DIR, ".rundata")
CACHE_FILE = os.path.join(CACHE_DIR, "update_cache.json")
CACHE_TTL = 24 * 3600  # 检查结果缓存 24 小时，避免每次调用都慢

JS_DELIVR = "https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}"
GITHUB_GIT = "https://github.com/{owner}/{repo}.git"

# 本地运行态 / 本地版本控制：更新时保留、不被远程覆盖
KEEP_LOCAL = {".rundata", "__pycache__", ".git"}


def log(msg):
    print(msg, flush=True)


def err(msg):
    print(f"[错误] {msg}", file=sys.stderr, flush=True)


# ---------- 版本 ----------
def read_local_version():
    p = os.path.join(SKILL_DIR, "VERSION")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            v = f.read().strip()
        if re.match(r"^\d+\.\d+\.\d+", v):
            return v
    return "0.0.0"


def parse_version(v):
    nums = re.findall(r"\d+", v or "")[:3]
    return tuple(int(x) for x in nums) or (0, 0, 0)


def is_newer(remote, local):
    return parse_version(remote) > parse_version(local)


# ---------- 远程读取 ----------
def fetch_remote_version(owner, repo, branch):
    """经 jsDelivr 读远程 VERSION（多技能仓库下带 SUBDIR 子路径）；失败回退 git clone。返回 (version, source)。"""
    rel = f"{SUBDIR}/VERSION" if SUBDIR else "VERSION"
    url = JS_DELIVR.format(owner=owner, repo=repo, branch=branch, path=rel)
    try:
        import requests
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            v = r.text.strip()
            if re.match(r"^\d+\.\d+\.\d+", v):
                return v, "jsDelivr"
    except Exception:
        pass

    # 回退：先快速探测仓库是否存在，再浅克隆读 VERSION
    git_url = GITHUB_GIT.format(owner=owner, repo=repo)
    try:
        subprocess.check_call(["git", "ls-remote", git_url, "HEAD"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except Exception:
        log("  [提示] 远程仓库不可达（jsDelivr 404 且 git ls-remote 失败），请检查仓库地址与网络。")
        return None, None
    tmp = tempfile.mkdtemp(prefix="wps-skill-check-")
    try:
        subprocess.check_call(["git", "clone", "--depth", "1", "-b", branch, git_url, tmp],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        src = os.path.join(tmp, SUBDIR) if SUBDIR else tmp
        p = os.path.join(src, "VERSION")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                v = f.read().strip()
            if re.match(r"^\d+\.\d+\.\d+", v):
                return v, "git"
    except Exception as e:
        log(f"  [提示] git 回退读取失败: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None, None


def fetch_changelog_head(owner, repo, branch, n=4):
    """读远程 CHANGELOG.md 开头 n 行（jsDelivr 快速通道）。"""
    rel = f"{SUBDIR}/CHANGELOG.md" if SUBDIR else "CHANGELOG.md"
    url = JS_DELIVR.format(owner=owner, repo=repo, branch=branch, path=rel)
    try:
        import requests
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            lines = [ln for ln in r.text.splitlines() if ln.strip()][:n]
            return "\n".join(lines)
    except Exception:
        pass
    return None


# ---------- 缓存 ----------
def read_cache():
    if os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def write_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


# ---------- 检查 ----------
def check(force=False):
    now = time.time()
    cache = read_cache()
    if not force and cache and cache.get("checked_at", 0) > now - CACHE_TTL:
        render(cache, cached=True)
        return cache

    local = read_local_version()
    remote, src = fetch_remote_version(OWNER, REPO, BRANCH)
    if remote is None:
        err("无法连接远程仓库，请检查网络后重试（VERSION 经 jsDelivr / git 读取均失败）。")
        sys.exit(1)

    cache = {
        "checked_at": now,
        "local": local,
        "remote": remote,
        "has_update": is_newer(remote, local),
        "source": src,
    }
    write_cache(cache)
    render(cache, cached=False)
    return cache


def render(cache, cached):
    local, remote, upd = cache["local"], cache["remote"], cache["has_update"]
    tag = "（缓存结果）" if cached else ""
    log(f"[wps-seo-weekly-articles] 当前版本 v{local}，远程最新 v{remote}{tag}")
    if upd:
        log("==> 发现新版本！可运行  python scripts/update_check.py --update  一键更新")
        head = fetch_changelog_head(OWNER, REPO, BRANCH)
        if head:
            log("    更新内容预览：")
            log("\n".join("    " + ln for ln in head.splitlines()))
    else:
        log("==> 已是最新版本，无需更新")


# ---------- 更新 ----------
def update():
    local = read_local_version()
    remote, _ = fetch_remote_version(OWNER, REPO, BRANCH)
    if remote is None:
        err("无法连接远程仓库，更新中止。")
        sys.exit(1)
    if not is_newer(remote, local):
        log(f"已是 v{local}，无需更新。")
        return 0

    log(f"正在从 v{local} 更新到 v{remote} ...")
    tmp = tempfile.mkdtemp(prefix="wps-skill-update-")
    try:
        git_url = GITHUB_GIT.format(owner=OWNER, repo=REPO)
        subprocess.check_call(["git", "clone", "--depth", "1", "-b", BRANCH, git_url, tmp],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)

        src_root = os.path.join(tmp, SUBDIR) if SUBDIR else tmp
        updated = []
        for item in sorted(os.listdir(src_root)):
            if item in KEEP_LOCAL:
                continue
            src = os.path.join(src_root, item)
            dst = os.path.join(SKILL_DIR, item)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            updated.append(item)

        log("更新完成，已更新: " + ", ".join(updated))
        log(f"当前版本: v{read_local_version()}")
        log("提示：若这是灵犀已安装的技能副本，请在灵犀中重新导入/刷新技能目录以生效。")
        return 0
    except subprocess.CalledProcessError as e:
        err(f"git clone 失败（{e}），更新中止。")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- 首次安装（朋友装机） ----------
def init_install(dest):
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    git_url = GITHUB_GIT.format(owner=OWNER, repo=REPO)
    log(f"克隆版本仓库到 {dest} ...")
    try:
        subprocess.check_call(["git", "clone", "--depth", "1", "-b", BRANCH, git_url, dest],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        v = read_local_version()
        log(f"完成，技能 v{v} 已就绪。")
        log("下一步：在灵犀「技能 → 我的技能」中从该路径导入安装；以后更新用 python scripts/update_check.py --update")
        return 0
    except subprocess.CalledProcessError as e:
        err(f"git clone 失败（{e}）。请确认网络可访问 github.com。")
        return 1


# ---------- 入口 ----------
def main():
    global OWNER, REPO, BRANCH
    ap = argparse.ArgumentParser(description="wps-seo-weekly-articles 技能版本更新工具")
    ap.add_argument("--force", action="store_true", help="跳过 24h 缓存，强制重新检查")
    ap.add_argument("--update", action="store_true", help="检查并自动更新到最新版")
    ap.add_argument("--init", metavar="DIR", help="首次安装：克隆仓库到指定目录（朋友装机用）")
    ap.add_argument("--repo", default=f"{OWNER}/{REPO}", help=f"远程仓库 owner/repo（默认 {OWNER}/{REPO}）")
    ap.add_argument("--branch", default=BRANCH, help=f"远程分支（默认 {BRANCH}）")
    args = ap.parse_args()

    if "/" in args.repo:
        OWNER, REPO = args.repo.split("/", 1)
    BRANCH = args.branch

    if args.init:
        sys.exit(init_install(args.init))
    if args.update:
        sys.exit(update())
    check(force=args.force)


if __name__ == "__main__":
    main()
