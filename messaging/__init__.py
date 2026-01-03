# ConFuse Messaging Library for Python Services
# =============================================
# Provides Kafka and RabbitMQ integration with DSA-optimized patterns

from .kafka_producer import KafkaProducerClient, FileIngestedEvent
from .kafka_consumer import KafkaConsumerClient
from .rabbit_client import RabbitMQClient
from .message_router import MessageRouter
from .priority_queue import PriorityMessageQueue
from .circuit_breaker import CircuitBreaker
from .bloom_filter import BloomDeduplicator

__all__ = [
    "KafkaProducerClient",
    "KafkaConsumerClient", 
    "FileIngestedEvent",
    "RabbitMQClient",
    "MessageRouter",
    "PriorityMessageQueue",
    "CircuitBreaker",
    "BloomDeduplicator",
]
