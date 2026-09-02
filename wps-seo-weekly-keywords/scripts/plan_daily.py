#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPS SEO 每日关键词规划（多信号加权版）
==========================================
相比 v1 的改进：
  1. 数据源改用完整词库 wps_final_kw.csv（12166 词，含百度PV/流量指数/需求级别/搜索意图/二级主题）
     + 合并 wps_daily_kw.csv 的月均搜索量
  2. 推荐分 = 搜索量×0.5 + 题材热度×0.3 + SEM×0.2 − 已覆盖惩罚
     搜索量：月均搜索量或百度PV，组内归一化
     题材热度：8月 CMS 文章篇均阅读量按题材映射归一化（theme_score.json）
     SEM：命中 SEM 词表得满分（--sem 指定，缺省为 0）
     已覆盖惩罚：关键词出现在已发布文章标题中 → 直接剔除（--covered 指定或自动拉 CMS）
  3. 脏词清洗：过滤含 \\ / . ' " URL 等异常词
  4. 竞品聚簇：同一主品牌只保留 TOP1-2 词，避免单一产品霸屏

用法示例：
    python plan_daily_v2.py
    python plan_daily_v2.py --total 20
    python plan_daily_v2.py --day 3 --out /path/第3天规划.md
    python plan_daily_v2.py --sem /path/sem_words.csv   # 启用 SEM 信号
    python plan_daily_v2.py --reset
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

# 技能根目录 = 本脚本的上级目录（scripts/ 的父目录）
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "assets", "data")
DEFAULT_FINAL_KW = os.path.join(DATA_DIR, "wps_final_kw.csv")
DEFAULT_DAILY_KW = os.path.join(DATA_DIR, "wps_daily_kw.csv")
DEFAULT_THEME = os.path.join(DATA_DIR, "theme_score.json")

# 策略组别映射：完整词库一级分类 → 四类策略词
CAT_MAP = {
    "品牌词": {"品牌与官方入口", "下载安装"},
    "竞品词": {"竞品对比与选型"},
    "通用词": {"内容与社媒词", "协同办公与企业", "其他", "云文档与在线办公", "价格与会员"},
    "功能词": {"组件功能与教程", "功能教程与知识", "格式转换与文档处理", "模板业务", "AI办公"},
}
INTENT = {
    "品牌词": "品牌/官网/正版入口，路径短、转化快，重承接与信任，承接品牌直达流量",
    "竞品词": "竞品/对比/替代需求，适合客观对比页与FAQ，拦截竞品搜索流量",
    "通用词": "办公软件泛需求，适合知识科普与工具页，拓展新用户认知",
    "功能词": "word/excel/ppt等具体功能需求，意图精准，适合功能教程页与工具页",
}
RATIO = [("品牌词", 0.35), ("竞品词", 0.10), ("通用词", 0.15), ("功能词", 0.40)]
WEIGHTS = {"搜索量": 0.5, "题材热度": 0.3, "SEM": 0.2}

# 脏词正则：URL / 含反斜杠 / 以.开头或结尾 / 含引号等
DIRTY_RE = re.compile(r"[\\/'\"]|https?://|\.wps|wps\.ai|ai\.wps|\.$|^\.|^\s*$")
# 垃圾/截断词：明显无意义或泛站广告词
JUNK_WORDS = {"（已屏蔽）", "heimaoku.com最新泛站程序资源", "泛站", "已屏蔽", "wps官", "w0rd文档"}
JUNK_RE = re.compile(r"heimaoku|泛站|已屏蔽|（已屏蔽）|w0rd|伽马|gamma官网")


def to_num(v):
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0


def load_final_kw(path):
    import pandas as pd
    df = pd.read_csv(path, encoding="utf-8-sig")
    out = []
    for _, row in df.iterrows():
        word = str(row.get("关键词") or "").strip()
        if not word or word.lower() == "nan":
            continue
        if DIRTY_RE.search(word):
            continue
        out.append({
            "关键词": word,
            "一级分类": str(row.get("一级分类") or "").strip(),
            "二级主题": str(row.get("二级主题") or "").strip(),
            "搜索意图": str(row.get("搜索意图") or "").strip(),
            "百度PV": to_num(row.get("百度统计PV")),
            "流量指数": to_num(row.get("第三方流量指数")),
            "GEO机会值": to_num(row.get("GEO机会值")),
            "社媒热度值": to_num(row.get("社媒热度值")),
            "需求级别": str(row.get("需求级别") or "").strip(),
        })
    return out


