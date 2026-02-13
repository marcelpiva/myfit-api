"""Storage service for file uploads to S3, R2, or local filesystem.

Supports:
- AWS S3
- Cloudflare R2 (S3-compatible)
- Local filesystem (for development)
"""
import hashlib
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Literal

import aiofiles
import aiofiles.os
from botocore.exceptions import BotoCoreError, ClientError

from src.config.settings import settings

logger = logging.getLogger(__name__)

# File size limits
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB
MAX_EXERCISE_MEDIA_SIZE = 50 * 1024 * 1024  # 50MB

# Allowed content types
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
ALLOWED_MEDIA_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES


class StorageError(Exception):
    """Base exception for storage errors."""

    pass


class FileTooLargeError(StorageError):
    """File exceeds maximum allowed size."""

    pass


class InvalidContentTypeError(StorageError):
    """File content type is not allowed."""

    pass


class StorageService:
    """Service for uploading and managing files in cloud storage."""

    def __init__(self):
        self._s3_client = None
        self._initialized = False

    async def _get_s3_client(self):
        """Get or create S3 client (lazy initialization)."""
        if self._s3_client is not None:
            return self._s3_client

        if settings.STORAGE_PROVIDER == "local":
            return None

        try:
            import aioboto3

            session = aioboto3.Session(
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )

            # Build endpoint URL for R2 if configured
            endpoint_url = settings.S3_ENDPOINT_URL or None

            self._s3_client = session.client(
                "s3",
                endpoint_url=endpoint_url,
            )
            self._initialized = True
            return self._s3_client

        except ImportError:
            logger.warning("aioboto3 not installed, using local storage")
            return None

    def _generate_file_path(
        self,
        file_type: Literal["avatars", "exercises", "media"],
        user_id: str | None = None,
        extension: str = "",
    ) -> str:
        """Generate a unique file path for storage."""
        # Create a unique filename
        timestamp = datetime.now().strftime("%Y%m%d")
        unique_id = uuid.uuid4().hex[:12]

        if user_id:
            # Include user ID in path for organization
            return f"{file_type}/{user_id}/{timestamp}_{unique_id}{extension}"
        return f"{file_type}/{timestamp}_{unique_id}{extension}"

    def _get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from content type."""
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "video/webm": ".webm",
        }
        return extensions.get(content_type, "")

    def _validate_file(
        self,
        content_type: str,
        file_size: int,
        allowed_types: set[str],
        max_size: int,
    ) -> None:
        """Validate file type and size."""
        if content_type not in allowed_types:
            raise InvalidContentTypeError(
                f"Content type '{content_type}' not allowed. "
                f"Allowed: {', '.join(allowed_types)}"
            )

        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            raise FileTooLargeError(
                f"File size {file_size / (1024 * 1024):.1f}MB exceeds "
                f"maximum allowed {max_mb:.0f}MB"
            )

    async def _upload_to_local(
        self,
        file_content: bytes,
        path: str,
        content_type: str,
    ) -> str:
        """Upload file to local filesystem (development only)."""
        local_path = Path(settings.LOCAL_STORAGE_PATH) / path

        # Create directories if needed
        await aiofiles.os.makedirs(local_path.parent, exist_ok=True)

        # Write file
        async with aiofiles.open(local_path, "wb") as f:
            await f.write(file_content)

        logger.info(f"Uploaded file to local storage: {path}")

        # Return URL (assuming static file server is configured)
        return f"/uploads/{path}"

    async def _upload_to_s3(
        self,
        file_content: bytes,
        path: str,
        content_type: str,
    ) -> str:
        """Upload file to S3 or R2."""
        client = await self._get_s3_client()
        if client is None:
            # Fallback to local
            return await self._upload_to_local(file_content, path, content_type)

        try:
            async with client as s3:
                await s3.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=path,
                    Body=file_content,
                    ContentType=content_type,
                    # Cache for 1 year (immutable files with unique names)
                    CacheControl="public, max-age=31536000, immutable",
                )

            logger.info(f"Uploaded file to S3: {path}")

            # Return CDN URL if configured, otherwise construct S3 URL
            if settings.CDN_BASE_URL:
                return f"{settings.CDN_BASE_URL.rstrip('/')}/{path}"

            # Direct S3 URL
            if settings.S3_ENDPOINT_URL:
                # R2 URL
                return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET_NAME}/{path}"

            # AWS S3 URL
            return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{path}"

        except (BotoCoreError, ClientError, OSError) as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise StorageError(f"Failed to upload file: {e}") from e

    async def upload_avatar(
        self,
        user_id: str,
        file_content: bytes,
        content_type: str,
    ) -> str:
        """Upload user avatar image.

        Args:
            user_id: UUID of the user
            file_content: Raw file bytes
            content_type: MIME type of the file

        Returns:
            Public URL of the uploaded file

        Raises:
            InvalidContentTypeError: If content type is not an allowed image type
            FileTooLargeError: If file exceeds maximum size
            StorageError: If upload fails
        """
        # Validate
        self._validate_file(
            content_type=content_type,
            file_size=len(file_content),
            allowed_types=ALLOWED_IMAGE_TYPES,
            max_size=MAX_AVATAR_SIZE,
        )

        # Generate path
        extension = self._get_extension_from_content_type(content_type)
        path = self._generate_file_path("avatars", user_id, extension)

        # Upload
        if settings.STORAGE_PROVIDER == "local":
            return await self._upload_to_local(file_content, path, content_type)
        return await self._upload_to_s3(file_content, path, content_type)

    async def upload_exercise_media(
        self,
        file_content: bytes,
        content_type: str,
        user_id: str | None = None,
    ) -> str:
        """Upload exercise media (image or video).

        Args:
            file_content: Raw file bytes
            content_type: MIME type of the file
            user_id: Optional UUID of the user uploading (for custom exercises)

        Returns:
            Public URL of the uploaded file

        Raises:
            InvalidContentTypeError: If content type is not allowed
            FileTooLargeError: If file exceeds maximum size
            StorageError: If upload fails
        """
        # Validate
        self._validate_file(
            content_type=content_type,
            file_size=len(file_content),
            allowed_types=ALLOWED_MEDIA_TYPES,
            max_size=MAX_EXERCISE_MEDIA_SIZE,
        )

        # Generate path
        extension = self._get_extension_from_content_type(content_type)
        path = self._generate_file_path("exercises", user_id, extension)

        # Upload
        if settings.STORAGE_PROVIDER == "local":
            return await self._upload_to_local(file_content, path, content_type)
        return await self._upload_to_s3(file_content, path, content_type)

    async def delete_file(self, url: str) -> bool:
        """Delete a file from storage.

        Args:
            url: Public URL of the file to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        # Extract path from URL
        try:
            if url.startswith("/uploads/"):
                # Local file
                path = url.replace("/uploads/", "")
                local_path = Path(settings.LOCAL_STORAGE_PATH) / path
                if await aiofiles.os.path.exists(local_path):
                    await aiofiles.os.remove(local_path)
                    logger.info(f"Deleted local file: {path}")
                    return True
                return False

            # Extract S3 key from URL
            if settings.CDN_BASE_URL and url.startswith(settings.CDN_BASE_URL):
                path = url.replace(f"{settings.CDN_BASE_URL.rstrip('/')}/", "")
            elif f"{settings.S3_BUCKET_NAME}/" in url:
                path = url.split(f"{settings.S3_BUCKET_NAME}/")[1]
            else:
                logger.warning(f"Could not extract path from URL: {url}")
                return False

            client = await self._get_s3_client()
            if client is None:
                return False

            async with client as s3:
                await s3.delete_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=path,
                )

            logger.info(f"Deleted S3 file: {path}")
            return True

        except (BotoCoreError, ClientError, OSError) as e:
            logger.error(f"Failed to delete file: {e}")
            return False

    async def get_presigned_upload_url(
        self,
        file_type: Literal["avatars", "exercises", "media"],
        content_type: str,
        user_id: str | None = None,
        expires_in: int = 3600,
    ) -> tuple[str, str]:
        """Get a presigned URL for direct client upload.

        This allows clients to upload directly to S3/R2 without going through
        our server, reducing bandwidth and improving performance.

        Args:
            file_type: Type of file being uploaded
            content_type: MIME type of the file
            user_id: Optional user ID for path generation
            expires_in: URL expiration time in seconds

        Returns:
            Tuple of (upload_url, final_url) where upload_url is for uploading
            and final_url is where the file will be accessible after upload
        """
        if settings.STORAGE_PROVIDER == "local":
            raise StorageError("Presigned URLs not available in local storage mode")

        extension = self._get_extension_from_content_type(content_type)
        path = self._generate_file_path(file_type, user_id, extension)

        client = await self._get_s3_client()
        if client is None:
            raise StorageError("S3 client not available")

        try:
            async with client as s3:
                upload_url = await s3.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": settings.S3_BUCKET_NAME,
                        "Key": path,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expires_in,
                )

            # Generate final URL
            if settings.CDN_BASE_URL:
                final_url = f"{settings.CDN_BASE_URL.rstrip('/')}/{path}"
            elif settings.S3_ENDPOINT_URL:
                final_url = f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET_NAME}/{path}"
            else:
                final_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{path}"

            return upload_url, final_url

        except (BotoCoreError, ClientError, OSError) as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise StorageError(f"Failed to generate upload URL: {e}") from e


# Singleton instance
storage_service = StorageService()
