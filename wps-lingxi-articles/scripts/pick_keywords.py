#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 周度文章 · 选题挑词脚本
================================
从《WPS_SEO完整关键词库》（wps_final_kw.csv）按 10 个策略组别挑取本周文章选题关键词：
- 每个策略组别至少 1 个关键词（默认 10 词/周 = 每组 1 词，可加大）
- 关键词按指定指标从高到低排列（默认：GEO机会值 > 第三方流量指数 > 百度统计PV > 社媒热度值，
  取第一非空值；也可用 --metric 指定单一指标）
- 跨周自动去重（状态文件记录历史已用词），保证每周选题不重复

用法示例：
    python pick_keywords.py                          # 本周每组 1 词
    python pick_keywords.py --count 15               # 共 15 篇（每组至少 1 篇，余量按价值分配）
    python pick_keywords.py --per-group 3            # 每组 3 词 = 30 词
    python pick_keywords.py --metric GEO机会值       # 按指定指标排序
    python pick_keywords.py --keywords "wps下载,wps会员,PDF转Word"  # 手动指定关键词（跳过自动挑词）
    python pick_keywords.py --week 3 --out 第3周选题.md
    python pick_keywords.py --reset                  # 清空去重历史，从第 1 周开始
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# 10 组别定义：组名 -> (筛选谓词, 意图标签)
# 与 wps-seo-weekly-keywords 技能保持一致
# ---------------------------------------------------------------------------
GROUPS = [
    ("下载安装", "下载落地页",
     lambda d: d["一级分类"] == "下载安装",
     "下载WPS各端安装包，落地页需官方下载入口承接"),
    ("价格购买", "价格/会员页",
     lambda d: d["一级分类"] == "价格与会员",
     "会员价格/免费权益/版本对比，适合价格与权益展示页"),
    ("对比选择", "竞品对比页",
     lambda d: d["一级分类"] == "竞品对比与选型",
     "对比选型阶段，适合客观对比页与FAQ"),
    ("模板获取", "模板聚合页",
     lambda d: d["一级分类"] == "模板业务",
     "简历/汇报/合同/表格等模板需求，适合模板库聚合页"),
    ("格式转换", "转换工具页",
     lambda d: d["一级分类"] == "格式转换与文档处理",
     "PDF/Word/PPT/图片互转与处理，适合工具页与教程"),
    ("故障解决", "FAQ解决页",
     lambda d: (d["一级分类"] == "组件功能与教程")
               & (d["二级主题"] == "WPS用户问题/故障解决"),
     "WPS使用故障/报错/文件丢失恢复问题，适合FAQ解决页与GEO答案资产"),
    ("教程操作", "教程内容页",
     lambda d: (d["一级分类"] == "组件功能与教程")
               & (d["二级主题"] != "WPS用户问题/故障解决"),
     "WPS表格/文字/演示/PDF功能与操作，适合功能教程页"),
    ("功能认知", "功能科普页",
     lambda d: d["一级分类"] == "功能教程与知识",
     "办公知识与操作问答，适合教程内容与GEO答案资产"),
    ("AI认知", "AI专题页",
     lambda d: d["一级分类"] == "AI办公",
     "AI生成PPT/写作/表格，适合WPS AI专题页与GEO抢占"),
    ("品牌直达", "品牌落地页",
     lambda d: d["一级分类"] == "品牌与官方入口",
     "品牌/官网/正版入口，路径短、转化快，重承接与信任"),
]

# 价值列优先级：越靠前越优先作为排序依据
VALUE_COLS = ["GEO机会值", "第三方流量指数", "百度统计PV", "社媒热度值"]


