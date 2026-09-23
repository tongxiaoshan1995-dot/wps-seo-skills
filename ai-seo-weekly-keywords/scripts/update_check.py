#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""灵犀技能：版本更新检查 / 一键更新（多技能仓库，SUBDIR 自动适配）。

用法:
  python scripts/update_check.py              # 检查是否有新版本（git ls-remote 实时判断）
  python scripts/update_check.py --update     # 检查 + 自动更新到最新版
  python scripts/update_check.py --init <目录># 首次安装：克隆仓库到指定目录（朋友装机用）
  python scripts/update_check.py --repo owner/repo --branch main   # 覆盖默认远程配置

更新判断原理（绕开 CDN 缓存，保证发布后第一时间可检测）:
  - 用 `git ls-remote` 读取远程分支 HEAD commit，与本地记录的上次 HEAD 对比
  - 远程 HEAD 变化 = 有新发布（git 不经 CDN，无缓存延迟）
  - 检测到更新后，浅克隆仓库读取远程 VERSION / CHANGELOG 摘要用于展示
  - 更新：git clone --depth 1 拉取最新，覆盖本地技能目录（保留 .rundata / __pycache__ 等运行态）
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------- 默认远程配置 ----------
OWNER = "tongxiaoshan1995-dot"
REPO = "wps-seo-skills"
BRANCH = "main"

# 技能根目录 = 本脚本的上级目录（scripts/ 的父目录）
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 本技能在版本仓库内的子目录（多技能共用一个仓库；仓库根直接放本技能时为空）
SUBDIR = os.path.basename(SKILL_DIR)
CACHE_DIR = os.path.join(SKILL_DIR, ".rundata")
HEAD_FILE = os.path.join(CACHE_DIR, "remote_head.txt")

GITHUB_GIT = "https://github.com/{owner}/{repo}.git"

# 本地运行态 / 本地版本控制：更新时保留、不被远程覆盖
KEEP_LOCAL = {".rundata", "__pycache__", ".git"}

def log(msg):
    print(msg, flush=True)

def err(msg):
    print(f"[错误] {msg}", file=sys.stderr, flush=True)

def run(cmd, timeout=60, capture=True):
    """执行命令，返回 (returncode, stdout)。失败返回非 0。"""
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, "git 不在 PATH 中"
    except subprocess.TimeoutExpired:
        return 124, "命令超时"

def remote_head():
    """读取远程分支 HEAD commit。返回 (ok, head) 或 (ok, error)。"""
    code, out = run(["git", "ls-remote", GITHUB_GIT.format(owner=OWNER, repo=REPO), BRANCH])
    if code != 0:
        return False, out.strip()
    head = out.split("\t")[0].strip() if out else ""
    if not head:
        return False, "远程未找到分支"
    return True, head

def read_remote_version():
    """浅克隆仓库到临时目录，读取远程 VERSION 与 CHANGELOG 摘要。"""
    tmp = tempfile.mkdtemp(prefix="skill_update_")
    repo_dir = os.path.join(tmp, "repo")
    code, out = run(["git", "clone", "--depth", "1", "-b", BRANCH,
                     GITHUB_GIT.format(owner=OWNER, repo=REPO), repo_dir], timeout=120)
    if code != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, None, out.strip()
    # 定位远程技能目录（仓库根直接放本技能或子目录）
    remote_skill = os.path.join(repo_dir, SUBDIR) if SUBDIR else repo_dir
    ver = cg = ""
    vf = os.path.join(remote_skill, "VERSION")
    if os.path.isfile(vf):
        with open(vf, encoding="utf-8") as f:
            ver = f.read().strip()
    cf = os.path.join(remote_skill, "CHANGELOG.md")
    if os.path.isfile(cf):
        with open(cf, encoding="utf-8") as f:
            cg = f.read().strip()
    return ver, cg, None

def local_version():
    vf = os.path.join(SKILL_DIR, "VERSION")
    if os.path.isfile(vf):
        with open(vf, encoding="utf-8") as f:
            return f.read().strip()
    return None

