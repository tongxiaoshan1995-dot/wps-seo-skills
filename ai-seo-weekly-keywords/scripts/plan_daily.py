# -*- coding: utf-8 -*-
"""AI SEO 每日关键词规划
策略：四维指纹去重（一级分类×意图×对象×工具）+ 周一至周五题材/意图差异化排期 + 分层推荐。
分类体系：一级分类=AI品牌词/AI场景词/AI竞品词/AI认知词（业务维度）；题材=AI能力（AI写作/AI绘图/...，供周排期轮转）。
数据源：assets/data/ai_enhanced_kw.csv（含 题材/一级分类/意图/操作对象/工具/指纹/内容策略/题材分/搜索量，已剔除价格/会员词）。
"""
import os, sys, json, argparse, math
from datetime import datetime
from collections import Counter

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "assets", "data")
DEFAULT_ENHANCED_KW = os.path.join(DATA_DIR, "ai_enhanced_kw.csv")
DEFAULT_STATE = os.path.join(SKILL_DIR, ".ai_seo_state.json")

# 周一至周五 排期（AI 题材轮转 + 6类意图）
WEEKDAY_SCHEDULE = {
    1: {"label": "周一", "主打题材": ["AI写作", "AI对话"], "主攻意图": ["教程操作", "品牌认知"], "定位": "AI文字创作：写作+对话，教程为主"},
    2: {"label": "周二", "主打题材": ["AI绘图", "AI视频"], "主攻意图": ["模板获取", "教程操作"], "定位": "视觉内容：绘图+视频，模板与制作"},
    3: {"label": "周三", "主打题材": ["AI编程", "AI办公"], "主攻意图": ["教程操作", "场景应用"], "定位": "效率提升：编程+办公，落地应用"},
    4: {"label": "周四", "主打题材": ["大模型", "AI搜索"], "主攻意图": ["功能对比", "品牌认知"], "定位": "选型决策：大模型+搜索，对比认知"},
    5: {"label": "周五", "主打题材": ["AI音频", "AI认知"], "主攻意图": ["教程操作", "品牌认知"], "定位": "泛AI收口：音频+认知，入门前瞻"},
}
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
                "一级分类": str(row.get("一级分类") or "").strip(),
                "意图": str(row.get("意图") or "").strip(),
                "操作对象": str(row.get("操作对象") or "").strip(),
                "工具": str(row.get("工具") or "").strip(),
                "指纹": str(row.get("指纹") or "").strip(),
                "内容策略": str(row.get("内容策略") or "").strip(),
                "搜索热度": str(row.get("搜索热度") or "").strip(),
                "热度分": to_num(row.get("热度分")),
                "题材分": to_num(row.get("题材分")),
            })
    return out

def log_norm(v):
    return math.log10(v + 1) / 6.0 if v > 0 else 0.0

CONTENT_W = {"高关联(整篇AI)": 3.0, "中关联(AI+工具章节)": 2.0, "低关联(方法论轻带)": 1.0}
# 意图内容价值分（官网/品牌等低内容词降权，教程/模板/对比等高内容词优先）
INTENT_W = {"教程操作": 1.0, "模板获取": 0.95, "功能对比": 0.9, "场景应用": 0.85,
            "品牌认知": 0.7, "官网下载": 0.35}

