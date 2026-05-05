from app.memory_store import load_work_state, load_tasks


def get_session_snapshot():
    work_state = load_work_state()
    tasks = load_tasks().get("tasks", [])

    pending_tasks = [t for t in tasks if t.get("status") != "done"]

    return {
        "current_focus": work_state.get("current_focus", ""),
        "last_completed_step": work_state.get("last_completed_step", ""),
        "next_step": work_state.get("next_step", ""),
        "pending_tasks": pending_tasks[:5]
    }