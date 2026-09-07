# -*- coding: utf-8 -*-
"""WPS SEO 每日关键词规划 v3
策略：三维指纹去重 + 周一至周五题材/意图差异化排期 + 分层推荐 + 去除会员/价格词。
数据源：assets/data/wps_enhanced_kw.csv（已清洗分类）。
"""
import os, sys, json, argparse, math
from datetime import datetime
from collections import Counter

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "assets", "data")
DEFAULT_ENHANCED_KW = os.path.join(DATA_DIR, "wps_enhanced_kw.csv")
DEFAULT_STATE = os.path.join(SKILL_DIR, ".wps_seo_state.json")

# 周一至周五 排期
WEEKDAY_SCHEDULE = {
    1: {"label": "周一", "主打题材": ["Excel", "Word"], "主攻意图": ["教程操作", "故障解决"], "定位": "基础文档处理，教程为主"},
    2: {"label": "周二", "主打题材": ["PDF", "PPT"], "主攻意图": ["模板获取", "教程操作"], "定位": "格式转换+模板制作"},
    3: {"label": "周三", "主打题材": ["WPS AI", "云文档/在线"], "主攻意图": ["AI认知", "教程操作"], "定位": "AI能力+在线协作新卖点"},
    4: {"label": "周四", "主打题材": ["下载/安装", "WPS综合"], "主攻意图": ["下载安装", "功能认知"], "定位": "转化层，承接下载安装"},
    5: {"label": "周五", "主打题材": ["Office通用", "WPS综合"], "主攻意图": ["对比选型", "功能认知"], "定位": "决策对比，周结尾收口"},
}
# 每天分层配比（篇数）
CORE_CNT, TAIL_CNT, SUPPORT_CNT = 3, 12, 15

def weekday_from_day(day):
    return (day - 1) % 5 + 1

def to_num(v):
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0

def load_enhanced_kw(path):
    import csv
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            kw = str(row.get("关键词") or "").strip()
            if not kw or kw.lower() == "nan":
                continue
            out.append({
                "关键词": kw,
                "题材": str(row.get("题材") or "").strip(),
                "意图": str(row.get("意图") or "").strip(),
                "操作对象": str(row.get("操作对象") or "").strip(),
                "指纹": str(row.get("指纹") or "").strip(),
                "内容策略": str(row.get("内容策略") or "").strip(),
                "搜索量": to_num(row.get("搜索量")),
                "题材分": to_num(row.get("题材分")),
            })
    return out

def log_norm(v):
    return math.log10(v + 1) / 6.0 if v > 0 else 0.0

CONTENT_W = {"高关联(整篇WPS)": 3.0, "中关联(通用+WPS章节)": 2.0, "低关联(方法论轻带)": 1.0}

