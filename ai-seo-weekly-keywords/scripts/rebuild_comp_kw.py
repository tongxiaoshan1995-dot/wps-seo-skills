# -*- coding: utf-8 -*-
"""按本月(2026-09)最新排名重写 AI竞品词。
口径：主流工具10词/长尾工具6词。数据源 _new_comp_tools.json。
将 ai_final_kw.csv 中 AI竞品词 整段替换为新生成词，品牌/场景/认知词保持不变。
"""
import csv, re, os, json, shutil, datetime

SK = r"C:\Users\kingsoft\AppData\Roaming\WPS 灵犀\serverdir\user_skills\ai-seo-weekly-keywords"
FIN = os.path.join(SK, "assets", "data", "ai_final_kw.csv")
BAK = os.path.join(SK, "assets", "data", "_bak")
TOOLS_JSON = os.path.join(BAK, "_new_comp_tools.json")

with open(TOOLS_JSON, encoding="utf-8") as f:
    TOOLS = json.load(f)  # [tool, heat, subject, mainstream]

# 题材 -> 场景应用对象（写周报等痛点场景，不含品牌）
SCENE = {
    "AI对话": ["写周报", "写论文", "写文案", "聊天", "做PPT", "查资料"],
    "大模型": ["写周报", "写论文", "写代码", "推理", "问答", "做PPT"],
    "AI办公": ["写周报", "做PPT", "做表格", "写会议纪要", "数据分析", "翻译", "写方案"],
    "AI编程": ["写代码", "写SQL", "调试bug", "自动化脚本", "代码重构", "做自动化"],
    "AI绘图": ["生成头像", "做海报", "生成插画", "做logo", "修图", "生成壁纸"],
    "AI视频": ["剪视频", "生成数字人", "做短视频", "视频换脸", "生成口播"],
    "AI音频": ["配音", "生成音乐", "语音转文字", "文字转语音"],
    "AI搜索": ["查资料", "搜索答案", "深度研究", "联网搜索", "阅读论文"],
}
# 题材 -> 教程操作扩展（用于主流工具，丰富教程意图）
HOWTO_EXTRA = {
    "大模型": ["本地部署", "API接入", "微调"],
    "AI编程": ["API接入", "命令行", "配置"],
    "AI对话": ["API接入"],
    "AI办公": ["接入", "插件"],
    "AI搜索": ["联网搜索"],
}

def hot(hs):
    if hs >= 0.75: return "高"
    if hs >= 0.6: return "中"
    if hs >= 0.45: return "低"
    return "长尾极低"

def gen_main(tool, heat, subject):
    """主流工具 10 词：品牌2 官网2 教程2 对比2 场景2（场景必保）"""
    scenes = SCENE.get(subject, SCENE["AI对话"])
    howto_extra = HOWTO_EXTRA.get(subject, [])
    w = []
    # 品牌认知
    w.append((f"{tool}是什么", "是什么", heat))
    w.append((f"{tool}功能介绍", "功能介绍", heat))
    # 官网下载
    w.append((f"{tool}官网", "官网", heat))
    w.append((f"{tool}下载", "下载", heat * 0.8))
    # 教程操作（技术向用 API接入/本地部署 替换 使用教程，非技术用 使用教程）
    if subject in ("AI编程", "大模型") and howto_extra:
        w.append((f"{tool}怎么用", "怎么用", heat * 0.8))
        w.append((f"{tool}{howto_extra[0]}", howto_extra[0], heat * 0.8))
    else:
        w.append((f"{tool}怎么用", "怎么用", heat * 0.8))
        w.append((f"{tool}使用教程", "使用教程", heat * 0.75))
    # 功能对比
    w.append((f"{tool}哪个好", "哪个好", heat * 0.85))
    w.append((f"{tool}评测", "评测", heat * 0.7))
    # 场景应用（必保）
    w.append((f"{tool}{scenes[0]}", scenes[0], heat * 0.5))
    w.append((f"{tool}{scenes[1]}", scenes[1], heat * 0.5))
    return w[:10]

def gen_tail(tool, heat, subject):
    """长尾工具 6 词：品牌1 官网1 教程1 对比1 场景2"""
    scenes = SCENE.get(subject, SCENE["AI对话"])
    w = [
        (f"{tool}是什么", "是什么", heat),
        (f"{tool}官网", "官网", heat),
        (f"{tool}怎么用", "怎么用", heat * 0.8),
        (f"{tool}哪个好", "哪个好", heat * 0.85),
        (f"{tool}{scenes[0]}", scenes[0], heat * 0.5),
        (f"{tool}{scenes[1]}", scenes[1], heat * 0.5),
    ]
    return w

def main():
    # 读取现有 final，保留非竞品行
    keep = []
    with open(FIN, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        for r in reader:
            if r.get("一级分类") == "AI竞品词":
                continue
            keep.append(r)

    # 生成新竞品词
    new_rows = []
    fp_seen = set()
    for tool, heat, subject, mainstream in TOOLS:
        words = gen_main(tool, heat, subject) if mainstream else gen_tail(tool, heat, subject)
        for kw, obj, hs in words:
            new_rows.append({
                "关键词": kw, "一级分类": "AI竞品词",
                "二级主题": obj, "搜索意图": tool,
                "搜索热度": hot(hs), "热度分": round(hs, 2),
                "数据来源": "2026-09最新排名重建（主流10词/长尾6词）"
            })

    # 合并写回
    rows = keep + new_rows
    with open(FIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print("非竞品行:", len(keep), "新竞品行:", len(new_rows), "总行:", len(rows))
    print("竞品工具数:", len(TOOLS))
    print("题材分布:", dict(Counter(x["搜索意图"] for x in new_rows)))
    print("一级分类:", dict(Counter(x["一级分类"] for x in rows)))
    print("保存:", FIN)

if __name__ == "__main__":
    main()
