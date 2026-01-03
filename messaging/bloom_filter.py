"""
Bloom Filter for Message Deduplication - DSA Implementation
============================================================

Space-efficient probabilistic data structure for detecting duplicate messages.
False positives possible, but no false negatives.

Space Complexity: O(m) where m = number of bits
Time Complexity: O(k) for add/check where k = number of hash functions
"""

import hashlib
import math
from typing import List, Optional
import threading


class BloomDeduplicator:
    """
    Bloom filter for message deduplication.
    
    Uses multiple hash functions to map message IDs to bit positions.
    Provides fast O(1) lookups for detecting duplicates with low memory.
    
    Example:
        dedup = BloomDeduplicator(expected_items=100000, false_positive_rate=0.01)
        
        # Check if message was seen before
        if not dedup.check_and_add(message_id):
            process_message(message)  # New message
        else:
            skip_message(message)  # Duplicate
    """
    
    def __init__(
        self,
        expected_items: int = 100000,
        false_positive_rate: float = 0.01,
        bit_array: Optional[bytearray] = None,
    ):
        """
        Initialize Bloom filter.
        
        Args:
            expected_items: Expected number of unique items
            false_positive_rate: Acceptable false positive rate (0-1)
            bit_array: Optional pre-existing bit array for restoration
        """
        # Calculate optimal size and number of hash functions
        # m = -(n * ln(p)) / (ln(2)^2)
        # k = (m/n) * ln(2)
        
        self._size = self._calculate_optimal_size(expected_items, false_positive_rate)
        self._num_hashes = self._calculate_optimal_hashes(self._size, expected_items)
        
        # Bit array (using bytearray for efficiency)
        if bit_array is not None:
            self._bits = bit_array
        else:
            self._bits = bytearray(math.ceil(self._size / 8))
        
        self._count = 0
        self._lock = threading.Lock()
        
        # Statistics
        self._checks = 0
        self._positives = 0
    
    @staticmethod
    def _calculate_optimal_size(n: int, p: float) -> int:
        """Calculate optimal bit array size"""
        m = -(n * math.log(p)) / (math.log(2) ** 2)
        return int(math.ceil(m))
    
    @staticmethod
    def _calculate_optimal_hashes(m: int, n: int) -> int:
        """Calculate optimal number of hash functions"""
        k = (m / n) * math.log(2)
        return int(math.ceil(k))
    
    def _get_hash_values(self, item: str) -> List[int]:
        """
        Generate k hash values using double hashing technique.
        h(i) = (h1 + i * h2) mod m
        
        This is more efficient than computing k independent hashes.
        """
        # Use SHA-256 split into two 128-bit values
        digest = hashlib.sha256(item.encode()).digest()
        h1 = int.from_bytes(digest[:16], byteorder="big")
        h2 = int.from_bytes(digest[16:], byteorder="big")
        
        # Ensure h2 is odd for better distribution
        if h2 % 2 == 0:
            h2 += 1
        
        return [(h1 + i * h2) % self._size for i in range(self._num_hashes)]
    
    def _get_bit(self, position: int) -> bool:
        """Get bit at position"""
        byte_index = position // 8
        bit_index = position % 8
        return bool(self._bits[byte_index] & (1 << bit_index))
    
    def _set_bit(self, position: int):
        """Set bit at position"""
        byte_index = position // 8
        bit_index = position % 8
        self._bits[byte_index] |= (1 << bit_index)
    
    def add(self, item: str):
        """Add item to bloom filter"""
        with self._lock:
            positions = self._get_hash_values(item)
            for pos in positions:
                self._set_bit(pos)
            self._count += 1
    
    def check(self, item: str) -> bool:
        """
        Check if item might be in the filter.
        
        Returns:
            True if item might be present (could be false positive)
            False if item is definitely not present
        """
        with self._lock:
            self._checks += 1
            positions = self._get_hash_values(item)
            result = all(self._get_bit(pos) for pos in positions)
            if result:
                self._positives += 1
            return result
    
    def check_and_add(self, item: str) -> bool:
        """
        Atomically check if item exists and add if not.
        
        Returns:
            True if item was already present (duplicate)
            False if item was new (just added)
        """
        with self._lock:
            positions = self._get_hash_values(item)
            exists = all(self._get_bit(pos) for pos in positions)
            
            if not exists:
                for pos in positions:
                    self._set_bit(pos)
                self._count += 1
            
            self._checks += 1
            if exists:
                self._positives += 1
            
            return exists
    
    def get_stats(self) -> dict:
        """Get filter statistics"""
        with self._lock:
            # Estimate false positive rate
            # p' = (1 - e^(-kn/m))^k
            fill_ratio = self._count * self._num_hashes / self._size
            estimated_fp = (1 - math.exp(-fill_ratio)) ** self._num_hashes
            
            return {
                "size_bits": self._size,
                "size_bytes": len(self._bits),
                "num_hashes": self._num_hashes,
                "items_added": self._count,
                "checks": self._checks,
                "positives": self._positives,
                "fill_ratio": fill_ratio,
                "estimated_false_positive_rate": estimated_fp,
            }
    
    def to_bytes(self) -> bytes:
        """Serialize filter to bytes for persistence"""
        return bytes(self._bits)
    
    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        expected_items: int,
        false_positive_rate: float,
    ) -> "BloomDeduplicator":
        """Restore filter from bytes"""
        return cls(
            expected_items=expected_items,
            false_positive_rate=false_positive_rate,
            bit_array=bytearray(data),
        )


class RotatingBloomFilter:
    """
    Time-based rotating bloom filter for deduplication with expiry.
    
    Uses multiple bloom filters that rotate periodically,
    allowing old entries to expire naturally.
    """
    
    def __init__(
        self,
        expected_items: int = 100000,
        false_positive_rate: float = 0.01,
        num_buckets: int = 3,
    ):
        self._buckets = [
            BloomDeduplicator(expected_items // num_buckets, false_positive_rate)
            for _ in range(num_buckets)
        ]
        self._current = 0
        self._lock = threading.Lock()
    
    def rotate(self):
        """
        Rotate to next bucket (call periodically, e.g., every hour).
        Clears the oldest bucket for reuse.
        """
        with self._lock:
            self._current = (self._current + 1) % len(self._buckets)
            # Clear the bucket we're rotating into
            self._buckets[self._current] = BloomDeduplicator(
                expected_items=100000 // len(self._buckets),
                false_positive_rate=0.01,
            )
    
    def check_and_add(self, item: str) -> bool:
        """Check across all buckets, add to current bucket"""
        with self._lock:
            # Check all buckets
            for bucket in self._buckets:
                if bucket.check(item):
                    return True  # Duplicate found
            
            # Add to current bucket
            self._buckets[self._current].add(item)
            return False
