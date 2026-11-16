"""只根据历史事实计算统计；不写数据库，也不推断答案正确性。"""

from .common import integer, keys, require

DEFAULT_RULE = dict(initial_weight=1, min_weight=1, max_weight=10, grade0_increment=2,
                    grade1_increment=1, consecutive_bonus=1, qualified_retests_required=2)


def validate_rule(parameters, base=None):
    keys(parameters, DEFAULT_RULE)
    result = dict(DEFAULT_RULE if base is None else base, **parameters)
    for key in result:
        result[key] = integer(result, key, minimum=0, maximum=10)
    require(1 <= result["min_weight"] <= result["initial_weight"] <= result["max_weight"] <= 10,
            "权重边界必须满足 1 ≤ 下限 ≤ 初始值 ≤ 上限 ≤ 10")
    require(result["qualified_retests_required"] >= 2, "降权至少需要两次合格复测")
    return result


def empty_stats(concept_id, initial=1):
    return dict(concept_id=concept_id, weight=initial, attempt_count=0, failure_count=0,
                consecutive_failures=0, qualified_retests=0, qualification_anchor_id=None,
                last_grade=None, last_answered_at=None, last_answered_order=None, current_gaps=[])


def replay(concepts, attempts):
    """attempts 为当前有效评估，按真实回答顺序排序；返回统计及每次权重轨迹。"""
    stats = {c["id"]: empty_stats(c["id"]) for c in concepts}
    trail = {}
    completed = []
    anchors = {}
    for a in sorted(attempts, key=lambda x: x["answered_order"]):
        if a["evaluation_status"] != "confirmed" or a["kind"] == "practice":
            continue
        cid, grade, rule = a["concept_id"], a["grade"], a["rule"]
        s = stats[cid]
        if not s["attempt_count"]:
            s["weight"] = rule["initial_weight"]
        before = s["weight"]
        s["attempt_count"] += 1
        s.update(last_grade=grade, last_answered_at=a["answered_at"],
                 last_answered_order=a["answered_order"], current_gaps=a["gaps"])
        if grade < 2:
            s["failure_count"] += 1
            s["consecutive_failures"] += 1
            s["weight"] += rule[f"grade{grade}_increment"]
            if s["consecutive_failures"] >= 2:
                s["weight"] += rule["consecutive_bonus"]
        else:
            s["consecutive_failures"] = 0
        if grade < 3:
            s["qualified_retests"] = 0
            s["qualification_anchor_id"] = None
            anchors.pop(cid, None)
        elif a["kind"] == "retest" and not a["substantive_hint"] and a.get("order_verified", True):
            anchor = anchors.get(cid)
            distance = sum(x["concept_id"] != cid and x["answered_order"] > anchor["answered_order"]
                           for x in completed) if anchor else 0
            if anchor is None or a["session_id"] != anchor["session_id"] or distance >= 2:
                s["qualified_retests"] += 1
                s["qualification_anchor_id"] = a["id"]
                anchors[cid] = a
                if s["qualified_retests"] >= rule["qualified_retests_required"]:
                    s["weight"] -= 1
                    s["qualified_retests"] = 0
                    s["qualification_anchor_id"] = None
                    anchors.pop(cid, None)
        s["weight"] = max(rule["min_weight"], min(rule["max_weight"], s["weight"]))
        trail[a["id"]] = {"before": before, "after": s["weight"]}
        completed.append(a)
    return stats, trail
