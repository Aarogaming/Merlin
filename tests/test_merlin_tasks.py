from merlin_tasks import MerlinTaskManager


def test_cancel_task_invokes_registered_hook_and_updates_status(tmp_path):
    manager = MerlinTaskManager(tasks_file=str(tmp_path / "tasks.json"))
    task = manager.add_task("t1", "desc", "Medium")
    callbacks = []

    assert manager.register_cancellation_hook(task["id"], lambda: callbacks.append("called")) is True
    assert manager.cancel_task(task["id"]) is True
    assert callbacks == ["called"]

    updated_task = manager.get_task(task["id"])
    assert updated_task is not None
    assert updated_task["status"] == "Cancelled"


def test_register_cancellation_hook_rejects_invalid_inputs(tmp_path):
    manager = MerlinTaskManager(tasks_file=str(tmp_path / "tasks.json"))

    assert manager.register_cancellation_hook(0, lambda: None) is False
    assert manager.register_cancellation_hook(1, None) is False


def test_cancel_task_returns_false_when_task_and_hook_missing(tmp_path):
    manager = MerlinTaskManager(tasks_file=str(tmp_path / "tasks.json"))
    assert manager.cancel_task(1234) is False