def do_update():
    """浅克隆远程技能覆盖本地（保留运行态目录）。"""
    tmp = tempfile.mkdtemp(prefix="skill_update_")
    repo_dir = os.path.join(tmp, "repo")
    code, out = run(["git", "clone", "--depth", "1", "-b", BRANCH,
                     GITHUB_GIT.format(owner=OWNER, repo=REPO), repo_dir], timeout=120)
    if code != 0:
        err("克隆仓库失败: " + out)
        return False
    remote_skill = os.path.join(repo_dir, SUBDIR) if SUBDIR else repo_dir
    if not os.path.isdir(remote_skill):
        err(f"仓库内未找到技能目录 {SUBDIR or '(根)'}")
        return False
    # 备份本地运行态
    backups = {}
    for keep in KEEP_LOCAL:
        p = os.path.join(SKILL_DIR, keep)
        if os.path.exists(p):
            bp = os.path.join(tmp, "keep_" + keep)
            shutil.copytree(p, bp, ignore=shutil.ignore_patterns("*.pyc"))
            backups[keep] = bp
    # 覆盖本地（移除旧文件后复制）
    for name in os.listdir(SKILL_DIR):
        p = os.path.join(SKILL_DIR, name)
        if name in KEEP_LOCAL:
            continue
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass
    for name in os.listdir(remote_skill):
        src = os.path.join(remote_skill, name)
        dst = os.path.join(SKILL_DIR, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.pyc"))
        else:
            shutil.copy2(src, dst)
    # 恢复运行态
    for keep, bp in backups.items():
        dst = os.path.join(SKILL_DIR, keep)
        if os.path.exists(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(bp, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    log("已更新到最新版，重新加载即可生效。")
    return True

def main():
    ap = argparse.ArgumentParser(description="AI SEO 关键词技能 · 版本更新检查 / 一键更新")
    ap.add_argument("--update", action="store_true", help="检查并自动更新到最新版")
    ap.add_argument("--init", metavar="DIR", help="首次安装：克隆仓库到指定目录")
    ap.add_argument("--repo", default=f"{OWNER}/{REPO}", help="覆盖默认远程仓库")
    ap.add_argument("--branch", default=BRANCH, help="覆盖默认分支")
    args = ap.parse_args()

    global OWNER, REPO, BRANCH
    if "/" in args.repo:
        OWNER, REPO = args.repo.split("/", 1)
    BRANCH = args.branch

    if args.init:
        code, out = run(["git", "clone", "--depth", "1", "-b", BRANCH,
                         GITHUB_GIT.format(owner=OWNER, repo=REPO), args.init], timeout=120)
        if code != 0:
            err("克隆失败: " + out)
            sys.exit(1)
        log(f"已克隆到 {args.init}，技能位于 {os.path.join(args.init, SUBDIR)}")
        return

    os.makedirs(CACHE_DIR, exist_ok=True)
    ok, head = remote_head()
    if not ok:
        log("远程不可达，跳过更新检查。")
        return

    last = ""
    if os.path.isfile(HEAD_FILE):
        with open(HEAD_FILE, encoding="utf-8") as f:
            last = f.read().strip()

    if last == head:
        log("已是最新版本")
        return

    # 远程 HEAD 变化 → 拉取版本与摘要
    rver, rcg, rerr = read_remote_version()
    lver = local_version()
    if rerr:
        log(f"检测到远程有更新（{last or '首次'} → {head[:8]}），但读取版本信息失败：{rerr}")
    else:
        log(f"[wps-ai-keywords] 当前版本 {lver}，远程 v{rver}，发现新版本")
        if rcg:
            summary = rcg.split("## ")[1].split("\n", 1)[-1].strip() if "## " in rcg else rcg
            log("更新内容摘要：")
            log(summary)
    with open(HEAD_FILE, "w", encoding="utf-8") as f:
        f.write(head)

    if args.update:
        if do_update():
            log("更新完成，重新加载技能即可使用新版。")
        else:
            err("更新失败，请稍后重试。")

if __name__ == "__main__":
    main()