def main():
    ap = argparse.ArgumentParser(description="WPS SEO 每日关键词规划 v3")
    ap.add_argument("--kw", "--final-kw", dest="kw", default=DEFAULT_ENHANCED_KW)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--day", type=int, default=None)
    ap.add_argument("--total", type=int, default=30)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    words = load_enhanced_kw(args.kw)
    if not words:
        print("[错误] 增强词库为空", file=sys.stderr)
        sys.exit(1)
    print(f"[数据] 增强词库 {len(words)} 词（已去会员/价格）", file=sys.stderr)

    # 状态
    state_path = os.path.abspath(args.state)
    if args.reset or not os.path.isfile(state_path):
        state = {"last_day": 0, "used_fp": {}, "updated_at": None}
    else:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    used_fp = set(state.get("used_fp", {}).keys())
    day = args.day or (state.get("last_day", 0) + 1)
    wd = weekday_from_day(day)
    sch = WEEKDAY_SCHEDULE[wd]

    # 分层配额
    core_n, tail_n, sup_n = CORE_CNT, TAIL_CNT, SUPPORT_CNT
    if args.total != 30:
        # 按比例：核心10% / 长尾40% / 支撑50%
        core_n = max(1, round(args.total * 0.1))
        tail_n = max(2, round(args.total * 0.4))
        sup_n = args.total - core_n - tail_n

    print(f"[排期] 第 {day} 天 = {sch['label']}（{sch['定位']}）", file=sys.stderr)
    print(f"[分层] 每天 {args.total} 词：核心{core_n} / 长尾{tail_n} / 支撑{sup_n}", file=sys.stderr)

    # 推荐分
    for k in words:
        sc = 0.5 * log_norm(k["搜索量"]) + 0.3 * k["题材分"] + 0.2 * (CONTENT_W.get(k["内容策略"], 2.0) / 3.0)
        if len(k["关键词"]) <= 2:
            sc -= 0.15
        if k["题材"] == "其他/泛":
            sc -= 0.2
        k["推荐分"] = sc

    # 未用池：指纹未用过的词
    fresh = [k for k in words if k["指纹"] not in used_fp]
    pool = fresh if len(fresh) >= args.total else words  # 不够则指纹轮转

    # ---- 核心层：主打题材 × 主攻意图，同一指纹只取最高分1词 ----
    # 先按指纹聚簇，每个指纹取推荐分最高者，避免同指纹重复
    best_by_fp = {}
    for k in pool:
        if k["指纹"] not in best_by_fp or k["推荐分"] > best_by_fp[k["指纹"]]["推荐分"]:
            best_by_fp[k["指纹"]] = k
    core = []
    seen_core = set()
    # 主打题材 × 主攻意图 的指纹候选（按推荐分降序）
    cand_fp = [k for k in best_by_fp.values() if k["题材"] in sch["主打题材"]
               and k["意图"] in sch["主攻意图"]]
    cand_fp.sort(key=lambda x: -x["推荐分"])
    for k in cand_fp:
        if len(core) >= core_n:
            break
        core.append(k)
        seen_core.add(k["指纹"])
    # 核心不足：从其余指纹补高分
    if len(core) < core_n:
        for k in sorted([x for x in best_by_fp.values() if x["指纹"] not in seen_core],
                        key=lambda x: -x["推荐分"]):
            if len(core) >= core_n:
                break
            core.append(k)
            seen_core.add(k["指纹"])

    # ---- 长尾层：基于 best_by_fp 指纹去重 + 题材分散 ----
    longtail = []
    used_fp_tail = set(seen_core)
    subj_cnt = Counter()
    for k in sorted([x for x in best_by_fp.values() if x["指纹"] not in used_fp_tail],
                    key=lambda x: -x["推荐分"]):
        if len(longtail) >= tail_n:
            break
        sb = k["题材"]
        limit = 3 if sb in sch["主打题材"] else 1  # 主打题材可多点
        if subj_cnt[sb] >= limit:
            continue
        longtail.append(k)
        used_fp_tail.add(k["指纹"])
        subj_cnt[sb] += 1

    # ---- 支撑层：基于 best_by_fp 指纹去重 + 题材分散（补充铺量）----
    support = []
    used_fp_sup = set(used_fp_tail)
    subj_sup = Counter()
    for k in sorted([x for x in best_by_fp.values() if x["指纹"] not in used_fp_sup],
                    key=lambda x: -x["推荐分"]):
        if len(support) >= sup_n:
            break
        sb = k["题材"]
        if subj_sup[sb] >= 4:
            continue
        support.append(k)
        used_fp_sup.add(k["指纹"])
        subj_sup[sb] += 1

    chosen = core + longtail + support
    # 去重兜底：确保当天指纹唯一
    seen_all = set()
    dedup = []
    for k in chosen:
        if k["指纹"] not in seen_all:
            seen_all.add(k["指纹"])
            dedup.append(k)
    chosen = dedup

    # ---- 输出 ----
    quota_core = len(core)
    quota_tail = len(longtail)
    title = f"WPS SEO 关键词每日规划 v3 · 第 {day} 天（{sch['label']}）"
    print("=" * 84)
    print(title)
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"词量：{len(chosen)}（核心{quota_core}/长尾{quota_tail}/支撑{len(support)}）· 三维指纹去重 · 已去会员/价格")
    print(f"排期定位：{sch['定位']}")
    print("=" * 84)
    print()
    segs = [("核心", core), ("长尾", longtail), ("支撑", support)]
    all_used = []
    for layer, seg in segs:
        print(f"## {layer}层")
        print("| # | 今日关键词 | 题材 | 意图 | 对象 | 指纹 | 内容策略 | 搜索量 | 推荐分 |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for i, k in enumerate(seg, 1):
            print(f"| {i} | {k['关键词']} | {k['题材']} | {k['意图']} | {k['操作对象']} | {k['指纹']} | {k['内容策略']} | {k['搜索量']:.0f} | {k['推荐分']:.3f} |")
            all_used.append(k)
        print()

    # 持久化
    new_fp = {fp: w for fp, w in state.get("used_fp", {}).items()}
    for k in all_used:
        new_fp[k["指纹"]] = k["关键词"]
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"last_day": day, "used_fp": new_fp,
                   "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=2)
    print(f"[状态] {state_path}", file=sys.stderr)
    print(f"[汇总] 今日新增 {len(all_used)} 词，累计唯一指纹 {len(new_fp)} 个")

    if args.out:
        lines = [title, f"词量：{len(chosen)}（核心{quota_core}/长尾{quota_tail}/支撑{len(support)}）", ""]
        for layer, seg in segs:
            lines.append(f"## {layer}层")
            lines.append("| # | 今日关键词 | 题材 | 意图 | 对象 | 指纹 | 内容策略 | 搜索量 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for i, k in enumerate(seg, 1):
                lines.append(f"| {i} | {k['关键词']} | {k['题材']} | {k['意图']} | {k['操作对象']} | {k['指纹']} | {k['内容策略']} | {k['搜索量']:.0f} |")
            lines.append("")
        with open(os.path.abspath(args.out), "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
        print(f"[导出] {os.path.abspath(args.out)}", file=sys.stderr)

if __name__ == "__main__":
    main()
