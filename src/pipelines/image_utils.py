import os
import gc
import io
import logging
from typing import Tuple, Optional, Union
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Configurable settings
MAX_UPLOAD_SIZE_MB = 25  # Configurable maximum file size limit in MB
MAX_IMAGE_DIMENSION = 2048  # Target max dimension for classroom group photos
MAX_TOTAL_PIXELS = 100_000_000  # 100 megapixels decompression bomb limit
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png')
SUPPORTED_FORMATS = ('JPEG', 'PNG')

# Prevent decompression bomb attacks/errors while safely allowing high-res photos
Image.MAX_IMAGE_PIXELS = MAX_TOTAL_PIXELS


def validate_image_file(
    file_source: Union[io.BytesIO, bytes, str],
    filename: str = "",
    max_size_mb: float = MAX_UPLOAD_SIZE_MB
) -> Tuple[bool, Optional[str]]:
    """
    Validates an image file before deep processing:
    - Verifies file size is within acceptable limits.
    - Validates file format and headers.
    - Verifies image integrity against corruption.
    - Handles incorrect extensions.
    Returns: (is_valid: bool, error_message: Optional[str])
    """
    try:
        # 1. Check file size
        if isinstance(file_source, bytes):
            size_bytes = len(file_source)
            bio = io.BytesIO(file_source)
        elif hasattr(file_source, 'size'):
            size_bytes = file_source.size
            file_source.seek(0)
            bio = io.BytesIO(file_source.read())
            file_source.seek(0)
        elif hasattr(file_source, 'getbuffer'):
            size_bytes = len(file_source.getbuffer())
            file_source.seek(0)
            bio = io.BytesIO(file_source.read())
            file_source.seek(0)
        else:
            file_source.seek(0)
            data = file_source.read()
            size_bytes = len(data)
            bio = io.BytesIO(data)

        size_mb = size_bytes / (1024 * 1024)
        if size_mb > max_size_mb:
            return False, f"File size ({size_mb:.1f} MB) exceeds maximum allowed limit ({max_size_mb} MB)."

        if size_bytes < 10:
            return False, "File is empty or too small to be a valid image."

        # 2. Check filename extension if provided
        if filename:
            ext = os.path.splitext(filename.lower())[1]
            if ext not in SUPPORTED_EXTENSIONS:
                return False, f"Unsupported file extension '{ext}'. Please upload JPG, JPEG, or PNG."

        # 3. Verify image with Pillow
        bio.seek(0)
        try:
            with Image.open(bio) as img:
                img_format = img.format
                if img_format not in SUPPORTED_FORMATS:
                    return False, f"Unsupported image format: {img_format}. Only JPEG and PNG are supported."
                img.verify()  # Verifies file integrity
        except Exception as e:
            return False, f"Corrupted or invalid image file: {str(e)}"

        return True, None

    except Exception as e:
        return False, f"Failed to validate image: {str(e)}"


def process_and_optimize_image(
    file_source: Union[io.BytesIO, bytes, Image.Image],
    max_dimension: int = MAX_IMAGE_DIMENSION
) -> Tuple[Optional[Image.Image], Optional[str]]:
    """
    Safely decodes, auto-orients, and optimizes high-resolution classroom images:
    - Auto-transposes according to EXIF orientation metadata.
    - Converts cleanly to RGB format (handles RGBA, grayscale, CMYK, etc.).
    - Scales down images larger than max_dimension while preserving aspect ratio.
    - Maintains high enough resolution for distant faces without triggering OOM.
    - Cleans up memory.
    Returns: (optimized_image: Optional[PIL.Image.Image], error_message: Optional[str])
    """
    try:
        # Open image if not already a PIL Image
        if isinstance(file_source, Image.Image):
            raw_img = file_source.copy()
        else:
            if isinstance(file_source, bytes):
                bio = io.BytesIO(file_source)
            elif hasattr(file_source, 'seek'):
                file_source.seek(0)
                bio = io.BytesIO(file_source.read())
                file_source.seek(0)
            else:
                bio = file_source
            bio.seek(0)
            raw_img = Image.open(bio)

        # 1. Handle EXIF orientation (e.g. photos taken vertically with phone cameras)
        try:
            transposed_img = ImageOps.exif_transpose(raw_img)
            if transposed_img is not None:
                raw_img = transposed_img
        except Exception as e:
            logger.debug(f"EXIF transpose skipped or failed: {e}")

        # 2. Convert to RGB format
        if raw_img.mode != "RGB":
            rgb_img = raw_img.convert("RGB")
            raw_img.close()
            raw_img = rgb_img

        # 3. Resize if largest dimension exceeds max_dimension
        w, h = raw_img.size
        max_dim = max(w, h)

        if max_dim > max_dimension:
            scale = max_dimension / float(max_dim)
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            # Resampling with Lanczos preserves crisp features on distant faces
            resized_img = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            raw_img.close()
            raw_img = resized_img

        return raw_img, None

    except Exception as e:
        return None, f"Failed to process and optimize image: {str(e)}"
    finally:
        gc.collect()


def safe_cleanup_memory():
    """Forces garbage collection to release temporary numpy arrays and images."""
    gc.collect()
