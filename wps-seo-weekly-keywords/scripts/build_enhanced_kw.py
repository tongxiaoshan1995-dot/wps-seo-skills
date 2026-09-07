# -*- coding: utf-8 -*-
"""一次性生成增强词库：在原始词库基础上，为每个词打上 题材/意图/操作对象/指纹/内容策略 标签，
并保留 百度统计PV(搜索量)/题材分 等价值字段，输出 wps_enhanced_kw.csv 作为重写后 plan_daily.py 的唯一数据源。"""
import csv, re, os

BASE = r"C:\Users\kingsoft\AppData\Roaming\WPS 灵犀\serverdir\user_skills\wps-seo-weekly-keywords"
SRC = os.path.join(BASE, "assets", "data", "wps_final_kw.csv")
DAILY = os.path.join(BASE, "assets", "data", "wps_daily_kw.csv")
OUT = os.path.join(BASE, "assets", "data", "wps_enhanced_kw.csv")

def norm(kw):
    return re.sub(r"[\u3000\ufeff·、，,。．.！？!?：:；;（）()【】\[\]《》<>/\\|_\-—~～“”\"'`]","",str(kw).lower())

OP_VERBS = r"(怎么写|怎么做|怎么用|怎么|如何|教程|操作方法|方法|步骤|技巧|设置|使用|制作|创建|插入|删除|合并|拆分|转换|导出|导入|排版|美化|入门|进阶|教学|实例|调整|修改|生成|查找|公式|函数|勾选|筛选|排序|计算|统计|样式|编号|序号|题注|目录|页眉|页脚|批注|修订|加密|打印|分享|协作|编辑|录制|演示|替换|提取|填充|压缩|打钩|去水印|显示|识别|改写|移除|去掉|冻结|隐藏|汇总|透视|粘贴|复制|合并单元格|拆分单元格|缩小|放大|旋转|添加|上传|保存|另存|批处理|批量|快捷|快捷键|组合|配对|对齐|行高|列宽|换行|分页|加粗|斜体|下划线|字体|字号|颜色|填充色|边框|底纹|分栏|缩进|项目符号|页边距|纸张|打印区域|链接|超链接|书签|域|宏|vba|图表|图形|图片|形状|艺术字|smartart|数据透视|数据验证|条件格式|合并计算|分类汇总)"
FAULT = r"(打不开|无法打开|打开失败|报错|错误|崩溃|闪退|乱码|丢失|损坏|修复|解决|卡顿|白屏|黑屏|不兼容|兼容|导出失败|保存失败|失效|异常|未响应|打不了|恢复|找回|误删)"
COMPARE = r"(哪个好|哪个好用|和.*区别|与.*区别|对比|区别|怎么选|如何选|替代|代替|选哪个|还是|vs|好用吗|怎么样|好不好|优缺点|优劣)"
PRICE = r"(多少钱|价格表|价格|收费|费用|值得|值不值|会员|开通|购买|年费|月费|划不划算|性价比|要不要花钱|免费版|限免|免费试用|充值|续费|贵不贵)"
DOWN = r"(下载|安装|卸载|重装|最新版|免费下载|安装包|安卓|ios|绿色版|离线包|破解版|激活)"
TEMP = r"(模板|背景|字体库|素材|封面|图标|范文|壁纸|简历模板|计划表|表格模板)"
AI = r"(ai|人工智能|智能|灵犀|自动生成|一键生成|大模型|智能写作|智能排版|ai写|ai生成|deepseek|豆包|千问|文心|通义|对话|助手)"
BRAND_NAV = r"(官网|官方|正版|管网|\.cn|\.com|国际版|企业版|旗舰版|专业版|网页版|在线版|入口|网址|官网首页|线上|网页|官方版)"
FUNC_COG = r"(是什么|是干什么|什么意思|干什么|有哪些|有什么用|作用|功能|介绍|简介|详解|了解|知识|主要|包括)"

def classify(kw, n):
    if re.search(OP_VERBS, n): return "教程操作"
    if re.search(FAULT, n): return "故障解决"
    if re.search(COMPARE, n): return "对比选型"
    if re.search(PRICE, n): return "价格购买"
    if re.search(TEMP, n): return "模板获取"
    if re.search(DOWN, n): return "下载安装"
    if re.search(AI, n): return "AI认知"
    if re.search(BRAND_NAV, n): return "品牌直达"
    if re.search(FUNC_COG, n): return "功能认知"
    for c in ["powerpoint","excel","word","ppt","pdf","wps","office","金山文档","云文档","思维导图","流程图"]:
        if c in n: return "品牌直达"
    return "弃用"

