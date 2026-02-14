"""
媒体处理服务

提供全面的媒体文件处理功能，包括：
1. 图像处理：压缩、格式转换、尺寸调整
2. 缩略图生成：多种尺寸的缩略图
3. 元数据提取：文件信息、EXIF数据
4. 响应式图片：WebP格式、srcset支持
5. 媒体优化：自动压缩、质量控制
"""

import os
import hashlib
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageOps, ExifTags, ImageDraw, ImageFont
from PIL.ExifTags import TAGS
import mimetypes
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from ..crud import setting as crud_setting


class MediaProcessor:
    """媒体处理服务类"""
    
    def __init__(self, db: Session):
        self.db = db
        self.load_settings()
        
        # 预定义的缩略图尺寸
        self.thumbnail_sizes = {
            'thumbnail': (150, 150),    # 缩略图
            'small': (300, 300),        # 小图
            'medium': (600, 600),       # 中图
            'large': (1200, 1200),      # 大图
            'cover': (1920, 1080),      # 封面图
        }
        
        # 支持的文件格式将从数据库配置加载
        self.supported_image_formats = set()
        self.supported_video_formats = set()
        self.supported_audio_formats = set()
        self.supported_document_formats = set()
        
        # 加载支持的文件格式
        self.load_supported_formats()
    
    def load_settings(self):
        """从数据库加载媒体处理设置"""
        # 图像处理设置
        self.image_quality = self._get_setting_int("media_image_quality", 85)
        self.max_image_size = self._get_setting_int("media_max_image_size", 2048)
        self.enable_webp = self._get_setting_bool("media_enable_webp", True)
        self.auto_compress = self._get_setting_bool("media_auto_compress", True)
        
        # 缩略图设置
        self._should_generate_thumbnails = self._get_setting_bool("media_generate_thumbnails", True) # 重命名属性
        self.thumbnail_quality = self._get_setting_int("media_thumbnail_quality", 80)
        
        # 上传设置
        self.upload_path = self._get_setting_str("media_upload_path", "media_uploads/")
        self.max_file_size = self._get_setting_int("media_max_file_size", 50 * 1024 * 1024)  # 50MB
        
        # 安全设置
        self.extract_exif = self._get_setting_bool("media_extract_exif", True)
        self.remove_exif = self._get_setting_bool("media_remove_exif", False)

        # 高级与输出设置
        self.enable_watermark = self._get_setting_bool("media_enable_watermark", False)
        self.watermark_text = self._get_setting_str("media_watermark_text", "")
        self.watermark_opacity = self._get_setting_float("media_watermark_opacity", 0.5)
        self.enable_responsive = self._get_setting_bool("media_enable_responsive", True)
        self.progressive_jpeg = self._get_setting_bool("media_progressive_jpeg", True)
        
        # 重新加载支持的文件格式（在设置加载后）
        self.load_supported_formats()
    
    def _get_setting_bool(self, key: str, default: bool) -> bool:
        """获取布尔类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return bool(setting.value["value"])
        return default
    
    def _get_setting_int(self, key: str, default: int) -> int:
        """获取整数类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return int(setting.value["value"])
        return default

    def _get_setting_float(self, key: str, default: float) -> float:
        """获取浮点类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return float(setting.value["value"])
        return default
    
    def _get_setting_str(self, key: str, default: str) -> str:
        """获取字符串类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return str(setting.value["value"])
        return default
    
    def load_supported_formats(self):
        """从数据库加载支持的文件格式"""
        # 图像格式
        image_formats_str = self._get_setting_str("media_allowed_image_formats", 
                                                  "jpg,jpeg,png,gif,bmp,webp,tiff")
        self.supported_image_formats = set([f'.{fmt.strip().lower()}' for fmt in image_formats_str.split(',') if fmt.strip()])
        
        # 视频格式
        video_formats_str = self._get_setting_str("media_allowed_video_formats", 
                                                  "mp4,avi,mov,wmv,flv,webm,mkv")
        self.supported_video_formats = set([f'.{fmt.strip().lower()}' for fmt in video_formats_str.split(',') if fmt.strip()])
        
        # 音频格式
        audio_formats_str = self._get_setting_str("media_allowed_audio_formats", 
                                                  "mp3,wav,flac,aac,ogg,m4a")
        self.supported_audio_formats = set([f'.{fmt.strip().lower()}' for fmt in audio_formats_str.split(',') if fmt.strip()])
        
        # 文档格式
        document_formats_str = self._get_setting_str("media_allowed_document_formats", 
                                                     "pdf,doc,docx,txt,md")
        self.supported_document_formats = set([f'.{fmt.strip().lower()}' for fmt in document_formats_str.split(',') if fmt.strip()])
    
    def get_file_info(self, file_path: str) -> Dict:
        """
        获取文件基本信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件信息字典
        """
        if not os.path.exists(file_path):
            return {}
        
        stat = os.stat(file_path)
        file_ext = Path(file_path).suffix.lower()
        mime_type, _ = mimetypes.guess_type(file_path)
        
        info = {
            'filename': Path(file_path).name,
            'size': stat.st_size,
            'extension': file_ext,
            'mime_type': mime_type,
            'created_at': datetime.fromtimestamp(stat.st_ctime),
            'modified_at': datetime.fromtimestamp(stat.st_mtime),
            'file_type': self._determine_file_type(file_ext, mime_type)
        }
        
        # 生成文件哈希
        info['md5_hash'] = self._calculate_file_hash(file_path)
        
        return info
    
    def _determine_file_type(self, extension: str, mime_type: str) -> str:
        """确定文件类型"""
        if extension in self.supported_image_formats:
            return 'image'
        elif extension in self.supported_video_formats:
            return 'video'
        elif extension in self.supported_audio_formats:
            return 'audio'
        elif extension in self.supported_document_formats:
            return 'document'
        elif mime_type and (mime_type.startswith('text/') or mime_type.startswith('application/')):
            return 'document'
        else:
            return 'other'
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件MD5哈希"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def extract_image_metadata(self, image_path: str) -> Dict:
        """
        提取图像元数据
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            图像元数据字典
        """
        metadata = {}
        
        try:
            with Image.open(image_path) as img:
                # 基本信息
                metadata.update({
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'has_transparency': img.mode in ('RGBA', 'LA') or 'transparency' in img.info
                })
                
                # EXIF数据
                if self.extract_exif and hasattr(img, '_getexif'):
                    exif_data = img._getexif()
                    if exif_data:
                        exif_metadata = {}
                        for tag_id, value in exif_data.items():
                            tag = TAGS.get(tag_id, tag_id)
                            if isinstance(value, (str, int, float)):
                                exif_metadata[tag] = value
                        metadata['exif'] = exif_metadata
                
        except Exception as e:
            metadata['error'] = str(e)
        
        return metadata
    
    def process_image(self, input_path: str, output_path: str, 
                     max_size: Optional[Tuple[int, int]] = None,
                     quality: Optional[int] = None,
                     format: Optional[str] = None,
                     remove_exif: bool = None) -> Dict:
        """
        处理图像：调整尺寸、压缩、格式转换
        
        Args:
            input_path: 输入图像路径
            output_path: 输出图像路径
            max_size: 最大尺寸 (width, height)
            quality: 压缩质量 (1-100)
            format: 输出格式
            remove_exif: 是否移除EXIF数据
            
        Returns:
            处理结果信息
        """
        if quality is None:
            quality = self.image_quality
        if remove_exif is None:
            remove_exif = self.remove_exif
        if max_size is None:
            max_size = (self.max_image_size, self.max_image_size)
        
        try:
            with Image.open(input_path) as img:
                original_size = img.size
                processed_img = img.copy()
                
                # 自动旋转（根据EXIF信息）
                processed_img = ImageOps.exif_transpose(processed_img)
                
                # 调整尺寸
                if max_size and (img.width > max_size[0] or img.height > max_size[1]):
                    processed_img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # 处理透明度
                if format and format.upper() == 'JPEG' and processed_img.mode in ('RGBA', 'LA'):
                    # JPEG不支持透明度，转换为白色背景
                    background = Image.new('RGB', processed_img.size, (255, 255, 255))
                    if processed_img.mode == 'RGBA':
                        background.paste(processed_img, mask=processed_img.split()[-1])
                    else:
                        background.paste(processed_img)
                    processed_img = background

                # 应用文本水印（仅在配置启用且有文字时）
                processed_img = self._apply_text_watermark(processed_img)
                
                # 确保输出目录存在
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # 保存处理后的图像
                save_kwargs = {'quality': quality, 'optimize': True}
                if remove_exif:
                    save_kwargs['exif'] = b''

                effective_format = (format or Path(output_path).suffix.lstrip(".")).upper()
                if effective_format in ("JPG", "JPEG") and self.progressive_jpeg:
                    save_kwargs['progressive'] = True
                
                if format:
                    save_kwargs['format'] = format
                
                processed_img.save(output_path, **save_kwargs)
                
                return {
                    'success': True,
                    'original_size': original_size,
                    'new_size': processed_img.size,
                    'output_path': output_path,
                    'file_size': os.path.getsize(output_path),
                    'compression_ratio': round(os.path.getsize(output_path) / os.path.getsize(input_path), 2)
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_thumbnails(self, input_path: str, base_output_dir: str) -> Dict[str, str]:
        """
        生成多种尺寸的缩略图
        
        Args:
            input_path: 原始图像路径
            base_output_dir: 缩略图输出目录
            
        Returns:
            缩略图路径字典 {size_name: file_path}
        """
        if not self._should_generate_thumbnails: # 使用重命名后的属性
            return {}
        
        thumbnails = {}
        file_stem = Path(input_path).stem
        
        for size_name, dimensions in self.thumbnail_sizes.items():
            try:
                output_filename = f"{file_stem}_{size_name}.jpg"
                output_path = os.path.join(base_output_dir, output_filename)
                
                result = self.process_image(
                    input_path, 
                    output_path,
                    max_size=dimensions,
                    quality=self.thumbnail_quality,
                    format='JPEG'
                )
                
                if result['success']:
                    thumbnails[size_name] = output_path
                    
            except Exception as e:
                print(f"生成缩略图失败 {size_name}: {e}")
        
        return thumbnails

    def _apply_text_watermark(self, image: Image.Image) -> Image.Image:
        """按当前配置给图像叠加文字水印。"""
        if not self.enable_watermark or not self.watermark_text:
            return image

        opacity = max(0.0, min(1.0, self.watermark_opacity))
        if opacity <= 0:
            return image

        try:
            original_mode = image.mode
            base = image.convert("RGBA")
            overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            font = ImageFont.load_default()

            text = self.watermark_text.strip()
            if not text:
                return image

            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = max(1, text_bbox[2] - text_bbox[0])
            text_height = max(1, text_bbox[3] - text_bbox[1])

            margin = max(12, int(min(base.width, base.height) * 0.02))
            x = max(margin, base.width - text_width - margin)
            y = max(margin, base.height - text_height - margin)

            alpha = int(255 * opacity)
            draw.text((x, y), text, fill=(255, 255, 255, alpha), font=font)
            composited = Image.alpha_composite(base, overlay)
            if original_mode in ("RGB", "L"):
                return composited.convert(original_mode)
            return composited
        except Exception:
            return image
    
    def generate_webp_version(self, input_path: str, output_dir: str) -> Optional[str]:
        """
        生成WebP格式版本
        
        Args:
            input_path: 原始图像路径
            output_dir: 输出目录
            
        Returns:
            WebP文件路径或None
        """
        if not self.enable_webp:
            return None
        
        try:
            file_stem = Path(input_path).stem
            webp_path = os.path.join(output_dir, f"{file_stem}.webp")
            
            result = self.process_image(
                input_path,
                webp_path,
                quality=self.image_quality,
                format='WebP'
            )
            
            return webp_path if result['success'] else None
            
        except Exception as e:
            print(f"生成WebP版本失败: {e}")
            return None
    
    def generate_responsive_images(self, input_path: str, output_dir: str) -> Dict:
        """
        生成响应式图像集合
        
        Args:
            input_path: 原始图像路径
            output_dir: 输出目录
            
        Returns:
            响应式图像信息
        """
        responsive_info = {
            'original': input_path,
            'thumbnails': {},
            'webp_versions': {},
            'srcset': [],
            'srcset_webp': []
        }

        if not self.enable_responsive:
            return responsive_info
        
        # 生成缩略图
        thumbnails = self.generate_thumbnails(input_path, output_dir)
        responsive_info['thumbnails'] = thumbnails
        
        # 为每个尺寸生成WebP版本
        if self.enable_webp:
            for size_name, thumb_path in thumbnails.items():
                webp_path = self.generate_webp_version(thumb_path, output_dir)
                if webp_path:
                    responsive_info['webp_versions'][size_name] = webp_path
        
        # 生成srcset信息 (JPEG/PNG)
        srcset_items = []
        for size_name, thumb_path in thumbnails.items():
            width = self.thumbnail_sizes[size_name][0]
            relative_path = os.path.relpath(thumb_path, self.upload_path)
            srcset_items.append(f"/media/{relative_path} {width}w")
        
        responsive_info['srcset'] = srcset_items
        
        # 生成srcset信息 (WebP)
        if self.enable_webp and responsive_info['webp_versions']:
            srcset_webp_items = []
            for size_name, webp_path in responsive_info['webp_versions'].items():
                width = self.thumbnail_sizes[size_name][0]
                relative_path = os.path.relpath(webp_path, self.upload_path)
                srcset_webp_items.append(f"/media/{relative_path} {width}w")
            responsive_info['srcset_webp'] = srcset_webp_items
        
        return responsive_info
    
    def get_responsive_image_html(self, image_url: str, alt_text: str = "", 
                                 css_classes: str = "", sizes: str = "") -> str:
        """
        生成响应式图像 HTML 代码
        
        Args:
            image_url: 图像 URL
            alt_text: 替代文本
            css_classes: CSS 类名
            sizes: sizes 属性值
            
        Returns:
            HTML 字符串
        """
        if not image_url:
            return ""

        if not self.enable_responsive:
            return f'<img src="{image_url}" alt="{alt_text}" class="{css_classes}" loading="lazy">'
        
        # 对于直接 URL 没有生成的缩略图，返回简单的 img 标签
        if not image_url.startswith('/media/'):
            return f'<img src="{image_url}" alt="{alt_text}" class="{css_classes}" loading="lazy">'
        
        # 尝试查找对应的缩略图文件
        try:
            import re
            # 从 URL中提取文件名
            url_match = re.search(r'/media/(.+)', image_url)
            if url_match:
                media_path = url_match.group(1)
                file_stem = Path(media_path).stem
                media_dir = os.path.dirname(os.path.join(self.upload_path, media_path))
                
                # 检查是否存在缩略图
                has_thumbnails = False
                srcset_items = []
                srcset_webp_items = []
                
                for size_name, dimensions in self.thumbnail_sizes.items():
                    thumb_filename = f"{file_stem}_{size_name}.jpg"
                    thumb_path = os.path.join(media_dir, thumb_filename)
                    
                    if os.path.exists(thumb_path):
                        has_thumbnails = True
                        width = dimensions[0]
                        relative_thumb = os.path.relpath(thumb_path, self.upload_path)
                        srcset_items.append(f"/media/{relative_thumb.replace(os.sep, '/')} {width}w")
                        
                        # 检查 WebP 版本
                        if self.enable_webp:
                            webp_filename = f"{file_stem}_{size_name}.webp"
                            webp_path = os.path.join(media_dir, webp_filename)
                            if os.path.exists(webp_path):
                                relative_webp = os.path.relpath(webp_path, self.upload_path)
                                srcset_webp_items.append(f"/media/{relative_webp.replace(os.sep, '/')} {width}w")
                
                # 如果有缩略图，生成响应式 HTML
                if has_thumbnails:
                    if not sizes:
                        sizes = "(max-width: 480px) 400px, (max-width: 768px) 800px, (max-width: 1200px) 1200px, 1920px"
                    
                    html = ""
                    
                    # 如果有 WebP 版本，使用 picture 元素
                    if srcset_webp_items:
                        html += '<picture>\n'
                        html += f'  <source type="image/webp" srcset="{", ".join(srcset_webp_items)}" sizes="{sizes}">\n'
                        html += f'  <img src="{image_url}" srcset="{", ".join(srcset_items)}" sizes="{sizes}" alt="{alt_text}" class="{css_classes}" loading="lazy">\n'
                        html += '</picture>'
                    else:
                        # 只有传统格式
                        html = f'<img src="{image_url}" srcset="{", ".join(srcset_items)}" sizes="{sizes}" alt="{alt_text}" class="{css_classes}" loading="lazy">'
                    
                    return html
        
        except Exception as e:
            print(f"生成响应式图像 HTML 失败: {e}")
        
        # 如果没有缩略图或出错，返回简单的 img 标签
        return f'<img src="{image_url}" alt="{alt_text}" class="{css_classes}" loading="lazy">'
    
    def validate_upload_file(self, filename: str, file_size: int, mime_type: str) -> Tuple[bool, str]:
        """
        验证上传文件
        
        Args:
            filename: 文件名
            file_size: 文件大小
            mime_type: MIME类型
            
        Returns:
            (是否有效, 错误信息)
        """
        # 检查文件大小
        if file_size > self.max_file_size:
            max_size_mb = self.max_file_size / (1024 * 1024)
            return False, f"文件大小超过限制（最大 {max_size_mb:.1f}MB）"
        
        # 检查文件扩展名
        file_ext = Path(filename).suffix.lower()
        all_supported = (self.supported_image_formats | 
                        self.supported_video_formats | 
                        self.supported_audio_formats |
                        self.supported_document_formats)
        
        if file_ext not in all_supported:
            return False, f"不支持的文件格式：{file_ext}"
        
        # 检查MIME类型
        if mime_type and not self._is_safe_mime_type(mime_type):
            return False, f"不安全的文件类型：{mime_type}"
        
        return True, ""
    
    def _is_safe_mime_type(self, mime_type: str) -> bool:
        """检查MIME类型是否安全"""
        safe_types = [
            'image/', 'video/', 'audio/',
            'application/pdf', 'text/',
            'application/msword',
            'application/vnd.openxmlformats-officedocument'
        ]
        return any(mime_type.startswith(safe_type) for safe_type in safe_types)
    
    def optimize_image(self, input_path: str, output_path: str = None) -> Dict:
        """
        优化图像文件（就地优化或输出到新路径）
        
        Args:
            input_path: 输入图像路径
            output_path: 输出路径（可选，默认覆盖原文件）
            
        Returns:
            优化结果信息
        """
        if output_path is None:
            output_path = input_path
        
        return self.process_image(
            input_path, 
            output_path,
            max_size=(self.max_image_size, self.max_image_size),
            quality=self.image_quality
        )


# 全局媒体处理器实例（延迟初始化）
_media_processor: Optional[MediaProcessor] = None

def get_media_processor(db: Session) -> MediaProcessor:
    """获取媒体处理器实例"""
    global _media_processor
    if _media_processor is None:
        _media_processor = MediaProcessor(db)
    else:
        _media_processor.db = db
        _media_processor.load_settings()
    return _media_processor
