import heapq
import itertools


class PriorityQueue:
    def __init__(self):
        self._queue = []
        self._insert_ctr = itertools.count()

    def push(self, item, priority):
        count = next(self._insert_ctr)
        entry = (priority, count, item)
        heapq.heappush(self._queue, entry)

    def pop(self):
        return heapq.heappop(self._queue)[2]

    def peek(self):
        return self._queue[0][2]

    def size(self):
        return len(self._queue)

    def empty(self):
        return len(self._queue) == 0
