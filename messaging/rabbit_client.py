"""
RabbitMQ Client for ConFuse Platform
=====================================

Provides async RabbitMQ operations for task queues, webhooks, and notifications.
Implements priority queues and RPC patterns.
"""

import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass, asdict
import pika
from pika.adapters.blocking_connection import BlockingChannel

logger = logging.getLogger(__name__)


@dataclass
class WebhookEvent:
    """Webhook event to be processed"""
    event_id: str
    source: str  # "github" or "gitlab"
    event_type: str  # "push", "pull_request", etc.
    payload: Dict[str, Any]
    priority: int = 5  # 1-10, higher = more urgent
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> "WebhookEvent":
        return cls(**json.loads(data))


@dataclass
class SyncJobEvent:
    """Sync job event"""
    job_id: str
    source_id: str
    job_type: str  # "scheduled" or "manual"
    priority: int = 5
    metadata: Dict[str, Any] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))


class RabbitMQClient:
    """
    RabbitMQ client for task queues and notifications.
    Supports priority queues and dead-letter exchanges.
    """
    
    EXCHANGES = {
        "webhook": "webhook.exchange",
        "auth": "auth.exchange",
        "notification": "notification.exchange",
        "sync": "sync.exchange",
    }
    
    QUEUES = {
        "webhook_github": "webhook.github",
        "webhook_gitlab": "webhook.gitlab",
        "auth_verify": "auth.verify",
        "auth_session": "auth.session",
        "notification_email": "notification.email",
        "notification_slack": "notification.slack",
        "sync_scheduled": "sync.scheduled",
        "sync_manual": "sync.manual",
    }
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5672,
        username: str = "confuse",
        password: str = "confuse_dev_pass",
        virtual_host: str = "/",
    ):
        self.host = host
        self.port = port
        
        self._credentials = pika.PlainCredentials(username, password)
        self._connection_params = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=virtual_host,
            credentials=self._credentials,
            heartbeat=60,
            blocked_connection_timeout=300,
        )
        
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[BlockingChannel] = None
        
    def connect(self):
        """Establish connection to RabbitMQ"""
        if self._connection is None or self._connection.is_closed:
            self._connection = pika.BlockingConnection(self._connection_params)
            self._channel = self._connection.channel()
            self._channel.confirm_delivery()
            logger.info(f"Connected to RabbitMQ: {self.host}:{self.port}")
    
    def _ensure_connected(self):
        """Ensure connection is active"""
        if self._connection is None or self._connection.is_closed:
            self.connect()
    
    def publish_webhook(self, event: WebhookEvent) -> bool:
        """
        Publish webhook event to appropriate queue.
        Uses priority queues for urgent events.
        """
        self._ensure_connected()
        
        try:
            routing_key = f"{event.source}.{event.event_type}"
            
            properties = pika.BasicProperties(
                delivery_mode=2,  # Persistent
                priority=event.priority,
                message_id=event.event_id,
                content_type="application/json",
            )
            
            self._channel.basic_publish(
                exchange=self.EXCHANGES["webhook"],
                routing_key=routing_key,
                body=event.to_json().encode("utf-8"),
                properties=properties,
            )
            
            logger.info(f"Published webhook: {routing_key} (priority={event.priority})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish webhook: {e}")
            return False
    
    def publish_sync_job(self, event: SyncJobEvent) -> bool:
        """Publish sync job to queue"""
        self._ensure_connected()
        
        try:
            routing_key = event.job_type  # "scheduled" or "manual"
            
            properties = pika.BasicProperties(
                delivery_mode=2,
                priority=event.priority,
                message_id=event.job_id,
                content_type="application/json",
            )
            
            self._channel.basic_publish(
                exchange=self.EXCHANGES["sync"],
                routing_key=routing_key,
                body=event.to_json().encode("utf-8"),
                properties=properties,
            )
            
            logger.info(f"Published sync job: {event.job_id} ({event.job_type})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish sync job: {e}")
            return False
    
    def consume_queue(
        self,
        queue_name: str,
        handler: Callable[[Dict[str, Any]], bool],
        prefetch_count: int = 10,
    ):
        """
        Consume messages from a queue.
        
        Args:
            queue_name: Name of the queue to consume
            handler: Function that processes messages, returns True on success
            prefetch_count: Number of unacknowledged messages to prefetch
        """
        self._ensure_connected()
        
        self._channel.basic_qos(prefetch_count=prefetch_count)
        
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body.decode("utf-8"))
                success = handler(message)
                
                if success:
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                else:
                    # Requeue for retry
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Send to DLQ by not requeuing
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        self._channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
        )
        
        logger.info(f"Starting to consume from: {queue_name}")
        self._channel.start_consuming()
    
    def rpc_call(
        self,
        exchange: str,
        routing_key: str,
        message: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Synchronous RPC call using RabbitMQ.
        Creates a temporary reply queue for the response.
        """
        self._ensure_connected()
        
        # Create exclusive reply queue
        result = self._channel.queue_declare(queue="", exclusive=True)
        callback_queue = result.method.queue
        
        correlation_id = str(uuid.uuid4())
        response = None
        
        def on_response(ch, method, props, body):
            nonlocal response
            if props.correlation_id == correlation_id:
                response = json.loads(body.decode("utf-8"))
        
        self._channel.basic_consume(
            queue=callback_queue,
            on_message_callback=on_response,
            auto_ack=True,
        )
        
        properties = pika.BasicProperties(
            reply_to=callback_queue,
            correlation_id=correlation_id,
            content_type="application/json",
        )
        
        self._channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(message).encode("utf-8"),
            properties=properties,
        )
        
        # Wait for response with timeout
        self._connection.process_data_events(timeout)
        
        return response
    
    def close(self):
        """Close connection gracefully"""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("RabbitMQ connection closed")
