from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel

_cache_dir: Path = Path("cache/haruka_gallery")
_config_dir: Path = Path("config/haruka_gallery")
_data_dir: Path = Path("data/haruka_gallery")

class Config(BaseModel):
    size_limit_mb: int = 10
    thumbnail_size: tuple[int, int] = (64, 64)
    repeat_image_show_size: tuple[int, int] = (128, 128)
    canvas_limit_size: tuple[int, int] = (4096, 4096)

    @property
    def cache_dir(self) -> Path:
        """插件缓存目录"""
        return _cache_dir

    @property
    def config_dir(self) -> Path:
        """插件配置目录"""
        return _config_dir

    @property
    def data_dir(self) -> Path:
        """插件数据目录"""
        return _data_dir

gallery_config: Config = get_plugin_config(Config)
