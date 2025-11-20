from pathlib import Path

import nonebot
from nonebot import get_plugin_config, get_driver, get_bot
from pydantic import BaseModel

_cache_dir: Path = Path("cache/haruka_gallery")
_config_dir: Path = Path("config/haruka_gallery")
_data_dir: Path = Path("data/haruka_gallery")
_bot_name: str = "小遥"


class Config(BaseModel):
    size_limit_mb: int = 10
    thumbnail_size: tuple[int, int] = (64, 64)
    repeat_image_show_size: tuple[int, int] = (128, 128)
    canvas_limit_size: tuple[int, int] = (4096, 4096)
    random_image_limit: int = 10
    enable_whateat: bool = False
    bot_id: int | None = None

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

    @property
    def bot_name(self) -> str:
        """机器人名称"""
        return _bot_name


try:
    gallery_config: Config = get_plugin_config(Config)
    nickname = list(get_driver().config.nickname)
    if nickname:
        _bot_name = nickname[0]
except Exception:
    import sys

    arg_offset = 1 if sys.argv[0].endswith('python.exe') or sys.argv[0].endswith('python3.exe') or sys.argv[0].endswith(
        'python') else 0
    print(f"bot 初始化失败，猜测正在运行脚本，采用 cwd {sys.argv[arg_offset + 1]} 作为根目录")
    _cache_dir = Path(sys.argv[arg_offset + 1]) / "cache" / "haruka_gallery"
    _config_dir = Path(sys.argv[arg_offset + 1]) / "config" / "haruka_gallery"
    _data_dir = Path(sys.argv[arg_offset + 1]) / "data" / "haruka_gallery"
    gallery_config = Config()
