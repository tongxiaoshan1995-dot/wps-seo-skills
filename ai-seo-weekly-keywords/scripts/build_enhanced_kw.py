# -*- coding: utf-8 -*-
"""一次生成 AI 方向增强词库。
分类体系（对齐参考技能 wps-seo-weekly-keywords 的业务维度）：
  一级分类 = AI品牌词 / AI场景词 / AI竞品词 / AI认知词（业务/场景维度）
             AI品牌词=仅 WPS AI/WPS灵犀；AI竞品词=其它AI工具品牌+对比选型；
             AI场景词=用AI做具体事（不含任何品牌）；AI认知词=概念认知（是什么/前景/原理）。
  题材     = AI 能力维度（AI写作/AI绘图/AI对话/...），供每日规划周排期轮转
  意图     = 精简6类：品牌认知 / 官网下载 / 教程操作 / 功能对比 / 模板获取 / 场景应用
  操作对象 = 场景细分（写周报/做PPT/生成头像/...）
  工具     = 工具名（豆包/DeepSeek/ChatGPT/WPS灵犀/...）
指纹 = 一级分类×意图×操作对象×工具（四维去重）。每词只归一类意图，6类不重复。
已剔除价格/会员类词（与参考技能一致，每日规划不产出价格词）。
用法：python build_enhanced_kw.py   （词库更新后重跑一次即可）
"""
import csv, re, os
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "assets", "data", "ai_final_kw.csv")
OUT = os.path.join(BASE, "assets", "data", "ai_enhanced_kw.csv")

def norm(kw):
    return re.sub(r"[\u3000\ufeff·、，,。．.！？!?：:；;（）()【】\[\]《》<>/\\|_\-—~～“”\"'`]",
                  "", str(kw).lower())

# ---------- 意图（精简6类，顺序判定，先命中即定，互不重复） ----------
BRAND_COG = r"(是什么|什么意思|有什么用|介绍|简介|原理|知识|趋势|发展|前景|有哪些|怎么学|什么功能|有哪些功能|特色|特点|怎么样|含义|概念|行业|应用价值)"
NAV = r"(官网|官方|入口|登录|下载|网址|注册|账号|免费版|网页版|官网入口)"
COMPARE = r"(哪个好|哪个好用|区别|对比|怎么选|选哪个|vs|代替|替代|优缺点|评测|跑分|好用吗|哪个强|相比|和.*比|哪家)"
TEMP = r"(模板|素材|提示词|prompt|案例|范文|背景图|配色方案)"
HOWTO = r"(怎么写|怎么做|怎么用|怎么|如何|教程|方法|步骤|技巧|使用|制作|生成|入门|操作|部署|接入|调用|api|打不开|报错|错误|失败|解决|不能用|卡|崩溃|未响应|异常|配置|优化|技巧)"
# 场景应用：无以上任何标志的纯痛点场景（写周报/做PPT/生成头像 等兜底）

def classify(n):
    if re.search(BRAND_COG, n): return "品牌认知"
    if re.search(NAV, n): return "官网下载"
    if re.search(COMPARE, n): return "功能对比"
    if re.search(TEMP, n): return "模板获取"
    if re.search(HOWTO, n): return "教程操作"
    return "场景应用"

PRICE = r"(免费|价格|会员|收费|多少钱|值得|开通|年费|月费|续费|充值|贵不贵|性价比)"

