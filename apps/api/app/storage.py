"""S3-compatible object storage.

Presigning is a local signature computation with no network call, so it is
safe to do inline in a request handler. Two clients exist because SigV4 signs
the host: the API reaches MinIO at ``minio:9000`` inside the compose network,
but the browser must PUT to an address it can resolve.
"""

import contextlib
import uuid
from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import get_settings

if TYPE_CHECKING:
    # boto3-stubs is a dev dependency. Importing it at runtime works in
    # development and fails in the production image, which installs no dev
    # group, so this annotation has to stay a string.
    from mypy_boto3_s3 import S3Client


def _client(endpoint_url: str) -> "S3Client":
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        # MinIO and R2 want SigV4 and path-style URLs; boto3 falls back to
        # SigV2 for unknown endpoints unless told otherwise.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@lru_cache
def internal_client() -> "S3Client":
    return _client(get_settings().s3_endpoint_url)


@lru_cache
def public_client() -> "S3Client":
    return _client(get_settings().s3_public_endpoint_url)


def build_storage_key(workspace_id: uuid.UUID, matter_id: uuid.UUID, document_id: uuid.UUID) -> str:
    """Object keys are prefixed by tenant so bucket listings shard by workspace."""
    return f"workspaces/{workspace_id}/matters/{matter_id}/documents/{document_id}"


def presign_upload(storage_key: str, mime_type: str) -> str:
    settings = get_settings()
    return public_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": storage_key,
            "ContentType": mime_type,
        },
        ExpiresIn=settings.presign_expiry_seconds,
    )


def presign_download(storage_key: str, filename: str) -> str:
    settings = get_settings()
    safe_name = filename.replace('"', "")
    return public_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": storage_key,
            "ResponseContentDisposition": f'inline; filename="{safe_name}"',
        },
        ExpiresIn=settings.presign_expiry_seconds,
    )


def delete_object(storage_key: str) -> None:
    """Best-effort removal. Used to clean up after a registration that lost a race."""
    settings = get_settings()
    with contextlib.suppress(ClientError):
        internal_client().delete_object(Bucket=settings.s3_bucket, Key=storage_key)


def object_exists(storage_key: str) -> bool:
    """HEAD the object. Used at registration to prove the upload happened."""
    settings = get_settings()
    try:
        internal_client().head_object(Bucket=settings.s3_bucket, Key=storage_key)
    except ClientError:
        return False
    return True