# ---------------------------------------------------------------------------
# 路径定位
# ---------------------------------------------------------------------------
def find_workspace_csv():
    """按优先级定位词库 CSV：显式参数 > 当前/最近工作区 > 技能内置副本"""
    candidates = []
    ws = os.environ.get("WORKSPACE_DIR")
    if ws:
        candidates.append(os.path.join(ws, "wps_final_kw.csv"))
    home = os.path.expanduser("~")
    for base in [os.path.join(home, "Documents", "lingxi-claw")]:
        if os.path.isdir(base):
            candidates += sorted(glob.glob(os.path.join(base, "*", "wps_final_kw.csv")),
                                 key=os.path.getmtime, reverse=True)
    skill_data = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "assets", "data", "wps_final_kw.csv")
    candidates.append(skill_data)
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def find_state_path(explicit=None):
    """状态文件：显式参数 > 最近工作区已有状态 > 最近工作区默认落点"""
    if explicit:
        return explicit
    home = os.path.expanduser("~")
    base = os.path.join(home, "Documents", "lingxi-claw")
    if os.path.isdir(base):
        found = sorted(glob.glob(os.path.join(base, "*", ".wps_seo_articles_state.json")),
                       key=os.path.getmtime, reverse=True)
        if found:
            return found[0]
        wss = sorted([d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d)],
                     key=os.path.getmtime, reverse=True)
        if wss:
            return os.path.join(wss[0], ".wps_seo_articles_state.json")
    ws = os.environ.get("WORKSPACE_DIR")
    if ws:
        return os.path.join(ws, ".wps_seo_articles_state.json")
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(skill_root, "data", "state.json")


def load_state(path):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_week": 0, "used": [], "used_by_group": {}, "updated_at": None}


def save_state(path, state):
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 挑词
# ---------------------------------------------------------------------------
def score_of(row, metric=None):
    """返回关键词价值分；metric 指定单一指标列，否则取第一非空价值列。"""
    cols = [metric] if metric else VALUE_COLS
    for c in cols:
        if c not in row:
            continue
        v = row[c]
        if v is None or (isinstance(v, float) and v != v):  # NaN
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def pick_per_group(sub, used, per_group, metric):
    """从子集剔除 used 后按价值降序取 per_group 个。返回 (chosen, exhausted)。"""
    cand = sub[~sub["关键词"].isin(used)].copy()
    exhausted = len(cand) < per_group
    if cand.empty:
        cand = sub.copy()  # 整组用尽，轮转回头部
    cand["_score"] = cand.apply(lambda r: score_of(r, metric), axis=1)
    cand = cand.sort_values("_score", ascending=False)
    chosen = cand.head(per_group)["关键词"].tolist()
    return chosen, exhausted


def dist_by_count(groups_subs, total, metric):
    """把 total 个名额分配到各组（每组至少 1），余量按组内 Top 词价值全局再分配。
    groups_subs: [(组名, 策略, 子集DataFrame, 意图)]；返回 {组名: [关键词...]}"""
    # 先每组 1 个
    plan = {}
    picked_first = {}
    for gname, _strategy, sub, _intent in groups_subs:
        chosen, _ = pick_per_group(sub, set(), 1, metric)
        plan[gname] = [chosen[0]]
        picked_first[gname] = chosen[0]
    # 剩余名额按“组内下一个最高价值词”的分数全局贪心
    rest = total - len(groups_subs)
    used_global = set(picked_first.values())
    pool = []  # (group, kw, score)
    for gname, _strategy, sub, _intent in groups_subs:
        cand = sub[~sub["关键词"].isin(used_global)].copy()
        if cand.empty:
            cand = _s.copy()
        cand["_score"] = cand.apply(lambda r: score_of(r, metric), axis=1)
        for _, row in cand.sort_values("_score", ascending=False).head(rest).iterrows():
            pool.append((gname, row["关键词"], row["_score"]))
    pool.sort(key=lambda x: x[2], reverse=True)
    for gname, kw, _sc in pool[:rest]:
        if kw not in used_global:
            plan[gname].append(kw)
            used_global.add(kw)
    return plan


