from apscheduler.triggers.interval import IntervalTrigger
from nonebot import require, logger

from .utils import file_cache, FileCache

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

count = file_cache.take_over_files(r'.*_thumb\.webp$', ignore_case=True, timeout=10 * 24 * 3600)
logger.debug(f"接管了 {count} 个缩略图缓存文件")

scheduler.add_job(
    FileCache.prune,
    trigger=IntervalTrigger(hours=1),
    args=[file_cache],
    id="haruka_gallery_file_cache_prune",
    replace_existing=True
)
