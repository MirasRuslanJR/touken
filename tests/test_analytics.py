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
