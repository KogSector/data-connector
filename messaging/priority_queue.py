"""
Priority Message Queue - DSA Implementation
============================================

A min-heap based priority queue for message ordering.
Supports efficient priority-based message retrieval.

Time Complexity:
- Insert: O(log n)
- Pop: O(log n)
- Peek: O(1)
"""

import heapq
import threading
from typing import Any, Generic, List, Optional, TypeVar
from dataclasses import dataclass, field

T = TypeVar("T")


@dataclass(order=True)
class PriorityItem:
    """Wrapper for priority queue items with stable ordering"""
    priority: int
    sequence: int  # For FIFO ordering within same priority
    item: Any = field(compare=False)


class PriorityMessageQueue(Generic[T]):
    """
    Thread-safe priority queue using a binary min-heap.
    
    Lower priority values = higher priority (processed first).
    For same priority, FIFO ordering is maintained.
    
    Example:
        queue = PriorityMessageQueue()
        queue.push(message1, priority=5)  # Normal priority
        queue.push(message2, priority=1)  # High priority
        queue.pop()  # Returns message2 (priority 1)
    """
    
    def __init__(self, maxsize: int = 0):
        """
        Initialize priority queue.
        
        Args:
            maxsize: Maximum queue size. 0 = unlimited.
        """
        self._heap: List[PriorityItem] = []
        self._sequence = 0
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._maxsize = maxsize
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)
    
    @property
    def empty(self) -> bool:
        return len(self) == 0
    
    @property
    def full(self) -> bool:
        if self._maxsize <= 0:
            return False
        return len(self) >= self._maxsize
    
    def push(self, item: T, priority: int = 5, block: bool = True, timeout: float = None) -> bool:
        """
        Add item to queue with given priority.
        
        Args:
            item: Message to enqueue
            priority: Priority level (lower = higher priority)
            block: If True, block until space is available
            timeout: Maximum time to wait if blocking
            
        Returns:
            True if item was added, False if queue was full
        """
        with self._not_full:
            if self._maxsize > 0:
                if not block:
                    if len(self._heap) >= self._maxsize:
                        return False
                else:
                    while len(self._heap) >= self._maxsize:
                        if not self._not_full.wait(timeout):
                            return False
            
            self._sequence += 1
            entry = PriorityItem(priority, self._sequence, item)
            heapq.heappush(self._heap, entry)
            self._not_empty.notify()
            return True
    
    def pop(self, block: bool = True, timeout: float = None) -> Optional[T]:
        """
        Remove and return highest priority item.
        
        Args:
            block: If True, block until item is available
            timeout: Maximum time to wait if blocking
            
        Returns:
            Item with highest priority (lowest value), or None if empty
        """
        with self._not_empty:
            if not block:
                if not self._heap:
                    return None
            else:
                while not self._heap:
                    if not self._not_empty.wait(timeout):
                        return None
            
            entry = heapq.heappop(self._heap)
            self._not_full.notify()
            return entry.item
    
    def peek(self) -> Optional[T]:
        """Return highest priority item without removing it"""
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0].item
    
    def clear(self):
        """Remove all items from queue"""
        with self._lock:
            self._heap.clear()
            self._not_full.notify_all()
    
    def get_stats(self) -> dict:
        """Get queue statistics"""
        with self._lock:
            if not self._heap:
                return {"size": 0, "priorities": {}}
            
            priorities = {}
            for entry in self._heap:
                priorities[entry.priority] = priorities.get(entry.priority, 0) + 1
            
            return {
                "size": len(self._heap),
                "priorities": priorities,
                "highest_priority": self._heap[0].priority,
            }


class MultiLevelPriorityQueue:
    """
    Multi-level feedback queue for different message types.
    Uses separate heaps for different priority bands.
    
    Bands:
    - Critical (0-2): System alerts, failures
    - High (3-4): User actions, webhooks  
    - Normal (5-6): Regular processing
    - Low (7-9): Background tasks, scheduled jobs
    """
    
    BANDS = {
        "critical": (0, 2),
        "high": (3, 4),
        "normal": (5, 6),
        "low": (7, 9),
    }
    
    def __init__(self):
        self._queues = {band: PriorityMessageQueue() for band in self.BANDS}
        self._lock = threading.Lock()
    
    def push(self, item: Any, priority: int = 5):
        """Add item to appropriate band"""
        band = self._get_band(priority)
        self._queues[band].push(item, priority)
    
    def pop(self, block: bool = False) -> Optional[Any]:
        """
        Pop from highest non-empty band.
        Ensures critical messages are always processed first.
        """
        for band in ["critical", "high", "normal", "low"]:
            queue = self._queues[band]
            if not queue.empty:
                item = queue.pop(block=False)
                if item is not None:
                    return item
        return None
    
    def _get_band(self, priority: int) -> str:
        for band, (low, high) in self.BANDS.items():
            if low <= priority <= high:
                return band
        return "normal"
    
    def get_stats(self) -> dict:
        return {band: q.get_stats() for band, q in self._queues.items()}
