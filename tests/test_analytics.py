"""
Unit-тесты для analytics.build_analysis, с упором на крайние случаи:
классы из 0–2 учеников и классы без единого ответа не должны падать или
делить на ноль.

Запуск:  pytest        (или)  python -m pytest
"""
from app.analytics import build_analysis


def students(n):
    return [{"id": i, "full_name": "S%d" % i} for i in range(1, n + 1)]


def positive(a, b, q="cinema"):
    return {"from_student": a, "to_student": b, "question": q}


def test_empty_graph_density_zero():
    res = build_analysis([], [])
    gm = res["graph_metrics"]
    assert gm["density"] == 0
    assert gm["students"] == 0
    assert gm["isolates"] == 0
    assert gm["mutual_pairs"] == 0
    assert gm["wellbeing_index"] == 0
    assert res["nodes"] == []
    assert res["edges"] == []


def test_class_without_any_answers_does_not_crash():
    res = build_analysis(students(5), [])
    gm = res["graph_metrics"]
    assert gm["density"] == 0
    assert gm["mutual_pairs"] == 0
    assert gm["isolates"] == 5            # никто никого не выбрал → все изоляты
    assert gm["wellbeing_index"] == 0
    assert len(res["nodes"]) == 5


def test_single_student_does_not_crash():
    res = build_analysis(students(1), [])
    gm = res["graph_metrics"]
    assert gm["students"] == 1
    assert gm["density"] == 0
    assert len(res["nodes"]) == 1


def test_two_students_one_mutual_pair():
    res = build_analysis(students(2), [positive(1, 2), positive(2, 1)])
    gm = res["graph_metrics"]
    assert gm["mutual_pairs"] == 1
    assert gm["isolates"] == 0
    per = res["per_student"]
    assert per["1"]["mutual"] == 1
    assert per["2"]["mutual"] == 1


def test_isolate_and_alone_votes():
    # 2 и 3 выбирают друг друга, 1 — никем не выбран (изолят) и отмечен "часто один"
    choices = [positive(2, 3), positive(3, 2), {"from_student": 2, "to_student": 1, "question": "alone"}]
    res = build_analysis(students(3), choices)
    per = res["per_student"]
    assert per["1"]["is_isolate"] is True
    assert per["1"]["alone_votes"] == 1
    assert res["graph_metrics"]["mutual_pairs"] == 1


def test_node_size_within_bounds():
    # один популярный ученик на фоне остальных — размеры узлов остаются в диапазоне
    choices = [positive(2, 1), positive(3, 1), positive(4, 1)]
    res = build_analysis(students(4), choices)
    sizes = [node["size"] for node in res["nodes"]]
    assert all(14.0 <= s <= 40.0 for s in sizes)


# ---------------------------------------------------------------- явка
# Отсутствие входящих выборов означает изоляцию только тогда, когда достаточная
# часть класса реально ответила. Иначе популярный ребёнок, чьи друзья не прошли
# опрос, получал красный бейдж «изолят» — и психолог шёл работать с ребёнком,
# у которого нет проблемы.

def test_low_turnout_does_not_produce_isolates():
    # 10 учеников, ответили трое (30%) — и выбрали только друг друга.
    choices = [positive(1, 2), positive(2, 1), positive(3, 1)]
    res = build_analysis(students(10), choices, responded_ids=[1, 2, 3])
    gm = res["graph_metrics"]
    assert gm["reliability"] == "low"
    assert gm["isolates"] == 0, "при явке 30% статус «изолят» не ставится"
    # Без входящих выборов остались семеро не ответивших плюс ученик 3.
    assert gm["unknown"] == 8
    assert gm["wellbeing_index"] is None, "индекс при низкой явке не считается"
    assert res["per_student"]["7"]["status"] == "unknown"
    assert res["per_student"]["7"]["is_isolate"] is False


def test_full_turnout_still_detects_a_real_isolate():
    # Тот же ребёнок без входящих выборов, но ответил весь класс — это сигнал.
    choices = [positive(1, 2), positive(2, 1), positive(3, 1), positive(4, 2), positive(5, 1)]
    res = build_analysis(students(5), choices, responded_ids=[1, 2, 3, 4, 5])
    gm = res["graph_metrics"]
    assert gm["reliability"] == "high"
    assert res["per_student"]["3"]["status"] == "isolate"
    assert res["per_student"]["3"]["is_isolate"] is True
    assert gm["unknown"] == 0
    assert gm["wellbeing_index"] is not None


def test_structural_metrics_use_the_responding_subgraph():
    """Плотность считается среди ответивших: иначе класс с явкой 40% выглядел
    бы разобщённым просто из-за неявки."""
    # Ответили четверо из 20, между собой связаны плотно.
    choices = [positive(a, b) for a in (1, 2, 3, 4) for b in (1, 2, 3, 4) if a != b]
    res = build_analysis(students(20), choices, responded_ids=[1, 2, 3, 4])
    # 12 рёбер на 4 узлах = полный граф среди ответивших.
    assert res["graph_metrics"]["density"] == 1.0
    assert res["graph_metrics"]["reciprocity"] == 1.0


def test_responded_flag_is_exposed_per_student():
    res = build_analysis(students(4), [positive(1, 2)], responded_ids=[1])
    assert res["per_student"]["1"]["responded"] is True
    assert res["per_student"]["4"]["responded"] is False


# --------------------------------------------- порог по номинациям «часто один»

def test_alone_votes_below_threshold_are_not_reportable():
    alone = [{"from_student": i, "to_student": 5, "question": "alone"} for i in (1, 2)]
    res = build_analysis(students(5), alone)
    m = res["per_student"]["5"]
    assert m["alone_votes"] == 2
    assert m["alone_reportable"] is False
    # В подсказке на графе точное число ниже порога не показывается.
    node = [n for n in res["nodes"] if n["id"] == 5][0]
    assert "менее 3" in node["title"]


def test_alone_votes_at_threshold_are_reportable():
    alone = [{"from_student": i, "to_student": 5, "question": "alone"} for i in (1, 2, 3)]
    res = build_analysis(students(5), alone)
    m = res["per_student"]["5"]
    assert m["alone_votes"] == 3
    assert m["alone_reportable"] is True


def test_alone_question_never_creates_graph_edges():
    alone = [{"from_student": 1, "to_student": 2, "question": "alone"}]
    res = build_analysis(students(3), alone)
    assert res["edges"] == []
    assert res["graph_metrics"]["positive_edges"] == 0
