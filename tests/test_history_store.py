"""组件3 单元测试：持久化会话历史（HistoryStore）。

运行：``set PYTHONPATH=src && python -m pytest tests/test_history_store.py -q``
"""

from miniclaw.cli.history_store import HistoryStore


def test_append_load_all_tail_stats(tmp_path):
    store = HistoryStore("s-demo", base_dir=str(tmp_path))
    for i in range(3):
        store.append({"role": "user", "content": f"m{i}"})

    # 物理文件存在
    assert store.path.exists()

    loaded = store.load_all()
    assert len(loaded) == 3
    assert loaded[0]["content"] == "m0"
    assert loaded[-1]["content"] == "m2"

    assert len(store.tail(2)) == 2
    assert store.tail(2)[-1]["content"] == "m2"

    stats = store.stats()
    assert stats["session_id"] == "s-demo"
    assert stats["messages"] == 3
    assert stats["bytes"] > 0
    assert stats["updated_at"] is not None
    assert stats["path"] == str(store.path)


def test_corrupted_line_tolerance(tmp_path):
    store = HistoryStore("s-corrupt", base_dir=str(tmp_path))
    store.append({"role": "user", "content": "ok1"})
    # 人为写入一行损坏数据
    with open(store.path, "a", encoding="utf-8") as f:
        f.write("{this is not json}\n")
    store.append({"role": "user", "content": "ok2"})

    loaded = store.load_all()
    assert len(loaded) == 2
    assert loaded[0]["content"] == "ok1"
    assert loaded[1]["content"] == "ok2"


def test_tail_boundary(tmp_path):
    store = HistoryStore("s-tail", base_dir=str(tmp_path))
    for i in range(3):
        store.append({"role": "user", "content": f"m{i}"})

    # n 大于条数：返回全部
    assert len(store.tail(10)) == 3
    # n <= 0：返回空
    assert store.tail(0) == []
    assert store.tail(-1) == []


def test_stats_empty_file(tmp_path):
    store = HistoryStore("s-empty", base_dir=str(tmp_path))
    stats = store.stats()
    assert stats["messages"] == 0
    assert stats["bytes"] == 0
    assert stats["updated_at"] is None


def test_load_all_missing_file(tmp_path):
    store = HistoryStore("s-missing", base_dir=str(tmp_path))
    assert store.load_all() == []
