"""
Image Utilities for MapToPoster
Handles preview generation, WebP conversion, and R2 upload
"""

import os
from pathlib import Path
from PIL import Image
import io
import hashlib

# Preview settings
PREVIEW_MAX_WIDTH = 1600  # Max width for web preview
PREVIEW_QUALITY = 85  # WebP quality (0-100)
THUMB_WIDTH = 400  # Thumbnail for gallery


def generate_preview_from_png(png_path: str, output_dir: Path) -> dict:
    """
    Generate optimized WebP preview and thumbnail from a full-res PNG.
    
    Returns dict with paths to generated files:
    {
        'preview': '/path/to/preview.webp',
        'thumb': '/path/to/thumb.webp',
        'blur_hash': 'base64_blur_placeholder'
    }
    """
    png_path = Path(png_path)
    if not png_path.exists():
        raise FileNotFoundError(f"PNG not found: {png_path}")
    
    # Generate unique name based on original
    base_name = png_path.stem
    
    # Open original image
    with Image.open(png_path) as img:
        original_width, original_height = img.size
        
        # Generate preview (max 1600px wide, WebP)
        preview_path = output_dir / f"{base_name}_preview.webp"
        preview_img = resize_image(img, PREVIEW_MAX_WIDTH)
        preview_img.save(preview_path, 'WEBP', quality=PREVIEW_QUALITY, method=6)
        
        # Generate thumbnail (400px wide, WebP)
        thumb_path = output_dir / f"{base_name}_thumb.webp"
        thumb_img = resize_image(img, THUMB_WIDTH)
        thumb_img.save(thumb_path, 'WEBP', quality=80, method=6)
        
        # Generate tiny blur placeholder (20px, base64)
        blur_placeholder = generate_blur_placeholder(img)
    
    return {
        'preview': str(preview_path),
        'thumb': str(thumb_path),
        'blur_placeholder': blur_placeholder,
        'original_width': original_width,
        'original_height': original_height,
    }


def resize_image(img: Image.Image, max_width: int) -> Image.Image:
    """Resize image maintaining aspect ratio."""
    width, height = img.size
    if width <= max_width:
        return img.copy()
    
    ratio = max_width / width
    new_height = int(height * ratio)
    return img.resize((max_width, new_height), Image.Resampling.LANCZOS)


def generate_blur_placeholder(img: Image.Image, size: int = 20) -> str:
    """Generate a tiny base64 blur placeholder for LQIP."""
    import base64
    
    # Resize to tiny
    ratio = size / max(img.size)
    tiny_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
    tiny = img.resize(tiny_size, Image.Resampling.LANCZOS)
    
    # Convert to WebP bytes
    buffer = io.BytesIO()
    tiny.save(buffer, 'WEBP', quality=20)
    buffer.seek(0)
    
    # Encode as base64
    return base64.b64encode(buffer.read()).decode('utf-8')


def convert_png_to_webp(png_path: str, quality: int = 85) -> str:
    """Convert a PNG to WebP, return new path."""
    png_path = Path(png_path)
    webp_path = png_path.with_suffix('.webp')
    
    with Image.open(png_path) as img:
        img.save(webp_path, 'WEBP', quality=quality, method=6)
    
    return str(webp_path)


def get_image_dimensions(path: str) -> tuple:
    """Get image dimensions without loading full image."""
    with Image.open(path) as img:
        return img.size


# Cloudflare R2 upload functions (to be configured)
class R2Storage:
    """Cloudflare R2 storage handler."""
    
    def __init__(self, account_id: str = None, access_key: str = None, secret_key: str = None, bucket: str = None):
        self.account_id = account_id or os.environ.get('R2_ACCOUNT_ID')
        self.access_key = access_key or os.environ.get('R2_ACCESS_KEY')
        self.secret_key = secret_key or os.environ.get('R2_SECRET_KEY')
        self.bucket = bucket or os.environ.get('R2_BUCKET', 'maptoposter')
        self.endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com" if self.account_id else None
        self._client = None
    
    @property
    def is_configured(self) -> bool:
        return all([self.account_id, self.access_key, self.secret_key])
    
    @property
    def client(self):
        if not self._client and self.is_configured:
            import boto3
            self._client = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name='auto'
            )
        return self._client
    
    def upload_file(self, local_path: str, remote_key: str, content_type: str = None) -> str:
        """Upload file to R2, return public URL."""
        if not self.is_configured:
            print("R2 not configured, skipping upload")
            return None
        
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        self.client.upload_file(local_path, self.bucket, remote_key, ExtraArgs=extra_args)
        
        # Return public URL (requires public bucket or custom domain)
        return f"https://{self.bucket}.{self.account_id}.r2.dev/{remote_key}"
    
    def upload_poster(self, png_path: str, preview_path: str, thumb_path: str, poster_id: str) -> dict:
        """Upload all poster variants to R2."""
        if not self.is_configured:
            return None
        
        urls = {}
        
        # Upload full-res PNG
        urls['print'] = self.upload_file(
            png_path, 
            f"print/{poster_id}.png",
            'image/png'
        )
        
        # Upload preview WebP
        urls['preview'] = self.upload_file(
            preview_path,
            f"preview/{poster_id}.webp", 
            'image/webp'
        )
        
        # Upload thumbnail WebP
        urls['thumb'] = self.upload_file(
            thumb_path,
            f"thumb/{poster_id}.webp",
            'image/webp'
        )
        
        return urls


# Global R2 instance (configured via env vars)
r2_storage = R2Storage()
