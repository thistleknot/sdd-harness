"""Task queue implementation."""

from collections import deque

from .task import Task, TaskStatus


class TaskQueue:
    """Simple FIFO task queue."""

    def __init__(self):
        self._tasks: deque[Task] = deque()

    def add(self, task: Task) -> None:
        """Add a task to the queue."""
        self._tasks.append(task)

    def pop(self) -> Task | None:
        """Remove and return the next pending task, or None if empty."""
        for i, task in enumerate(self._tasks):
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.RUNNING
                del self._tasks[i]
                return task
        return None

    def peek(self) -> Task | None:
        """Return the next pending task without removing it."""
        for task in self._tasks:
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def size(self) -> int:
        """Return the number of tasks in the queue."""
        return len(self._tasks)
