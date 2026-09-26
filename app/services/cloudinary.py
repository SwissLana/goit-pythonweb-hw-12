"""Non-blocking Cloudinary avatar uploads."""

from functools import partial

import cloudinary
import cloudinary.uploader
from anyio import to_thread

from app.core.config import get_settings


class CloudinaryNotConfiguredError(RuntimeError):
    """Raised when avatar upload credentials are absent."""


async def upload_avatar(image: bytes, user_id: int) -> str:
    """Upload an avatar and return its secure delivery URL."""

    settings = get_settings()
    if not all(
        (
            settings.cloudinary_cloud_name,
            settings.cloudinary_api_key,
            settings.cloudinary_api_secret,
        )
    ):
        raise CloudinaryNotConfiguredError("Cloudinary is not configured")

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret.get_secret_value(),
        secure=True,
    )
    upload = partial(
        cloudinary.uploader.upload,
        image,
        resource_type="image",
        folder=settings.cloudinary_folder,
        public_id=f"user-{user_id}",
        overwrite=True,
        invalidate=True,
        unique_filename=False,
        allowed_formats=["jpg", "jpeg", "png", "webp", "gif"],
        transformation=[
            {
                "width": 500,
                "height": 500,
                "crop": "fill",
                "gravity": "face",
            }
        ],
    )
    result = await to_thread.run_sync(upload)
    secure_url = result.get("secure_url")
    if not isinstance(secure_url, str) or not secure_url:
        raise RuntimeError("Cloudinary did not return a secure URL")
    return secure_url
