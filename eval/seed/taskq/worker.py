"""Worker that processes tasks from a queue."""

import time

from .queue import TaskQueue
from .task import Task, TaskStatus


class Worker:
    """Processes tasks from a TaskQueue."""

    def __init__(self, queue: TaskQueue):
        self.queue = queue

    def process_one(self) -> Task | None:
        """Pop and process a single task. Returns the task or None."""
        task = self.queue.pop()
        if task is None:
            return None
        try:
            self._execute(task)
            task.status = TaskStatus.DONE
        except Exception:
            task.status = TaskStatus.FAILED
        return task

    def run(self, poll_interval: float = 0.1) -> None:
        """Run loop: process tasks until the queue is empty."""
        while self.queue.size() > 0:
            result = self.process_one()
            if result is None:
                time.sleep(poll_interval)

    def _execute(self, task: Task) -> None:
        """Execute a task. Override in subclasses for real work."""
        pass
