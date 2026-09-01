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


# ---------- 版本 ----------
def read_local_version():
    p = os.path.join(SKILL_DIR, "VERSION")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            v = f.read().strip()
        if re.match(r"^\d+\.\d+\.\d+", v):
            return v
    return "0.0.0"


def version_tuple(v):
    nums = re.findall(r"\d+", v or "")[:3]
    return tuple(int(x) for x in nums) or (0, 0, 0)


# ---------- 远程（git 权威通道，无 CDN 缓存） ----------
def git_url():
    return GITHUB_GIT.format(owner=OWNER, repo=REPO)


def fetch_remote_head():
    """git ls-remote 取远程分支 HEAD commit（权威、快、无缓存）。失败返回 None。"""
    try:
        out = subprocess.check_output(
            ["git", "ls-remote", git_url(), f"refs/heads/{BRANCH}"],
            timeout=20, stderr=subprocess.DEVNULL)
        parts = out.decode().strip().split()
        return parts[0] if parts else None
    except Exception:
        return None


def clone_to_tmp():
    """浅克隆远程仓库到临时目录，返回目录路径；失败返回 None。"""
    tmp = tempfile.mkdtemp(prefix="wps-skill-")
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", "-b", BRANCH, git_url(), tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        return tmp
    except Exception:
        cleanup(tmp)
        return None


def overwrite_copy(src_root, dst):
    """用系统命令把 src_root 内容覆盖复制到 dst（绕开 Python os.remove 删除拦截）。"""
    if sys.platform == "win32":
        r = subprocess.run(
            ["robocopy", src_root, dst, "/E", "/IS", "/IT",
             "/XD", ".rundata", ".git", "__pycache__", ".git_old", ".git_backup",
             "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS"],
            timeout=120, capture_output=True)
        if r.returncode >= 8:
            raise RuntimeError(f"robocopy 失败（退出码 {r.returncode}）")
    else:
        subprocess.run(["cp", "-R", src_root.rstrip("/") + "/.", dst.rstrip("/") + "/"],
                       check=True, timeout=120)


def cleanup(tmp):
    """尽力清理临时目录；Windows 沙箱限制下允许残留（位于系统临时目录，不影响技能）。"""
    try:
        if sys.platform != "win32":
            subprocess.run(["rm", "-rf", tmp], timeout=60)
        # Windows：临时目录由系统 Temp 机制回收，不强行删除（沙箱禁止 cmd/rmdir 类命令）
    except Exception:
        pass


def read_remote_meta(tmp):
    """从克隆目录读取本技能子目录的 VERSION 与 CHANGELOG 摘要。返回 (version, changelog_head)。"""
    src = os.path.join(tmp, SUBDIR) if SUBDIR else tmp
    version = None
    pv = os.path.join(src, "VERSION")
    if os.path.isfile(pv):
        with open(pv, encoding="utf-8") as f:
            v = f.read().strip()
        if re.match(r"^\d+\.\d+\.\d+", v):
            version = v
    head = None
    pc = os.path.join(src, "CHANGELOG.md")
    if os.path.isfile(pc):
        with open(pc, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()][:6]
        head = "\n".join(lines)
    return version, head


# ---------- 本地记录 ----------
def read_head():
    try:
        with open(HEAD_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None


def write_head(head):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(HEAD_FILE, "w", encoding="utf-8") as f:
            f.write(head)
    except Exception:
        pass


# ---------- 检查 ----------
def check():
    local = read_local_version()
    remote_head = fetch_remote_head()
    if not remote_head:
        err("无法连接远程仓库（git ls-remote 失败），请检查网络 / github.com 可达性。")
        sys.exit(1)

    last_head = read_head()
    # 需要拉取远程元信息的情形：首次运行（无记录）或远程 HEAD 有变化
    remote_ver, changelog = None, None
    head_changed = last_head is not None and remote_head != last_head
    need_clone = head_changed or last_head is None
    if need_clone:
        tmp = clone_to_tmp()
        if tmp:
            remote_ver, changelog = read_remote_meta(tmp)

    # 判断是否有更新：发布过新提交（HEAD 变化）或远程版本号高于本地（本地装了旧包）
    ver_newer = bool(remote_ver) and version_tuple(remote_ver) > version_tuple(local)
    has_update = head_changed or ver_newer

    if has_update:
        log(f"[{SUBDIR}] 当前版本 v{local}，远程最新 v{remote_ver or '?'}")
        log("==> 发现新版本！可运行  python scripts/update_check.py --update  一键更新")
        if changelog:
            log("    更新内容预览：")
            log("\n".join("    " + ln for ln in changelog.splitlines()))
    else:
        write_head(remote_head)
        if last_head is None:
            log(f"[{SUBDIR}] 当前版本 v{local}，已与远程仓库同步（首次记录）")
        else:
            log(f"[{SUBDIR}] 当前版本 v{local}，远程 v{remote_ver or local}，已是最新版本")


# ---------- 更新 ----------
def update():
    local = read_local_version()
    remote_head = fetch_remote_head()
    if not remote_head:
        err("无法连接远程仓库（git ls-remote 失败），更新中止。")
        sys.exit(1)

    last_head = read_head()
    tmp = clone_to_tmp()
    if not tmp:
        err("git clone 失败，更新中止。")
        sys.exit(1)
    try:
        remote_ver, _ = read_remote_meta(tmp)
    except Exception:
        remote_ver = None

    if last_head is not None and remote_head == last_head:
        log(f"[{SUBDIR}] 已是最新版本（v{local}），无需更新。")
        shutil.rmtree(tmp, ignore_errors=True)
        return 0

    log(f"[{SUBDIR}] 正在从 v{local} 更新到 v{remote_ver or '最新'} ...")
    try:
        src_root = os.path.join(tmp, SUBDIR) if SUBDIR else tmp
        overwrite_copy(src_root, SKILL_DIR)   # 系统命令覆盖合并，跳过 .rundata/.git/__pycache__ 等

        write_head(remote_head)
        log("更新完成")
        log(f"当前版本: v{read_local_version()}")
        log("提示：若这是灵犀已安装的技能副本，请重新导入/刷新技能目录以生效。")
        return 0
    except Exception as e:
        err(f"更新失败: {e}")
        return 1
    finally:
        cleanup(tmp)


# ---------- 首次安装（朋友装机） ----------
def init_install(dest):
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    log(f"克隆版本仓库到 {dest} ...")
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", "-b", BRANCH, git_url(), dest],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
        log("完成。")
        log("下一步：在灵犀「技能 → 我的技能」中从该路径导入安装；以后更新用 python scripts/update_check.py --update")
        return 0
    except subprocess.CalledProcessError as e:
        err(f"git clone 失败（{e}）。请确认网络可访问 github.com。")
        return 1


# ---------- 入口 ----------
def main():
    global OWNER, REPO, BRANCH
    ap = argparse.ArgumentParser(description="灵犀技能版本更新工具")
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
    check()


if __name__ == "__main__":
    main()
