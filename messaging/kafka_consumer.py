"""
Kafka Consumer Client for ConFuse Platform
==========================================

Consumes messages from Kafka topics with automatic offset management,
error handling, and dead-letter queue support.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass
from confluent_kafka import Consumer, KafkaError, KafkaException
from confluent_kafka import Producer

logger = logging.getLogger(__name__)


@dataclass
class ConsumedMessage:
    """Wrapper for consumed Kafka messages"""
    topic: str
    partition: int
    offset: int
    key: Optional[str]
    value: Dict[str, Any]
    timestamp: int
    
    @classmethod
    def from_kafka_message(cls, msg) -> "ConsumedMessage":
        return cls(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=msg.key().decode("utf-8") if msg.key() else None,
            value=json.loads(msg.value().decode("utf-8")),
            timestamp=msg.timestamp()[1],
        )


class KafkaConsumerClient:
    """
    High-level Kafka consumer with automatic offset management
    and dead-letter queue support.
    """
    
    DLQ_PREFIX = "dlq."
    
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "default-consumer-group",
        topics: list = None,
        auto_commit: bool = True,
        max_retries: int = 3,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topics = topics or []
        self.max_retries = max_retries
        
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": auto_commit,
            "auto.commit.interval.ms": 5000,
            "session.timeout.ms": 30000,
            "max.poll.interval.ms": 300000,  # 5 minutes for long processing
        })
        
        # Producer for DLQ
        self._dlq_producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "client.id": f"{group_id}-dlq",
        })
        
        self._running = False
        self._retry_counts: Dict[str, int] = {}
        
        if self.topics:
            self._consumer.subscribe(self.topics)
            logger.info(f"Subscribed to topics: {self.topics}")
    
    def subscribe(self, topics: list):
        """Subscribe to additional topics"""
        self.topics.extend(topics)
        self._consumer.subscribe(self.topics)
        logger.info(f"Subscribed to topics: {topics}")
    
    def consume_one(self, timeout: float = 1.0) -> Optional[ConsumedMessage]:
        """Consume a single message"""
        msg = self._consumer.poll(timeout)
        
        if msg is None:
            return None
        
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                return None
            raise KafkaException(msg.error())
        
        return ConsumedMessage.from_kafka_message(msg)
    
    def consume_batch(
        self,
        handler: Callable[[ConsumedMessage], bool],
        batch_size: int = 100,
        timeout: float = 1.0,
    ) -> int:
        """
        Consume and process a batch of messages.
        
        Args:
            handler: Function that processes each message, returns True on success
            batch_size: Maximum messages to process in one batch
            timeout: Poll timeout in seconds
            
        Returns:
            Number of successfully processed messages
        """
        processed = 0
        
        for _ in range(batch_size):
            msg = self.consume_one(timeout)
            if msg is None:
                break
            
            try:
                success = handler(msg)
                if success:
                    processed += 1
                else:
                    self._handle_failure(msg)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                self._handle_failure(msg, str(e))
        
        return processed
    
    def _handle_failure(self, msg: ConsumedMessage, error: str = None):
        """Send failed message to dead-letter queue after max retries"""
        msg_key = f"{msg.topic}:{msg.partition}:{msg.offset}"
        
        self._retry_counts[msg_key] = self._retry_counts.get(msg_key, 0) + 1
        
        if self._retry_counts[msg_key] >= self.max_retries:
            # Send to DLQ
            dlq_topic = f"{self.DLQ_PREFIX}{msg.topic}"
            dlq_message = {
                "original_topic": msg.topic,
                "original_partition": msg.partition,
                "original_offset": msg.offset,
                "original_value": msg.value,
                "error": error,
                "retry_count": self._retry_counts[msg_key],
            }
            
            self._dlq_producer.produce(
                topic=dlq_topic,
                key=msg.key.encode("utf-8") if msg.key else None,
                value=json.dumps(dlq_message).encode("utf-8"),
            )
            self._dlq_producer.flush()
            
            logger.warning(f"Message sent to DLQ: {dlq_topic}")
            del self._retry_counts[msg_key]
    
    def run_forever(
        self,
        handler: Callable[[ConsumedMessage], bool],
        batch_size: int = 100,
    ):
        """Run consumer loop indefinitely"""
        self._running = True
        logger.info(f"Starting consumer loop for group: {self.group_id}")
        
        try:
            while self._running:
                self.consume_batch(handler, batch_size)
        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
        finally:
            self.close()
    
    def stop(self):
        """Stop the consumer loop"""
        self._running = False
    
    def close(self):
        """Close the consumer gracefully"""
        self._consumer.close()
        self._dlq_producer.flush()
        logger.info("Kafka consumer closed")