# ---------- 模板/提示词补充词（保证 模板获取 意图充足，6类均衡） ----------
def gen_tpl_words():
    """返回 关键词->(一级分类,操作对象,工具) 的模板类补充词。
    目的：意图精简为6类后，模板获取意图若无品牌/竞品模板词会偏少，
    这里为品牌/场景/竞品三类补充 模板/提示词 词，供周一~周五模板获取排期。"""
    WRITE = ["周报","日报","工作总结","论文","作文","文案","简历","邮件","公文","方案",
             "演讲稿","读后感","日记","小说","脚本","标题","报告","通知","合同","项目总结",
             "会议纪要","调研报告","辞职信"]
    VISUAL = ["做ppt","做海报","生成头像","做简历","做思维导图","做数据图表","做表格",
              "生成背景图","生成壁纸","生成插画","做logo","做商品图","做证件照","生成表情包"]
    out = {}
    # 品牌模板词
    for pref in ["WPS灵犀", "WPS AI"]:
        for s in WRITE:
            out[f"{pref}写{s}模板"] = ("AI品牌词", f"写{s}", "WPS灵犀" if "灵犀" in pref else "WPS AI")
        for s in VISUAL[:6]:
            out[f"{pref}{s}模板"] = ("AI品牌词", s, "WPS灵犀" if "灵犀" in pref else "WPS AI")
        for s in WRITE[:12] + ["做ppt","生成图片","做表格","数据分析","翻译","写代码"]:
            out[f"{pref}{s}提示词"] = ("AI品牌词", s, "WPS灵犀" if "灵犀" in pref else "WPS AI")
        out[f"{pref}提示词大全"] = ("AI品牌词", "提示词大全", "WPS灵犀" if "灵犀" in pref else "WPS AI")
        out[f"{pref}prompt模板"] = ("AI品牌词", "prompt模板", "WPS灵犀" if "灵犀" in pref else "WPS AI")
    # 场景模板词
    for s in WRITE:
        out[f"AI写{s}模板"] = ("AI场景词", f"写{s}", "AI")
        out[f"AI{s}提示词"] = ("AI场景词", s, "AI")
    for s in VISUAL:
        out[f"AI{s}模板"] = ("AI场景词", s, "AI")
    out["AI提示词大全"] = ("AI场景词", "提示词大全", "AI")
    out["AI写作prompt"] = ("AI场景词", "写作prompt", "AI")
    out["AI绘图prompt"] = ("AI场景词", "绘图prompt", "AI")
    out["AI提示词模板"] = ("AI场景词", "提示词模板", "AI")
    # 竞品模板词
    for t in ["豆包","ChatGPT","DeepSeek","Kimi","文心一言","通义千问","Claude","Gemini"]:
        for s in ["写周报","写论文","写文案","做ppt","生成图片"]:
            out[f"{t}{s}提示词"] = ("AI竞品词", s, t)
        out[f"{t}提示词大全"] = ("AI竞品词", "提示词大全", t)
        out[f"{t}prompt模板"] = ("AI竞品词", "prompt模板", t)
    return out
TPL_WORDS = gen_tpl_words()

# ---------- AI 能力题材（从关键词推导，供周排期） ----------
SUBJECT_RULES = [
    ("AI写作", r"(写|写作|作文|文案|小说|脚本|标题|论文|周报|日报|总结|邮件|公文|演讲稿|简历|读后感|日记|方案|小红书|朋友圈|推文|报告|通知|致辞|调研)"),
    ("AI绘图", r"(绘|画|图|插画|头像|海报|logo|壁纸|证件照|商品图|表情包|水彩|绘本|设计图|背景图|产品图|修图|抠图)"),
    ("AI对话", r"(对话|聊天|问答|角色扮演|头脑风暴|咨询|辅导|心理|英语|翻译|学外语|陪聊|情感)"),
    ("AI视频", r"(视频|剪辑|数字人|字幕|转场|换脸|抠像|开场动画|口播|宣传片|vlog|文生视频|短视频|分镜)"),
    ("AI音频", r"(音频|配音|音乐|声音|人声|语音|转文字|转写|克隆|降噪|合成|有声书|音效|变声)"),
    ("AI编程", r"(代码|编程|函数|调试|bug|重构|爬虫|脚本|测试用例|sql|api|正则|单元测试|前端|后端|自动化)"),
    ("AI办公", r"(办公|ppt|excel|表格|word|文档|会议|纪要|思维导图|数据分析|图表|pdf|整理|校对|润色|格式转换)"),
    ("AI搜索", r"(搜索|联网|浏览器|查资料|阅读论文|搜索答案|学术|深度|资讯)"),
    ("大模型", r"(大模型|gpt|llama|qwen|千问|deepseek|豆包大模型|上下文|部署|api|多模态|agent|模型|推理|微调)"),
    ("AI认知", r"(ai|人工智能|aigc|生成式|智能|应用|趋势|前景|原理|知识|学习路线|入门|行业|岗位|赚钱|变现|工作|产业|未来)"),
]
def subject(n):
    for name, pat in SUBJECT_RULES:
        if re.search(pat, n): return name
    return "AI认知"

