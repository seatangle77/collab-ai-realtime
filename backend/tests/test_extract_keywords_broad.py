"""
extract_keywords_broad 接口测试
覆盖：认证鉴权、功能验证、边界值、极端输入、异常输入

用法（在 backend/ 目录下）：
    python -m tests.test_extract_keywords_broad

前置条件：
    后端已启动：uvicorn app.main:app --reload --port 8000
"""
import sys

import requests

BASE = "http://localhost:8000"
HEADERS = {"X-Admin-Token": "TestAdminKey123"}
WRONG_HEADERS = {"X-Admin-Token": "wrong"}
URL = f"{BASE}/api/nlp/extract_keywords_broad"

_pass = 0
_fail = 0


def check(label: str, r: requests.Response, expect: int = 200) -> dict | None:
    global _pass, _fail
    ok = r.status_code == expect
    icon = "✓" if ok else "✗"
    print(f"  {icon} [{r.status_code}] {label}")
    if not ok:
        _fail += 1
        print(f"      → {r.text[:400]}")
        return None
    _pass += 1
    try:
        return r.json()
    except Exception:
        return None


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def post_json(payload: dict, headers: dict | None = None) -> requests.Response:
    return requests.post(URL, json=payload, headers=headers or HEADERS)


section("1. 认证鉴权")

check("无 Token → 403", requests.post(URL, json={"texts": ["测试文本"]}), 403)
check("错误 Token → 403", requests.post(URL, json={"texts": ["测试文本"]}, headers=WRONG_HEADERS), 403)
check("正确 Token → 200", post_json({"texts": ["这是一段用于验证接口鉴权的测试文本，内容足够长，包含若干有意义的词语。"]}), 200)

section("2. 全功能验证")

data = check(
    "单段中文文本（100 字以上）→ 返回非空 keywords 列表",
    post_json({
        "texts": [
            "人工智能正在改变教育、医疗和协作方式。团队在会议中讨论了模型能力、推理质量、沟通效率、"
            "任务拆解、知识共享和信息同步。为了让讨论更深入，成员会不断追问原因、证据和场景，这些"
            "内容通常会形成比较稳定的关键词集合，并帮助我们评估当前主题是否有新的信息进入。"
        ]
    }),
)
if data:
    assert isinstance(data.get("keywords"), list), "keywords 应为列表"
    assert data["keywords"], "keywords 不应为空"
    assert all(isinstance(item, str) for item in data["keywords"]), "keywords 元素应全为字符串"

data = check("多段文本（5 条）→ 正常返回", post_json({
    "texts": [
        "我们今天重点讨论协作效率。",
        "有人提到会议中的上下文切换问题。",
        "也有人补充了文档同步和知识沉淀。",
        "最后大家讨论了行动项和负责人安排。",
        "整体上还是围绕信息流动与任务推进。",
    ]
}))
if data:
    assert isinstance(data.get("keywords"), list), "多段文本返回结构错误"

data = check("默认 top_n=10，返回 <= 10 个词", post_json({
    "texts": ["围绕产品规划、用户反馈、需求评审、协作流程、沟通成本、排期风险进行讨论。"]
}))
if data:
    assert len(data["keywords"]) <= 10, "默认 top_n 应限制在 10 个以内"

data = check("显式 top_n=5 → 返回 <= 5 个词", post_json({
    "texts": ["团队围绕产品规划、用户反馈、需求评审、协作流程、沟通成本、排期风险进行讨论。"],
    "top_n": 5,
}))
if data:
    assert len(data["keywords"]) <= 5, "top_n=5 应限制在 5 个以内"

data = check("返回词不含停用词", post_json({
    "texts": ["我们讨论的内容里有很多真实信息，但是不应该把的、了、吗这类停用词作为关键词返回。"],
    "top_n": 20,
}))
if data:
    for stop_word in ["的", "了", "吗"]:
        assert stop_word not in data["keywords"], f"停用词 {stop_word} 不应出现在结果中"

