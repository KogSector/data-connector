"""
Kafka Producer Client for ConFuse Platform
==========================================

Publishes file ingestion events to Kafka topics for downstream processing.
Uses consistent hashing for partition assignment to ensure ordering per source.
"""

import json
import hashlib
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

logger = logging.getLogger(__name__)


@dataclass
class FileIngestedEvent:
    """Event published when a file is ingested from a source"""
    event_id: str
    source_id: str
    file_path: str
    file_type: str
    content: str
    metadata: Dict[str, Any]
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> "FileIngestedEvent":
        return cls(**json.loads(data))


@dataclass
class CodeNormalizedEvent:
    """Event published when code is normalized"""
    event_id: str
    source_id: str
    file_path: str
    language: str
    normalized_content: str
    entities: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))


class ConsistentHashPartitioner:
    """
    DSA: Consistent Hashing for Kafka partition assignment.
    
    Ensures messages with the same key always go to the same partition,
    maintaining ordering guarantees while distributing load evenly.
    """
    
    def __init__(self, num_partitions: int):
        self.num_partitions = num_partitions
        # Virtual nodes for better distribution
        self.virtual_nodes = 150
        self._ring: Dict[int, int] = {}
        self._build_ring()
    
    def _build_ring(self):
        """Build the consistent hash ring with virtual nodes"""
        for partition in range(self.num_partitions):
            for i in range(self.virtual_nodes):
                key = f"partition-{partition}-vnode-{i}"
                hash_val = self._hash(key)
                self._ring[hash_val] = partition
        self._sorted_keys = sorted(self._ring.keys())
    
    def _hash(self, key: str) -> int:
        """MD5 hash for consistent distribution"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def get_partition(self, key: str) -> int:
        """
        Binary search to find the appropriate partition.
        Time complexity: O(log n) where n = num_partitions * virtual_nodes
        """
        if not self._sorted_keys:
            return 0
        
        hash_val = self._hash(key)
        
        # Binary search for the first key >= hash_val
        left, right = 0, len(self._sorted_keys) - 1
        while left < right:
            mid = (left + right) // 2
            if self._sorted_keys[mid] < hash_val:
                left = mid + 1
            else:
                right = mid
        
        # Wrap around if we're past the last key
        if self._sorted_keys[left] < hash_val:
            left = 0
        
        return self._ring[self._sorted_keys[left]]


class KafkaProducerClient:
    """
    High-level Kafka producer with consistent hashing and delivery guarantees.
    """
    
    TOPICS = {
        "file_ingested": "file.ingested",
        "code_normalized": "code.normalized",
        "chunk_created": "chunk.created",
        "embedding_generated": "embedding.generated",
        "graph_updated": "graph.updated",
    }
    
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        client_id: str = "data-connector",
        num_partitions: int = 3,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.partitioner = ConsistentHashPartitioner(num_partitions)
        
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
            "acks": "all",  # Wait for all replicas
            "retries": 3,
            "retry.backoff.ms": 1000,
            "enable.idempotence": True,  # Exactly-once semantics
            "compression.type": "snappy",
            "batch.size": 16384,
            "linger.ms": 10,  # Small batching for low latency
        })
        
        self._pending_messages = 0
        logger.info(f"Kafka producer initialized: {bootstrap_servers}")
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation"""
        self._pending_messages -= 1
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")
    
    def publish_file_ingested(self, event: FileIngestedEvent) -> bool:
        """
        Publish a file ingested event to Kafka.
        Uses source_id as partition key for ordering guarantee per source.
        """
        try:
            partition = self.partitioner.get_partition(event.source_id)
            
            self._producer.produce(
                topic=self.TOPICS["file_ingested"],
                key=event.source_id.encode("utf-8"),
                value=event.to_json().encode("utf-8"),
                partition=partition,
                callback=self._delivery_callback,
            )
            self._pending_messages += 1
            
            # Trigger delivery reports periodically
            self._producer.poll(0)
            
            logger.info(f"Published file.ingested: {event.file_path} -> partition {partition}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish file.ingested: {e}")
            return False
    
    def publish_code_normalized(self, event: CodeNormalizedEvent) -> bool:
        """Publish code normalized event"""
        try:
            partition = self.partitioner.get_partition(event.file_path)
            
            self._producer.produce(
                topic=self.TOPICS["code_normalized"],
                key=event.file_path.encode("utf-8"),
                value=event.to_json().encode("utf-8"),
                partition=partition,
                callback=self._delivery_callback,
            )
            self._pending_messages += 1
            self._producer.poll(0)
            
            return True
        except Exception as e:
            logger.error(f"Failed to publish code.normalized: {e}")
            return False
    
    def flush(self, timeout: float = 10.0):
        """Flush all pending messages"""
        remaining = self._producer.flush(timeout)
        if remaining > 0:
            logger.warning(f"{remaining} messages still pending after flush")
        return remaining == 0
    
    def close(self):
        """Close the producer gracefully"""
        self.flush()
        logger.info("Kafka producer closed")


def create_topics_if_not_exist(
    bootstrap_servers: str = "localhost:9092",
    topics: Optional[List[str]] = None,
):
    """Create Kafka topics if they don't exist"""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    
    if topics is None:
        topics = list(KafkaProducerClient.TOPICS.values())
    
    existing = admin.list_topics().topics.keys()
    new_topics = [
        NewTopic(topic, num_partitions=3, replication_factor=1)
        for topic in topics if topic not in existing
    ]
    
    if new_topics:
        futures = admin.create_topics(new_topics)
        for topic, future in futures.items():
            try:
                future.result()
                logger.info(f"Created topic: {topic}")
            except Exception as e:
                logger.error(f"Failed to create topic {topic}: {e}")