# ---------- 一级分类（来自 ai_final_kw.csv 已打好标） ----------
CAT3_MAP = {"AI品牌词":"AI品牌词","AI场景词":"AI场景词","AI竞品词":"AI竞品词","AI认知词":"AI认知词"}

THEME_SCORE = {"AI写作":0.9,"AI绘图":0.85,"AI对话":0.9,"AI办公":0.88,"AI编程":0.8,
    "AI视频":0.78,"AI音频":0.65,"大模型":0.82,"AI搜索":0.7,"AI认知":0.75}
CONTENT = {"官网下载":"高关联(整篇AI)","品牌认知":"高关联(整篇AI)",
    "教程操作":"中关联(AI+工具章节)","场景应用":"中关联(AI+工具章节)",
    "模板获取":"中关联(AI+工具章节)","功能对比":"中关联(AI+工具章节)"}

def main():
    rows = []
    with open(SRC, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            kw = str(r.get("关键词") or "").strip()
            if not kw or kw.lower() == "nan":
                continue
            cat3 = str(r.get("一级分类") or "").strip() or "AI场景词"
            scene = str(r.get("二级主题") or "").strip() or "通用"
            tool = str(r.get("搜索意图") or "").strip() or "通用"
            hot = str(r.get("搜索热度") or "").strip() or "中"
            try:
                hs = float(str(r.get("热度分") or "").strip())
            except Exception:
                hs = 0.6
            rows.append({"关键词": kw, "一级分类": cat3, "对象": scene, "工具": tool, "搜索热度": hot, "热度分": hs})

    # 补充模板/提示词词（final 已有则不重复，保证 模板获取 意图充足）
    rows_keys = {norm(x["关键词"]) for x in rows}
    for kw, (cat3, scene, tool) in TPL_WORDS.items():
        if norm(kw) in rows_keys:
            continue
        rows.append({"关键词": kw, "一级分类": cat3, "对象": scene, "工具": tool,
                     "搜索热度": "中", "热度分": 0.6})
        rows_keys.add(norm(kw))

    out, seen = [], set()
    for r in rows:
        n = norm(r["关键词"])
        if re.search(PRICE, n):
            continue  # 剔除价格/会员类词
        intent = classify(n)
        sb = subject(n)
        fp = f"{r['一级分类']}·{intent}·{r['对象']}·{r['工具']}"
        if fp in seen:
            continue
        seen.add(fp)
        content = CONTENT.get(intent, "中关联(AI+工具章节)")
        ts = THEME_SCORE.get(sb, 0.7)
        out.append([r["关键词"], sb, r["一级分类"], intent, r["对象"], r["工具"],
                    fp, content, ts, r["搜索热度"], r["热度分"]])

    print(f"增强词库 {len(out)} 条，唯一指纹 {len(seen)} 个")
    print("题材(AI能力):", dict(Counter(x[1] for x in out)))
    print("一级分类(四类):", dict(Counter(x[2] for x in out)))
    print("意图(6类):", dict(Counter(x[3] for x in out)))
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["关键词","题材","一级分类","意图","操作对象","工具","指纹","内容策略","题材分","搜索热度","热度分"])
        for x in out:
            w.writerow(x)
    print("已保存:", OUT)

if __name__ == "__main__":
    main()