def main():
    ap = argparse.ArgumentParser(description="AI SEO 每日关键词规划")
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
    print(f"[数据] 增强词库 {len(words)} 词", file=sys.stderr)

    state_path = os.path.abspath(args.state)
    if args.reset or not os.path.isfile(state_path):
        state = {"last_day": 0, "used_fp": {}, "updated_at": None}
    else:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    used_fp = set(state.get("used_fp", {}).keys())
    day = args.day or (state.get("last_day", 0) + 1)
    real_wd = datetime.now().isoweekday()
    wd = real_wd if real_wd <= 5 else 5
    sch = WEEKDAY_SCHEDULE[wd]

    core_n, tail_n, sup_n = CORE_CNT, TAIL_CNT, SUPPORT_CNT
    if args.total != 30:
        core_n = max(1, round(args.total * 0.1))
        tail_n = max(2, round(args.total * 0.4))
        sup_n = args.total - core_n - tail_n

    print(f"[排期] 第 {day} 天 = {sch['label']}（{sch['定位']}）", file=sys.stderr)
    print(f"[分层] 每天 {args.total} 词：核心{core_n} / 长尾{tail_n} / 支撑{sup_n}", file=sys.stderr)

    for k in words:
        sc = 0.5 * k["热度分"] + 0.3 * k["题材分"] + 0.2 * (CONTENT_W.get(k["内容策略"], 2.0) / 3.0)
        sc *= INTENT_W.get(k["意图"], 0.7)
        if len(k["关键词"]) <= 2:
            sc -= 0.15
        k["推荐分"] = sc

    pool_fresh = [k for k in words if k["指纹"] not in used_fp]
    pool = pool_fresh if len(pool_fresh) >= args.total else words

    # 指纹聚簇：每指纹取最高分
    best_by_fp = {}
    for k in pool:
        if k["指纹"] not in best_by_fp or k["推荐分"] > best_by_fp[k["指纹"]]["推荐分"]:
            best_by_fp[k["指纹"]] = k

    # ---- 核心层：主打题材 × 主攻意图 ----
    core, seen_core = [], set()
    cand_fp = [k for k in best_by_fp.values() if k["题材"] in sch["主打题材"]
               and k["意图"] in sch["主攻意图"]]
    cand_fp.sort(key=lambda x: -x["推荐分"])
    for k in cand_fp:
        if len(core) >= core_n: break
        core.append(k); seen_core.add(k["指纹"])
    # 核心层：若主打题材词不足，按 四类(品牌/场景/竞品/认知) 分散补足
    if len(core) < core_n:
        cat_cnt = Counter(k["一级分类"] for k in core)
        for k in sorted([x for x in best_by_fp.values() if x["指纹"] not in seen_core],
                        key=lambda x: -x["推荐分"]):
            if len(core) >= core_n: break
            c3 = k["一级分类"]
            if len(core) >= 2 and c3 in cat_cnt and cat_cnt[c3] >= 1:
                continue  # 已有该大类则换其它大类，保证三类均衡
            core.append(k); seen_core.add(k["指纹"]); cat_cnt[c3] += 1

    # ---- 长尾层 ----
    longtail, used_fp_tail, subj_cnt = [], set(seen_core), Counter()
    for k in sorted([x for x in best_by_fp.values() if x["指纹"] not in used_fp_tail],
                    key=lambda x: -x["推荐分"]):
        if len(longtail) >= tail_n: break
        sb = k["题材"]
        limit = 3 if sb in sch["主打题材"] else 1
        if subj_cnt[sb] >= limit: continue
        longtail.append(k); used_fp_tail.add(k["指纹"]); subj_cnt[sb] += 1

    # ---- 支撑层 ----
    support, used_fp_sup, subj_sup = [], set(used_fp_tail), Counter()
    for k in sorted([x for x in best_by_fp.values() if x["指纹"] not in used_fp_sup],
                    key=lambda x: -x["推荐分"]):
        if len(support) >= sup_n: break
        sb = k["题材"]
        if subj_sup[sb] >= 4: continue
        support.append(k); used_fp_sup.add(k["指纹"]); subj_sup[sb] += 1

    chosen = core + longtail + support
    seen_all = set(); dedup = []
    for k in chosen:
        if k["指纹"] not in seen_all:
            seen_all.add(k["指纹"]); dedup.append(k)
    chosen = dedup

    print("=" * 88)
    print(f"AI SEO 关键词每日规划 · 第 {day} 天（{sch['label']}）")
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"词量：{len(chosen)}（核心{len(core)}/长尾{len(longtail)}/支撑{len(support)}）· 四维指纹去重")
    print(f"排期定位：{sch['定位']}")
    print("=" * 88)
    print()
    segs = [("核心", core), ("长尾", longtail), ("支撑", support)]
    all_used = []
    for layer, seg in segs:
        print(f"## {layer}层")
        print("| # | 今日关键词 | 分类 | 题材 | 工具 | 意图 | 对象 | 指纹 | 内容策略 | 热度 | 推荐分 |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for i, k in enumerate(seg, 1):
            print(f"| {i} | {k['关键词']} | {k['一级分类']} | {k['题材']} | {k['工具']} | {k['意图']} | {k['操作对象']} | {k['指纹']} | {k['内容策略']} | {k['搜索热度']} | {k['推荐分']:.3f} |")
            all_used.append(k)
        print()

    new_fp = {fp: w for fp, w in state.get("used_fp", {}).items()}
    for k in all_used:
        new_fp[k["指纹"]] = k["关键词"]
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"last_day": day, "used_fp": new_fp,
                   "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=2)
    print(f"[状态] {state_path}", file=sys.stderr)
    print(f"[汇总] 今日新增 {len(all_used)} 词，累计唯一指纹 {len(new_fp)} 个")

    if args.out:
        lines = [f"AI SEO 关键词每日规划 · 第 {day} 天（{sch['label']}）",
                 f"词量：{len(chosen)}（核心{len(core)}/长尾{len(longtail)}/支撑{len(support)}）", ""]
        for layer, seg in segs:
            lines.append(f"## {layer}层")
            lines.append("| # | 今日关键词 | 分类 | 题材 | 工具 | 意图 | 对象 | 指纹 | 内容策略 | 热度 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            for i, k in enumerate(seg, 1):
                lines.append(f"| {i} | {k['关键词']} | {k['一级分类']} | {k['题材']} | {k['工具']} | {k['意图']} | {k['操作对象']} | {k['指纹']} | {k['内容策略']} | {k['搜索热度']} |")
            lines.append("")
        with open(os.path.abspath(args.out), "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
        print(f"[导出] {os.path.abspath(args.out)}", file=sys.stderr)

if __name__ == "__main__":
    main()
