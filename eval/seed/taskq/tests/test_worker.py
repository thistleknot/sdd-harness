"""Tests for Worker."""

from taskq import Task, TaskQueue, TaskStatus, Worker


class FailingWorker(Worker):
    """Worker subclass that raises on execute."""

    def _execute(self, task):
        raise RuntimeError("boom")


def test_process_one_success():
    q = TaskQueue()
    q.add(Task(name="t1"))
    w = Worker(q)
    result = w.process_one()
    assert result is not None
    assert result.name == "t1"
    assert result.status == TaskStatus.DONE


def test_process_one_failure():
    q = TaskQueue()
    q.add(Task(name="t1"))
    w = FailingWorker(q)
    result = w.process_one()
    assert result is not None
    assert result.status == TaskStatus.FAILED


def test_process_one_empty_queue():
    q = TaskQueue()
    w = Worker(q)
    assert w.process_one() is None


def test_run_drains_queue():
    q = TaskQueue()
    q.add(Task(name="t1"))
    q.add(Task(name="t2"))
    q.add(Task(name="t3"))
    w = Worker(q)
    w.run()
    assert q.size() == 0