def main():
    ap = argparse.ArgumentParser(description="WPS SEO 周度文章 · 选题挑词")
    ap.add_argument("--csv", help="词库 CSV 路径（默认自动定位）")
    ap.add_argument("--state", help="状态 JSON 路径（默认自动定位）")
    ap.add_argument("--week", type=int, help="指定周次（默认自动递增）")
    ap.add_argument("--count", type=int, default=10, help="本周文章总数（默认 10 = 每组 1 篇）")
    ap.add_argument("--per-group", type=int, help="每组词数（指定后优先于 --count）")
    ap.add_argument("--metric", default=None, help="排序指标列名，如 GEO机会值/第三方流量指数/百度统计PV/社媒热度值")
    ap.add_argument("--keywords", help="手动指定关键词（逗号分隔，跳过自动挑词；同时用 --group 分组）")
    ap.add_argument("--group", default=None, help="与 --keywords 配合：给手动关键词统一指定策略组别（如 教程操作）")
    ap.add_argument("--out", help="输出选题清单路径（.md）")
    ap.add_argument("--reset", action="store_true", help="清空去重历史，从第 1 周开始")
    args = ap.parse_args()

    import pandas as pd

    state_path = find_state_path(args.state)
    if args.reset:
        state = {"last_week": 0, "used": [], "used_by_group": {}, "updated_at": None}
    else:
        state = load_state(state_path)
    used = set(state.get("used", []))
    week = args.week if args.week else (state.get("last_week", 0) + 1)

    csv_path = args.csv or find_workspace_csv()
    if not csv_path or not os.path.isfile(csv_path):
        sys.exit("[错误] 找不到词库文件 wps_final_kw.csv，请用 --csv 指定路径")
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df = df.fillna({c: None for c in VALUE_COLS})
    print(f"[数据] 词库：{os.path.basename(csv_path)}（{len(df)} 词）", file=sys.stderr)

    # 手动关键词模式
    rows = []
    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
        gname = args.group or "教程操作"
        intent = dict((g[0], g[3]) for g in GROUPS).get(gname, "")
        for kw in kws:
            # 尝试在词库中补全价值信息
            hit = df[df["关键词"] == kw]
            if not hit.empty:
                r = hit.iloc[0]
                rows.append((f"{gname}", kw, intent, score_of(r, args.metric),
                             str(r["二级主题"]) if "二级主题" in r else ""))
            else:
                rows.append((f"{gname}", kw, intent, 0.0, ""))
        this_week_kws = kws
    else:
        # 自动挑词
        groups_subs = [(g[0], g[1], df[g[2](df)], g[3]) for g in GROUPS]
        plan = {}
        if args.per_group:
            for gname, strategy, sub, intent in groups_subs:
                chosen, exhausted = pick_per_group(sub, used, args.per_group, args.metric)
                plan[gname] = chosen
        else:
            plan = dist_by_count(groups_subs, args.count, args.metric)
        for gname, strategy, sub, intent in groups_subs:
            for kw in plan.get(gname, []):
                hit = df[df["关键词"] == kw]
                subtopic = str(hit.iloc[0]["二级主题"]) if not hit.empty and "二级主题" in hit.columns else ""
                rows.append((f"{gname} · {strategy}", kw, intent, score_of(hit.iloc[0], args.metric), subtopic))
        this_week_kws = [kw for _g, kw, _i, _s, _t in rows]

    # 持久化状态
    state["used"] = sorted(set(used) | set(this_week_kws))
    by_group = state.setdefault("used_by_group", {})
    for g, kw, _i, _s, _t in rows:
        g0 = g.split(" · ")[0]
        by_group.setdefault(g0, []).append(kw)
    state["last_week"] = week
    save_state(state_path, state)

    # 输出
    title = f"WPS SEO 周度文章选题 · 第 {week} 周"
    sep = "=" * 62
    lines = [sep, title,
             f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"文章数：{len(this_week_kws)} 篇（每组至少 1 篇）"
             + (f"；排序指标：{args.metric}" if args.metric else "；排序指标：第一非空价值列"),
             sep, "",
             "| # | 策略组别 | 关键词 | 搜索意图 | 价值分 |",
             "| --- | --- | --- | --- | --- |"]
    for idx, (g, kw, intent, sc, _t) in enumerate(rows, 1):
        lines.append(f"| {idx} | {g} | {kw} | {intent} | {sc:.1f} |")
    lines.append("")
    lines.append(f"本组覆盖：{len(set(x[1] for x in rows))} 篇 / 累计已用 {len(state['used'])} 词。")
    lines.append("（状态已写入 " + state_path + " ）")

    text = "\n".join(lines)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n[已导出] {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
