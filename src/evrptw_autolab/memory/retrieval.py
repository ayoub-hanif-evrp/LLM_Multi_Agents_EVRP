from evrptw_autolab.memory.lessons import LessonMemory


def retrieve_lessons(memory: LessonMemory, target: str, k: int = 5) -> list[dict]:
    return memory.retrieve(target, k=k)