def merge_daily_vol(final_words, daily_csv):
    """把 daily 词库的月均搜索量合并进完整词库；daily 独有词整条补充进候选池
    （尤其竞品词：豆包/WorkBuddy 等真实搜索量在 daily，final 缺失）。
    返回 (vol_map, daily_only_words)。"""
    import pandas as pd
    if not os.path.isfile(daily_csv):
        return {}, []
    df = pd.read_csv(daily_csv, encoding="utf-8-sig")
    existing = {k["关键词"] for k in final_words}
    vol_map = {}
    daily_only = []
    for _, row in df.iterrows():
        w = str(row.get("关键词") or "").strip()
        if not w:
            continue
        vol_map[w] = to_num(row.get("月均搜索量"))
        if w not in existing:
            cat_daily = str(row.get("类别") or "").strip()
            # daily 四类 → final 一级分类语义
            if cat_daily == "品牌词":
                cat1 = "品牌与官方入口"
            elif cat_daily == "竞品词":
                cat1 = "竞品对比与选型"
            elif cat_daily == "通用词":
                cat1 = "其他"
            else:
                cat1 = "组件功能与教程"
            daily_only.append({
                "关键词": w,
                "一级分类": cat1,
                "二级主题": cat_daily,
                "搜索意图": "",
                "百度PV": to_num(row.get("月均搜索量")),
                "流量指数": 0.0,
                "GEO机会值": 0.0,
                "社媒热度值": 0.0,
                "需求级别": "",
                "月均搜索量": vol_map[w],
            })
    for k in final_words:
        k["月均搜索量"] = vol_map.get(k["关键词"], 0.0)
    # daily 补充词同样做脏词过滤
    daily_only = [k for k in daily_only
                  if k["关键词"] not in JUNK_WORDS and not JUNK_RE.search(k["关键词"]) and not DIRTY_RE.search(k["关键词"])]
    return vol_map, daily_only


def map_category(cat1):
    for cat, s in CAT_MAP.items():
        if cat1 in s:
            return cat
    return None


# 竞品词必须含对比/选型语义（词库一级分类有噪音，如 wvs网页版入口 被错标为竞品）
# vs 需独立成词，避免 wvs 误判；自家品牌词（wps/金山）需同时含竞品名才保留
COMPARE_RE = re.compile(r"对比|区别|哪个好|哪个好用|替代|还是|怎么选|哪个版本好|比一比|推荐")
VS_RE = re.compile(r"(?<![a-z])vs(?![a-z])", re.I)
SELF_BRAND = ("wps", "金山", "wps365")
RIVAL_BRAND = ("office", "microsoft", "微软", "腾讯", "飞书", "钉钉", "石墨", "豆包", "千问", "notion", "obsidian", "多人在线")


def is_compare_word(kw):
    """竞品词判定：含中文对比词，或独立 vs，或含自家品牌+竞品名。"""
    if COMPARE_RE.search(kw) or VS_RE.search(kw):
        # 自家品牌词但未含竞品名 → 不算竞品（如 wps是哪个公司的产品、wps下载哪个版本好）
        if any(b in kw.lower() for b in SELF_BRAND) and not any(b in kw.lower() for b in RIVAL_BRAND):
            return False
        return True
    return False


def load_theme_score(path):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def theme_for_word(k):
    """按二级主题/关键词/一级分类映射到 8 月题材热度键。
    导航/下载/官网类词归 NAV（题材分低，主要靠搜索量）。
    """
    sub = k["二级主题"]
    cat1 = k["一级分类"]
    kw = k["关键词"]
    low = kw.lower()
    # 导航/承接类词 → 低题材分
    if any(x in kw for x in ("下载", "官网", "入口", "网页版", "安装", "版本", "正版", "官方", "注册", "登录", "网址")):
        return "NAV"
    # AI 词优先（含 ai/AI 即归 WPS AI，避免“能做ppt的ai”等词被 PPT 题材抢走）
    if "AI" in cat1 or "AI" in sub or "ai" in low:
        return "WPS AI"
    if "表格" in sub or "excel" in low or "表格" in kw:
        return "Excel"
    if any(x in sub for x in ("演示", "PPT", "模板", "汇报", "简历")) or "ppt" in low:
        return "PPT"
    if "PDF" in sub or "转换" in sub or "OCR" in sub or "识别" in sub or "pdf" in low:
        return "PDF"
    if "在线" in sub or "云" in sub or "协同" in sub or "协作" in sub:
        return "在线文档"
    if "文字" in sub or "word" in low:
        return "word"
    if "教程" in sub or "知识" in sub or "功能" in sub or "故障" in sub or "怎么" in kw or "如何" in kw:
        return "WPS教程"
    return "office"


