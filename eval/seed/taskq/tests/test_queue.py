"""Basic tests for TaskQueue."""

from taskq import Task, TaskQueue, TaskStatus


def test_add_and_size():
    q = TaskQueue()
    assert q.size() == 0
    q.add(Task(name="t1"))
    assert q.size() == 1
    q.add(Task(name="t2"))
    assert q.size() == 2


def test_pop_returns_pending():
    q = TaskQueue()
    q.add(Task(name="t1"))
    task = q.pop()
    assert task is not None
    assert task.name == "t1"
    assert task.status == TaskStatus.RUNNING


def test_pop_empty_returns_none():
    q = TaskQueue()
    assert q.pop() is None
