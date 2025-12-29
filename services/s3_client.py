"""
ConHub Data Connector - S3/MinIO Client

Handles large file uploads to S3-compatible storage.
"""

from typing import Optional
from uuid import UUID, uuid4

import boto3
from botocore.exceptions import ClientError
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class S3Client:
    """Client for S3/MinIO blob storage."""
    
    def __init__(self):
        self._client = None
    
    def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            config = {
                "aws_access_key_id": settings.s3_access_key,
                "aws_secret_access_key": settings.s3_secret_key,
                "region_name": settings.s3_region,
            }
            
            if settings.s3_endpoint_url:
                config["endpoint_url"] = settings.s3_endpoint_url
            
            self._client = boto3.client("s3", **config)
            
        return self._client
    
    async def upload_blob(
        self,
        content: str,
        file_id: str,
        tenant_id: str,
        file_name: Optional[str] = None,
        content_type: str = "text/plain",
    ) -> str:
        """
        Upload content to S3 and return the blob URL.
        
        Args:
            content: File content as string
            file_id: Unique file identifier
            tenant_id: Tenant identifier
            file_name: Optional original filename
            content_type: MIME type
            
        Returns:
            Blob URL (s3://{bucket}/{key} or presigned URL)
        """
        client = self._get_client()
        bucket = settings.s3_bucket_name
        
        # Generate key with tenant isolation
        blob_id = str(uuid4())
        key = f"{tenant_id}/{file_id}/{blob_id}"
        
        if file_name:
            # Append extension if present
            ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
            if ext:
                key = f"{key}.{ext}"
        
        try:
            # Upload content
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
                Metadata={
                    "file_id": file_id,
                    "tenant_id": tenant_id,
                    "file_name": file_name or "",
                },
            )
            
            # Generate presigned URL for download
            presigned_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=3600 * 24 * 7,  # 7 days
            )
            
            logger.info(
                "Uploaded blob to S3",
                bucket=bucket,
                key=key,
                size=len(content),
            )
            
            return presigned_url
            
        except ClientError as e:
            logger.error("S3 upload failed", error=str(e))
            raise
    
    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload raw bytes to S3.
        
        Args:
            data: Raw bytes to upload
            key: S3 object key
            content_type: MIME type
            
        Returns:
            Presigned download URL
        """
        client = self._get_client()
        bucket = settings.s3_bucket_name
        
        try:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            
            presigned_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=3600 * 24 * 7,
            )
            
            return presigned_url
            
        except ClientError as e:
            logger.error("S3 upload failed", key=key, error=str(e))
            raise
    
    async def download_blob(self, key: str) -> bytes:
        """
        Download blob from S3.
        
        Args:
            key: S3 object key
            
        Returns:
            Raw bytes content
        """
        client = self._get_client()
        bucket = settings.s3_bucket_name
        
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            logger.error("S3 download failed", key=key, error=str(e))
            raise
    
    async def delete_blob(self, key: str) -> bool:
        """
        Delete blob from S3.
        
        Args:
            key: S3 object key
            
        Returns:
            True if deleted
        """
        client = self._get_client()
        bucket = settings.s3_bucket_name
        
        try:
            client.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            logger.error("S3 delete failed", key=key, error=str(e))
            return False
    
    def is_configured(self) -> bool:
        """Check if S3 is properly configured."""
        return bool(
            settings.s3_access_key and
            settings.s3_secret_key and
            settings.s3_bucket_name
        )


# Global client instance
_s3_client: Optional[S3Client] = None


def get_s3_client() -> S3Client:
    """Get global S3 client instance."""
    global _s3_client
    if _s3_client is None:
        _s3_client = S3Client()
    return _s3_client