SUBJECT_RULES = [
    ("WPS AI", r"(ai|人工智能|灵犀|智能|一键生成|自动生成|ai写|ai生成|大模型|对话|助手|deepseek|豆包|千问|文心|通义|智能排版|智能写作)"),
    ("PDF", r"(pdf|acrobat)"),
    ("PPT", r"(ppt|powerpoint|演示|幻灯片)"),
    ("Excel", r"(excel|表格|电子表格|透视|xlsx|xls|函数|条件格式|subtotal|xlookup|vlookup|sumproduct)"),
    ("Word", r"(word|文字|docx|doc|页眉|页脚|正文|文档排版|文字处理)"),
    ("云文档/在线", r"(云文档|在线|金山文档|云端|协作|分享|网页版|在线文档|协同|多人)"),
    ("Office通用", r"(office|办公软件|办公套件|微软|microsoft|wpsoffice)"),
    ("下载/安装", r"(下载|安装|卸载|重装|破解版|绿色版|安装包|离线包|激活)"),
    ("WPS综合", r"(wps|金山)"),
]
def subject(kw, n):
    for name, pat in SUBJECT_RULES:
        if re.search(pat, n): return name
    return "其他/泛"

OBJ_HINTS = ["合并单元格","拆分单元格","vlookup","xlookup","函数","数据透视","条件格式",
             "页眉","页脚","目录","批注","修订","图表","模板","水印","打印","分页",
             "公式","表格","幻灯片","背景","简历","打不开","乱码","下载","安装",
             "合并","拆分","转word","转excel","转ppt","加密","解密","宏","vba","字体","行距"]
def object_of(n):
    for o in OBJ_HINTS:
        if o in n: return o
    return "通用"

def content_strategy(n, it):
    if re.search(r"(wps|金山|官网|会员|office|word|excel|ppt|pdf)", n) and it in ("品牌直达","价格购买","下载安装"):
        return "高关联(整篇WPS)"
    if it in ("教程操作","故障解决","模板获取","功能认知","AI认知"):
        return "中关联(通用+WPS章节)"
    return "低关联(方法论轻带)"

# 读取原词库
rows=[]
with open(SRC, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append(r)

# 读取daily补充月均搜索量
daily_pv={}
if os.path.isfile(DAILY):
    with open(DAILY, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            daily_pv[r['关键词'].strip().lower()]=r.get('月均搜索量','')

def to_num(v):
    try: return float(str(v).strip())
    except: return 0.0

# 题材分映射（沿用 theme_score.json，键统一为大写风格）
THEME_SCORE = {"WPS AI":0.0,"Office通用":0.857,"WPS综合":0.8135,"PPT":1.0,"PDF":0.2212,
               "Word":0.4224,"云文档/在线":0.4399,"Excel":0.274,"下载/安装":0.0,"其他/泛":0.0}

out_rows=[]
for row in rows:
    kw = str(row.get('关键词') or '').strip()
    if not kw or kw.lower()=='nan': continue
    n = norm(kw)
    it = classify(kw, n)
    if it in ('弃用','价格购买'): continue  # 运营要求：剔除会员/价格类词（题材与内容层均不产出）
    sb = subject(kw, n)
    obj = object_of(n)
    fp = f"{sb}·{it}·{obj}"
    cs = content_strategy(n, it)
    pv = max(to_num(row.get('百度统计PV')), to_num(daily_pv.get(kw.lower(),0)))
    out_rows.append({
        "关键词": kw, "题材": sb, "意图": it, "操作对象": obj, "指纹": fp,
        "内容策略": cs, "题材分": THEME_SCORE.get(sb, 0.0),
        "搜索量": pv, "需求级别": str(row.get('需求级别') or '').strip(),
    })

# 写入增强词库
with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["关键词","题材","意图","操作对象","指纹","内容策略","题材分","搜索量","需求级别"])
    w.writeheader()
    for r in out_rows:
        w.writerow(r)

print(f"增强词库生成: {len(out_rows)} 词 → {OUT}")
from collections import Counter
print("题材分布:", dict(Counter(r['题材'] for r in out_rows)))
print("意图分布:", dict(Counter(r['意图'] for r in out_rows)))
print("唯一指纹数:", len(set(r['指纹'] for r in out_rows)))
