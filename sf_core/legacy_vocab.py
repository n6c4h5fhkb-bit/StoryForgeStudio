"""English state codes used by shortdrama-director 1.2.x boards, with their Chinese wording.

Copied from the 1.2.6 prompt renderer so old projects can be converted once into plain Chinese.
New projects never need this: they write state in Chinese from the start.
"""
from __future__ import annotations

LABELS = {
    "access": "准入状态",
    "action": "动作状态",
    "attitude": "态度",
    "body": "身体状态",
    "brake": "轮椅刹车",
    "charge": "能量余量",
    "clothing": "衣装",
    "condition": "状态",
    "contact": "接触部位",
    "costume": "服装",
    "count": "数量",
    "door": "门的状态",
    "eyes": "眼睛",
    "facing": "朝向",
    "form": "形态",
    "grade": "品级",
    "health": "生命状态",
    "holder": "持有关系",
    "injury": "伤情",
    "knows_aunt_player": "对小姨玩家身份的认知",
    "level": "等级",
    "lid": "棺盖",
    "light": "光照",
    "lighting": "光照",
    "mirror": "镜面状态",
    "mobility": "行动能力",
    "mode": "形态",
    "open": "开合状态",
    "outfit": "服装",
    "permission": "知情状态",
    "place": "所在处",
    "pose": "姿态",
    "position": "位置",
    "power": "状态",
    "preservation": "保存状态",
    "recovery": "恢复设施状态",
    "response": "回应",
    "san": "理智值",
    "screen": "屏幕内容",
    "signal": "求援信号",
    "signed": "签署状态",
    "structure": "结构",
    "time": "时间",
    "visibility": "可见程度",
    "ward": "防护状态",
    "wardrobe": "服装",
    "wave": "攻势"
}

VALUES = {
    "action": {
        "air_counter": "气流反击",
        "resting": "休息",
        "water_defense": "水系防御"
    },
    "charge": {
        "empty": "无能量",
        "full": "已充满",
        "partial": "部分充能"
    },
    "clothing": {
        "restored_white_opaque": "白衣破损已修复，完整不透明",
        "torn_white_opaque": "白衣有破损，仍完整遮蔽且不透明"
    },
    "door": {
        "broken": "破损",
        "intact": "完好"
    },
    "holder": {
        "mixed": "由下述多人分别持有",
        "none": "无人持有"
    },
    "light": {
        "day": "日间",
        "night": "夜间"
    },
    "lighting": {
        "day": "日间",
        "night": "夜间"
    },
    "mode": {
        "absent": "已不存在",
        "approaching": "接近中",
        "attached": "附着",
        "bypassing": "绕行",
        "held": "手持",
        "hostile": "敌对",
        "locked": "锁定",
        "placed": "放置",
        "surrender": "投降",
        "unlocked": "解锁",
        "worn": "穿戴"
    },
    "pose": {
        "crouching": "蹲着",
        "fallen": "倒地",
        "seated": "坐着",
        "standing": "站立"
    },
    "power": {
        "depleted": "已耗尽",
        "fading": "正在衰退",
        "temporary": "暂时维持"
    },
    "recovery": {
        "formed_unpowered": "设施已成形，尚无供能",
        "idle_no_live_supply": "暂时闲置，无持续供能",
        "thin_qi": "微弱灵气",
        "unbuilt": "尚未建成"
    },
    "structure": {
        "expanded_worksite": "已扩建的施工结构",
        "original": "原有结构"
    },
    "visibility": {
        "half_hidden": "半遮蔽",
        "visible": "可见"
    },
    "ward": {
        "active": "防护生效",
        "inactive_currently": "防护当前未生效",
        "unbuilt": "防护尚未建成"
    }
}

PLACES = {
    "bed_array": "床阵位置",
    "bed_center": "床中央",
    "bed_foot": "床脚",
    "bed_front": "床前",
    "bed_side": "床边",
    "before_desk": "桌前",
    "before_desk_stepback": "桌前后退处",
    "behind_defenders": "防御者后方",
    "beside_desk": "桌旁",
    "door": "门边",
    "door_array": "门口阵法",
    "door_block": "门口挡路处",
    "door_ground": "门口地面",
    "door_inside": "门内",
    "door_preplaced": "门边预先放置处",
    "estate_door": "府门边",
    "floor": "地面",
    "going_city": "前往城中",
    "gone": "已离开",
    "hands": "双手",
    "hands_split_batch": "双手分批搬持",
    "head_seat": "主位",
    "in_box": "盒内",
    "inner_hall": "内堂",
    "leaving": "离开中",
    "left_attacking": "左路进攻位",
    "left_defense": "左侧防御位",
    "left_door_floor": "门左地面",
    "left_door_recoil": "门左受击后退处",
    "left_flank": "左翼",
    "left_wall_leaning": "倚在左墙边",
    "outside": "室外",
    "outside_ground": "室外地面",
    "outside_stepback": "室外后退处",
    "outside_stopped": "门外停步处",
    "outside_wall_offscreen": "画外的外墙边",
    "pool_distance": "距池一段距离处",
    "pool_side": "池边",
    "rear_extension": "后方扩建区",
    "right_attacking": "右路进攻位",
    "right_defense": "右侧防御位",
    "right_flank": "右翼",
    "right_hand": "右手",
    "right_hand_thrust": "右手前刺位置",
    "right_wall": "右墙边",
    "right_wall_floor": "右墙脚地面",
    "road_edge": "路边",
    "room": "屋内",
    "shop": "店内",
    "split_hidden_and_box": "一部分藏起，一部分在盒内",
    "split_hidden_and_outside": "一部分藏起，一部分在门外",
    "subjective_information_layer": "主观信息画面",
    "table": "桌上",
    "wall_inside": "墙内侧",
    "window": "窗边",
    "worksite": "工地",
    "wrong_array": "错误阵位"
}
