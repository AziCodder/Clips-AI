from __future__ import annotations

import io
import os
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.core.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def presign_url(s3_key: str, ttl: int | None = None) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
        ExpiresIn=ttl or settings.S3_PRESIGNED_TTL,
    )


def upload_file(local_path: str, s3_key: str, content_type: str = "application/octet-stream") -> int:
    client = _client()
    file_size = os.path.getsize(local_path)
    client.upload_file(
        local_path,
        settings.S3_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": content_type},
    )
    return file_size


def upload_fileobj(fileobj: BinaryIO, s3_key: str, content_type: str = "application/octet-stream") -> None:
    client = _client()
    client.upload_fileobj(
        fileobj,
        settings.S3_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": content_type},
    )


def download_file(s3_key: str, local_path: str) -> None:
    client = _client()
    client.download_file(settings.S3_BUCKET, s3_key, local_path)


def download_fileobj(s3_key: str) -> bytes:
    client = _client()
    buf = io.BytesIO()
    client.download_fileobj(settings.S3_BUCKET, s3_key, buf)
    return buf.getvalue()


def object_exists(s3_key: str) -> bool:
    client = _client()
    try:
        client.head_object(Bucket=settings.S3_BUCKET, Key=s3_key)
        return True
    except client.exceptions.ClientError:
        return False


def delete_prefix(prefix: str) -> int:
    """Delete all objects under a prefix. Returns count of deleted objects."""
    client = _client()
    paginator = client.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=settings.S3_BUCKET, Delete={"Objects": objects})
            deleted += len(objects)
    return deleted


def delete_object(s3_key: str) -> None:
    client = _client()
    client.delete_object(Bucket=settings.S3_BUCKET, Key=s3_key)


def verify_transcript_bundle(video_id: str, job_id: str) -> list[str]:
    """Return list of missing required keys for a transcript bundle."""
    required = [
        f"videos/{video_id}/transcripts/{job_id}/transcript.txt",
        f"videos/{video_id}/transcripts/{job_id}/words.json",
        f"videos/{video_id}/transcripts/{job_id}/segments.json",
        f"videos/{video_id}/transcripts/{job_id}/subtitles.srt",
    ]
    return [k for k in required if not object_exists(k)]
