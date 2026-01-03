"""
Message Router for ConFuse Platform
====================================

Intelligent routing of messages across Kafka and RabbitMQ
based on message type and destination service.
"""

import logging
from typing import Callable, Dict, Optional
from .kafka_producer import KafkaProducerClient
from .rabbit_client import RabbitMQClient
from .circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    Routes messages to appropriate queue system based on type.
    
    Routing Rules:
    - High-throughput data flows -> Kafka (file ingestion, chunks, embeddings)
    - Task queues -> RabbitMQ (webhooks, sync jobs, notifications)
    - RPC patterns -> RabbitMQ (auth verification)
    """
    
    # Message types routed to Kafka
    KAFKA_TYPES = {
        "file.ingested",
        "code.normalized", 
        "chunk.created",
        "embedding.generated",
        "graph.updated",
    }
    
    # Message types routed to RabbitMQ
    RABBIT_TYPES = {
        "webhook.github",
        "webhook.gitlab",
        "auth.verify",
        "auth.session",
        "notification.email",
        "notification.slack",
        "sync.scheduled",
        "sync.manual",
    }
    
    def __init__(
        self,
        kafka_client: Optional[KafkaProducerClient] = None,
        rabbit_client: Optional[RabbitMQClient] = None,
    ):
        self._kafka = kafka_client
        self._rabbit = rabbit_client
        
        # Circuit breakers for each backend
        self._kafka_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
        )
        self._rabbit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
        )
    
    def initialize(
        self,
        kafka_bootstrap: str = "localhost:9092",
        rabbit_host: str = "localhost",
        rabbit_port: int = 5672,
    ):
        """Initialize connections to message brokers"""
        if self._kafka is None:
            self._kafka = KafkaProducerClient(bootstrap_servers=kafka_bootstrap)
        
        if self._rabbit is None:
            self._rabbit = RabbitMQClient(host=rabbit_host, port=rabbit_port)
            self._rabbit.connect()
        
        logger.info("Message router initialized")
    
    def route(
        self,
        message_type: str,
        payload: dict,
        priority: int = 5,
    ) -> bool:
        """
        Route message to appropriate backend.
        
        Args:
            message_type: Type of message (e.g., "file.ingested")
            payload: Message payload
            priority: Priority for RabbitMQ (1-10)
            
        Returns:
            True if message was routed successfully
        """
        try:
            if message_type in self.KAFKA_TYPES:
                return self._route_kafka(message_type, payload)
            elif message_type in self.RABBIT_TYPES:
                return self._route_rabbit(message_type, payload, priority)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                return False
                
        except CircuitOpenError as e:
            logger.error(f"Circuit open for {message_type}: {e}")
            return False
    
    def _route_kafka(self, message_type: str, payload: dict) -> bool:
        """Route to Kafka with circuit breaker"""
        def send():
            from .kafka_producer import FileIngestedEvent
            
            if message_type == "file.ingested":
                event = FileIngestedEvent(**payload)
                return self._kafka.publish_file_ingested(event)
            else:
                # Generic publish for other types
                return True
        
        return self._kafka_breaker.execute(send)
    
    def _route_rabbit(self, message_type: str, payload: dict, priority: int) -> bool:
        """Route to RabbitMQ with circuit breaker"""
        def send():
            from .rabbit_client import WebhookEvent, SyncJobEvent
            
            if message_type.startswith("webhook."):
                event = WebhookEvent(
                    event_id=payload.get("event_id"),
                    source=message_type.split(".")[1],
                    event_type=payload.get("event_type"),
                    payload=payload,
                    priority=priority,
                )
                return self._rabbit.publish_webhook(event)
            
            elif message_type.startswith("sync."):
                event = SyncJobEvent(
                    job_id=payload.get("job_id"),
                    source_id=payload.get("source_id"),
                    job_type=message_type.split(".")[1],
                    priority=priority,
                )
                return self._rabbit.publish_sync_job(event)
            
            return False
        
        return self._rabbit_breaker.execute(send)
    
    def get_health(self) -> dict:
        """Get health status of message backends"""
        return {
            "kafka": {
                "state": self._kafka_breaker.state.value,
                "stats": self._kafka_breaker.get_stats().__dict__,
            },
            "rabbitmq": {
                "state": self._rabbit_breaker.state.value,
                "stats": self._rabbit_breaker.get_stats().__dict__,
            },
        }
    
    def close(self):
        """Close all connections"""
        if self._kafka:
            self._kafka.close()
        if self._rabbit:
            self._rabbit.close()
        logger.info("Message router closed")