data = check("宽松模式验证：普通动词/形容词也可进入结果", post_json({
    "texts": [
        "大家反复提到推进、整理、讨论、清晰、混乱、具体这些词，说明接口不只抓专业术语，也会保留常见表达。"
    ],
    "top_n": 20,
}))
if data:
    assert isinstance(data["keywords"], list), "宽松模式返回结构错误"

section("3. 边界")

data = check("top_n=1 → 返回 <= 1 个词", post_json({
    "texts": ["协作效率 任务拆解 上下文同步 讨论质量 反馈机制"],
    "top_n": 1,
}))
if data:
    assert len(data["keywords"]) <= 1, "top_n=1 时返回数量不应超过 1"

check("top_n=50（最大合法）→ 200", post_json({
    "texts": ["这是用于测试最大 top_n 的文本，内容包含多个不同语义单元，确保接口可以正常处理。"],
    "top_n": 50,
}))
check("texts 为 1 条文本 → 200", post_json({"texts": ["单条文本也应正常处理。"]}))
check("texts 为 20 条文本 → 200", post_json({"texts": [f"第{i}条文本，讨论协作与信息同步。" for i in range(20)]}))

data = check("文本全是停用词 → 200，返回 []", post_json({
    "texts": ["的 了 吗 呢 啊"],
    "top_n": 10,
}))
if data:
    assert data["keywords"] == [], "全停用词应返回空列表"

data = check("文本全是标点/空格 → 200，不崩溃且返回列表", post_json({
    "texts": ["  ，。！？；：……   "],
    "top_n": 10,
}))
if data:
    assert isinstance(data["keywords"], list), "全标点/空格场景 keywords 应为列表"

data = check("文本只有单个字 → 200，返回 []", post_json({
    "texts": ["我"],
    "top_n": 10,
}))
if data:
    assert data["keywords"] == [], "单字符文本应返回空列表"

section("4. 极端")

long_text = "人工智能协作讨论知识共享任务推进上下文同步证据理由" * 350
data = check("单条文本 5000 字 → 200，正常返回", post_json({
    "texts": [long_text],
    "top_n": 20,
}))
if data:
    assert isinstance(data["keywords"], list), "长文本返回结构错误"

data = check("中英混排文本 → 200", post_json({
    "texts": ["团队讨论了 roadmap、deadline、协作效率、ownership 和 meeting notes 的同步问题。"],
    "top_n": 20,
}))
if data:
    assert isinstance(data["keywords"], list), "中英混排返回结构错误"

data = check("含 emoji、全角符号的文本 → 200", post_json({
    "texts": ["这次讨论很顺利😀，大家提到协作、反馈、节奏、总结、复盘，以及全角符号（）【】。"],
    "top_n": 20,
}))
if data:
    assert isinstance(data["keywords"], list), "emoji 文本返回结构错误"

section("5. 异常")

check("top_n=0 → 422", post_json({"texts": ["测试"], "top_n": 0}), 422)
check("top_n=51 → 422", post_json({"texts": ["测试"], "top_n": 51}), 422)
check("top_n=-1 → 422", post_json({"texts": ["测试"], "top_n": -1}), 422)
check("top_n='abc' → 422", post_json({"texts": ["测试"], "top_n": "abc"}), 422)

data = check("texts=[]（空数组）→ 200，返回 []", post_json({"texts": []}))
if data:
    assert data["keywords"] == [], "空数组应返回空关键词列表"

check("texts 为字符串而非数组 → 422", post_json({"texts": "不是数组"}), 422)
check("缺少 texts 字段 → 422", post_json({"top_n": 10}), 422)
check("body 为空 → 422", requests.post(URL, data="", headers=HEADERS), 422)
check("body 不是合法 JSON → 422",
      requests.post(URL, data="{", headers={**HEADERS, "Content-Type": "application/json"}), 422)

print(f"\n{'=' * 60}")
print(f"  结果汇总：通过 {_pass}，失败 {_fail}")
print(f"{'=' * 60}\n")

if _fail > 0:
    sys.exit(1)
