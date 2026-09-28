from evrptw_autolab.memory.lessons import LessonMemory


def test_lesson_memory_roundtrip(tmp_path) -> None:
    memory = LessonMemory(tmp_path / "lessons.jsonl", max_total=3)
    memory.add({"lesson": "battery first"})
    memory.add({"lesson": "keep working routing"})
    rows = memory.retrieve("battery", k=1)
    assert rows
    assert "battery" in rows[0]["lesson"]
