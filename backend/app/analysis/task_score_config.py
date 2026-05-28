from __future__ import annotations

from typing import Literal, TypedDict


ScoreDirection = Literal["lower_is_better"]


class TaskScoreItem(TypedDict):
    key: str
    label: str
    expert_rank: int
    rationale: str


class TaskScoreConfig(TypedDict):
    label: str
    item_count: int
    score_direction: ScoreDirection
    scoring_rule: str
    items: list[TaskScoreItem]


TASK_SCORE_CONFIG: dict[str, TaskScoreConfig] = {
    "moon_survival": {
        "label": "NASA Moon Survival（月球求生任务）",
        "item_count": 15,
        "score_direction": "lower_is_better",
        "scoring_rule": "sum_absolute_rank_difference",
        "items": [
            {
                "key": "oxygen_tanks",
                "label": "两罐 100 磅氧气",
                "expert_rank": 1,
                "rationale": "最紧迫的生存需求，月球无大气",
            },
            {
                "key": "water_5_gallons",
                "label": "5 加仑饮用水",
                "expert_rank": 2,
                "rationale": "补充出汗失去的水分，无替代来源",
            },
            {
                "key": "stellar_map",
                "label": "星象图（月面星座）",
                "expert_rank": 3,
                "rationale": "导航主要手段，月面星象与地球基本一致",
            },
            {
                "key": "food_concentrate",
                "label": "食物浓缩包",
                "expert_rank": 4,
                "rationale": "高效补充能量",
            },
            {
                "key": "solar_fm_transceiver",
                "label": "太阳能调频收发器",
                "expert_rank": 5,
                "rationale": "与母船通信的唯一手段",
            },
            {
                "key": "nylon_rope_50ft",
                "label": "50 英尺尼龙绳",
                "expert_rank": 6,
                "rationale": "攀爬悬崖、捆绑伤员",
            },
            {
                "key": "first_aid_kit",
                "label": "急救箱（含注射针）",
                "expert_rank": 7,
                "rationale": "处理伤口，注射针可注射维生素",
            },
            {
                "key": "parachute_silk",
                "label": "降落伞丝绸",
                "expert_rank": 8,
                "rationale": "遮挡阳光辐射",
            },
            {
                "key": "life_raft",
                "label": "救生筏",
                "expert_rank": 9,
                "rationale": "可在月面尘土上拖运物资",
            },
            {
                "key": "signal_flares",
                "label": "信号弹",
                "expert_rank": 10,
                "rationale": "接近母船时可用作信号",
            },
            {
                "key": "pistols_45_caliber",
                "label": "两把 .45 口径手枪",
                "expert_rank": 11,
                "rationale": "可作为自推进装置",
            },
            {
                "key": "dehydrated_milk",
                "label": "一箱脱水奶粉",
                "expert_rank": 12,
                "rationale": "食物浓缩包的低效替代品",
            },
            {
                "key": "portable_heater",
                "label": "便携式加热装置",
                "expert_rank": 13,
                "rationale": "月球亮面不需要，暗面才有用",
            },
            {
                "key": "magnetic_compass",
                "label": "磁罗盘",
                "expert_rank": 14,
                "rationale": "月球无磁场，完全无用",
            },
            {
                "key": "matches",
                "label": "一盒火柴",
                "expert_rank": 15,
                "rationale": "月球无氧气，无法燃烧",
            },
        ],
    },
    "lost_at_sea": {
        "label": "Lost at Sea（海上求生任务）",
        "item_count": 15,
        "score_direction": "lower_is_better",
        "scoring_rule": "sum_absolute_rank_difference",
        "items": [
            {
                "key": "shaving_mirror",
                "label": "剃须镜",
                "expert_rank": 1,
                "rationale": "白天信号求救，被发现是第一优先",
            },
            {
                "key": "oil_gas_mixture_2_gallons",
                "label": "2 加仑油气混合物",
                "expert_rank": 2,
                "rationale": "漂浮在水面可点燃，夜间信号",
            },
            {
                "key": "water_5_gallons",
                "label": "5 加仑饮用水",
                "expert_rank": 3,
                "rationale": "补充出汗和缺水，短期生存关键",
            },
            {
                "key": "army_c_rations",
                "label": "一箱美军 C 口粮",
                "expert_rank": 4,
                "rationale": "营养补给，维持体力等待救援",
            },
            {
                "key": "opaque_plastic_sheet",
                "label": "20 平方英尺不透明塑料布",
                "expert_rank": 5,
                "rationale": "遮阳避雨，也可收集雨水",
            },
            {
                "key": "chocolate_bars",
                "label": "两箱巧克力棒",
                "expert_rank": 6,
                "rationale": "应急食物，提供热量",
            },
            {
                "key": "fishing_kit",
                "label": "钓鱼套装",
                "expert_rank": 7,
                "rationale": "潜在食物来源，鱼竿可作支撑",
            },
            {
                "key": "nylon_rope_15ft",
                "label": "15 英尺尼龙绳",
                "expert_rank": 8,
                "rationale": "捆绑设备，多用途",
            },
            {
                "key": "floating_seat_cushion",
                "label": "浮力座垫",
                "expert_rank": 9,
                "rationale": "有人落水时的救生装置",
            },
            {
                "key": "shark_repellent",
                "label": "鲨鱼驱避剂",
                "expert_rank": 10,
                "rationale": "在水中时有用",
            },
            {
                "key": "rum_160_proof",
                "label": "160 度朗姆酒（1 夸脱）",
                "expert_rank": 11,
                "rationale": "可作消毒剂，饮用会加速脱水",
            },
            {
                "key": "transistor_radio",
                "label": "小型晶体管收音机",
                "expert_rank": 12,
                "rationale": "超出任何广播电台覆盖范围",
            },
            {
                "key": "pacific_ocean_chart",
                "label": "太平洋海图",
                "expert_rank": 13,
                "rationale": "无导航设备，地图意义不大",
            },
            {
                "key": "mosquito_netting",
                "label": "防蚊网",
                "expert_rank": 14,
                "rationale": "大洋中几乎无蚊虫",
            },
            {
                "key": "sextant",
                "label": "六分仪",
                "expert_rank": 15,
                "rationale": "无天文历表和精确时钟，无法使用",
            },
        ],
    },
    "winter_survival": {
        "label": "Winter Survival（冬季求生任务）",
        "item_count": 12,
        "score_direction": "lower_is_better",
        "scoring_rule": "sum_absolute_rank_difference",
        "items": [
            {
                "key": "windproof_matches",
                "label": "火柴（防风火柴盒）",
                "expert_rank": 1,
                "rationale": "生火是一切的基础，可用于保暖、信号、融雪",
            },
            {
                "key": "candle",
                "label": "蜡烛",
                "expert_rank": 2,
                "rationale": "帮助生火，密闭空间内可升温",
            },
            {
                "key": "large_caliber_pistol",
                "label": "大口径手枪（含子弹）",
                "expert_rank": 3,
                "rationale": "可作为有效求救信号工具",
            },
            {
                "key": "household_knife",
                "label": "家用短刀",
                "expert_rank": 4,
                "rationale": "多用途工具，可切割、制作工具、处理食物",
            },
            {
                "key": "newspapers",
                "label": "报纸（每人一份）",
                "expert_rank": 5,
                "rationale": "可作隔热材料，也可用于引火",
            },
            {
                "key": "hand_axe",
                "label": "手斧",
                "expert_rank": 6,
                "rationale": "砍柴生火的关键工具",
            },
            {
                "key": "wool_scarf",
                "label": "厚羊毛围巾（每人）",
                "expert_rank": 7,
                "rationale": "保护头部和颈部，减少热量散失",
            },
            {
                "key": "vegetable_oil",
                "label": "植物油（1 升）",
                "expert_rank": 8,
                "rationale": "可涂抹皮肤防冻，也可作燃料",
            },
            {
                "key": "flashlight",
                "label": "手电筒（备用电池）",
                "expert_rank": 9,
                "rationale": "夜间信号，辅助探路",
            },
            {
                "key": "whiskey",
                "label": "威士忌酒（1 瓶）",
                "expert_rank": 10,
                "rationale": "可外用消毒，饮用会加速体温下降",
            },
            {
                "key": "local_aerial_map",
                "label": "航空地图（本地区）",
                "expert_rank": 11,
                "rationale": "定位作用有限，暴风雪中方向感差",
            },
            {
                "key": "compass",
                "label": "指南针",
                "expert_rank": 12,
                "rationale": "待在原地等救援比移动更安全，几乎无用",
            },
        ],
    },
}


def get_task_score_config(task_id: str) -> TaskScoreConfig:
    return TASK_SCORE_CONFIG[task_id]


def validate_task_score_config() -> None:
    for task_id, config in TASK_SCORE_CONFIG.items():
        items = config["items"]
        item_count = config["item_count"]
        keys = [item["key"] for item in items]
        ranks = [item["expert_rank"] for item in items]

        if len(items) != item_count:
            raise ValueError(f"{task_id} item_count does not match items length")
        if len(set(keys)) != len(keys):
            raise ValueError(f"{task_id} contains duplicate item keys")
        if sorted(ranks) != list(range(1, item_count + 1)):
            raise ValueError(f"{task_id} expert ranks must be 1..{item_count}")