def load_sem_words(path):
    """SEM 词表：CSV（第一列关键词）或 TXT（每行一词）。"""
    if not path or not os.path.isfile(path):
        return set()
    words = set()
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "," in line:
                line = line.split(",")[0]
            words.add(line)
    return words


def load_covered_titles(path=None, cms_token=None):
    """已覆盖标题：文件每行一个标题；缺省尝试从 CMS 拉取（8月已发布）。
    token 优先取参数，其次环境变量 WPS_CMS_TOKEN；两者皆无则跳过拉取。"""
    titles = []
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            titles = [l.strip() for l in f if l.strip()]
        return titles
    token = cms_token or os.environ.get("WPS_CMS_TOKEN")
    if not token:
        sys.stderr.write("[warn] 未提供 CMS token（--cms-token 或环境变量 WPS_CMS_TOKEN），跳过已覆盖剔除\n")
        return titles
    try:
        import requests
        BASE = "https://www.wps.cn/article/api"
        page, size = 1, 50
        while True:
            r = requests.get(f"{BASE}/article/", params={
                "page": page, "size": size, "status": 2, "access_token": token},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            d = r.json()
            data = d.get("data") or []
            titles += [a.get("title") or "" for a in data]
            if not data or len(titles) >= (d.get("total") or 0):
                break
            page += 1
    except Exception as e:
        sys.stderr.write(f"[warn] 拉取已覆盖标题失败：{e}\n")
    return titles

# 保底名额题材白名单：内容型题材必保底（Excel/PDF/word/WPS AI 等用户明确关注），
# NAV（导航下载）不保底，只按推荐分自然参与
GUARANTEED_THEMES = {"Excel", "PPT", "word", "PDF", "WPS教程", "在线文档", "office", "WPS AI"}


def pick_diverse_function(cand, q, theme_score):
    """功能词多样性选取：白名单题材各保底 1 词（取该题材推荐分最高者），
    剩余名额从全部候选按推荐分降序补充。
    保证 Excel/PDF/word/PPT 等核心题材每天都有机会，而不是被单一题材霸榜。"""
    if len(cand) <= q:
        return cand
    buckets = defaultdict(list)
    for k in cand:
        buckets[k["题材"]].append(k)
    for t in buckets:
        buckets[t].sort(key=lambda x: (-x["推荐分"], -x["搜索量"]))
    chosen = []
    # 第一轮：白名单题材各取推荐分最高者（保底名额）
    for t in GUARANTEED_THEMES:
        if t in buckets:
            chosen.append(buckets[t][0])
    # 第二轮：剩余名额按推荐分降序从全部候选补充（未选中的）
    if len(chosen) < q:
        picked_ids = {k["关键词"] for k in chosen}
        rest = [k for k in cand if k["关键词"] not in picked_ids]
        rest.sort(key=lambda x: (-x["推荐分"], -x["搜索量"]))
        chosen += rest[:q - len(chosen)]
    return chosen


def allocate_quota(total):
    raw = [(n, r * total) for n, r in RATIO]
    floors = {n: int(q) for n, q in raw}
    base = sum(floors.values())
    remain = total - base
    order = sorted(raw, key=lambda x: x[1] - int(x[1]), reverse=True)
    for n, _ in order[:remain]:
        floors[n] += 1
    return floors


def main():
    ap = argparse.ArgumentParser(description="WPS SEO 每日关键词规划 v2")
    ap.add_argument("--final-kw", default=None, help="完整词库 CSV（缺省用技能内置 wps_final_kw.csv）")
    ap.add_argument("--daily-csv", default=None)
    ap.add_argument("--theme", default=DEFAULT_THEME)
    ap.add_argument("--sem", default=None, help="SEM 词表 CSV/TXT")
    ap.add_argument("--covered", default=None, help="已覆盖标题文件（每行一个；缺省自动拉 CMS）")
    ap.add_argument("--cms-token", default=None, help="CMS OpenAPI token（拉取已覆盖标题用；或设环境变量 WPS_CMS_TOKEN）")
    ap.add_argument("--state", default=None)
    ap.add_argument("--day", type=int)
    ap.add_argument("--total", type=int, default=30)
    ap.add_argument("--out", default=None)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if not (20 <= args.total <= 30):
        sys.exit(f"[错误] --total 需在 20~30 之间")

    # ---- 数据源 ----
    import pandas as pd
    final_csv = args.final_kw or DEFAULT_FINAL_KW
    daily_csv = args.daily_csv or DEFAULT_DAILY_KW

    words = load_final_kw(final_csv)
    _, daily_only = merge_daily_vol(words, daily_csv)
    words += daily_only
    print(f"[数据] 完整词库清洗后 {len(words)} 词（含 daily 补充 {len(daily_only)} 词）", file=sys.stderr)

    theme_score = load_theme_score(args.theme)
    # NAV 题材兜底分（导航/下载类词内容发挥空间小，给低基础分）
    theme_score.setdefault("NAV", 0.15)
    sem_words = load_sem_words(args.sem)
    if sem_words:
        print(f"[SEM] 已载入 {len(sem_words)} 个 SEM 词", file=sys.stderr)
    else:
        print("[SEM] 未提供 SEM 词表，SEM 分=0（权重 20% 暂时空置）", file=sys.stderr)

    covered_titles = load_covered_titles(args.covered, args.cms_token)
    covered_set = set()
    for t in covered_titles:
        if t:
            covered_set.add(t.lower())
    print(f"[覆盖] 已覆盖标题 {len(covered_set)} 条（用于剔除已写词）", file=sys.stderr)

    # ---- 构建候选池 ----
    pool = []
    for k in words:
        cat = map_category(k["一级分类"])
        if not cat:
            continue
        # 竞品词过滤：词库一级分类有噪音，要求含对比/选型语义才保留
        if cat == "竞品词" and not is_compare_word(k["关键词"]):
            continue
        # 垃圾/截断词过滤
        if k["关键词"] in JUNK_WORDS or JUNK_RE.search(k["关键词"]):
            continue
        kw = k["关键词"]
        # 已覆盖剔除
        if any(t in kw.lower() or kw.lower() in t for t in list(covered_set)[:0]):
            pass
        # 已覆盖剔除：关键词>=4字做子串匹配（避免 wps/word 等短词误伤），短词精确匹配
        kwl = kw.lower()
        if len(kw) >= 4:
            covered_flag = any(kwl in t for t in covered_set)
        else:
            covered_flag = kwl in covered_set
        k["covered"] = covered_flag
        k["题材"] = theme_for_word(k)
        # 在线文档题材词归入功能词池（原在“云文档与在线办公”分类→通用词，
        # 导致功能词保底白名单中的“在线文档”永远落空）
        if cat == "通用词" and k["一级分类"] == "云文档与在线办公" and k["题材"] == "在线文档":
            cat = "功能词"
        k["组别"] = cat
        k["题材分"] = theme_score.get(k["题材"], 0.0)
        k["搜索量"] = max(k.get("月均搜索量", 0.0), k["百度PV"])
        k["SEM分"] = 1.0 if kw.lower() in sem_words else 0.0
        pool.append(k)

    # ---- 组内搜索量归一化（min-max，log 平滑）----
    import math
    groups = defaultdict(list)
    for k in pool:
        groups[k["组别"]].append(k)
    for cat, items in groups.items():
        logs = [math.log10(v + 1) for v in (k["搜索量"] for k in items)]
        mn, mx = min(logs), max(logs)
        for k, lv in zip(items, logs):
            k["搜索量分"] = (lv - mn) / (mx - mn) if mx > mn else 0.0

    # ---- 竞品聚簇：同品牌只保留 TOP2（按搜索量），其余标低分 ----
    def brand_key(kw):
        m = re.match(r"^([a-zA-Z\u4e00-\u9fa5]{2,})", kw)
        return m.group(1).lower() if m else kw.lower()

    for cat in ["竞品词"]:
        items = sorted(groups[cat], key=lambda x: -x["搜索量"])
        seen = defaultdict(int)
        for k in items:
            bk = brand_key(k["关键词"])
            seen[bk] += 1
            if seen[bk] > 2:
                k["搜索量分"] *= 0.3  # 同品牌第3个起大幅降权

    # ---- 推荐分 ----
    for k in pool:
        base = WEIGHTS["搜索量"] * k["搜索量分"] + WEIGHTS["题材热度"] * k["题材分"] + WEIGHTS["SEM"] * k["SEM分"]
        k["推荐分"] = base
        k["covered"] = bool(k.get("covered"))

    # ---- 状态（复用 v1 逻辑，按组记录已用词）----
    state_path = args.state or os.path.join(SKILL_DIR, ".wps_seo_state.json")
    if args.reset or not os.path.isfile(state_path):
        state = {"last_day": 0, "used_by_cat": {}, "updated_at": None}
    else:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    used_by_cat = state.get("used_by_cat", {})
    day = args.day or (state.get("last_day", 0) + 1)
    quota = allocate_quota(args.total)

    rows = []
    rotated = []
    for cat in ["品牌词", "竞品词", "通用词", "功能词"]:
        items = [k for k in pool if k["组别"] == cat and not k["covered"]]
        # 按推荐分降序；同分按搜索量
        items.sort(key=lambda x: (-x["推荐分"], -x["搜索量"]))
        used = set(used_by_cat.get(cat, []))
        cand = [k for k in items if k["关键词"] not in used]
        q = quota[cat]
        if len(cand) < q:
            cand = items  # 轮转
            rotated.append(cat)
        if cat == "功能词":
            # 题材多样性：每个题材保底 1 个名额，剩余按推荐分补充
            chosen = pick_diverse_function(cand, q, theme_score)
        else:
            chosen = cand[:q]
        for k in chosen:
            rows.append((cat, k, k))
            used.add(k["关键词"])
        used_by_cat[cat] = sorted(used)

    # ---- 输出 ----
    title = f"WPS SEO 关键词每日规划 v2 · 第 {day} 天"
    print("=" * 70)
    print(title)
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"词量：{args.total}（品牌{quota['品牌词']}/竞品{quota['竞品词']}/通用{quota['通用词']}/功能{quota['功能词']}）")
    print(f"权重：搜索量{WEIGHTS['搜索量']} / 题材热度{WEIGHTS['题材热度']} / SEM{WEIGHTS['SEM']}（已覆盖词已剔除）")
    print("=" * 70)
    print()
    print("| 策略组别 | 今日关键词 | 搜索量 | 题材 | 题材分 | SEM | 推荐分 | 搜索意图 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for cat, kw, k in rows:
        intent = INTENT[cat]
        print(f"| {cat} | {kw['关键词']} | {kw['搜索量']:.0f} | {kw['题材']} | {kw['题材分']:.2f} | "
              f"{'✓' if kw['SEM分'] else ''} | {kw['推荐分']:.3f} | {intent} |")

    used_total = len(set().union(*[set(v) for v in used_by_cat.values()] or [set()]))
    print()
    print("---")
    print("**覆盖说明**")
    print(f"- 今日新增：{args.total} 词（累计已用 {used_total} 词）")
    print(f"- 已剔除已覆盖词：{len(covered_set)} 标题关键词库剔除")
    if rotated:
        print(f"- 轮转组：{'、'.join(rotated)}")

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"last_day": day, "used_by_cat": used_by_cat,
                   "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=2)
    print(f"\n[状态] {state_path}", file=sys.stderr)

    if args.out:
        out_lines = [
            title,
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"权重：搜索量{WEIGHTS['搜索量']} / 题材热度{WEIGHTS['题材热度']} / SEM{WEIGHTS['SEM']}",
            "",
            "| 策略组别 | 今日关键词 | 搜索量 | 题材 | 题材分 | SEM | 推荐分 | 搜索意图 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for cat, kw, k in rows:
            out_lines.append(
                f"| {cat} | {kw['关键词']} | {kw['搜索量']:.0f} | {kw['题材']} | {kw['题材分']:.2f} | "
                f"{'✓' if kw['SEM分'] else ''} | {kw['推荐分']:.3f} | {INTENT[cat]} |")
        with open(os.path.abspath(args.out), "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(out_lines) + "\n")
        print(f"[导出] {os.path.abspath(args.out)}", file=sys.stderr)


if __name__ == "__main__":
    main()
