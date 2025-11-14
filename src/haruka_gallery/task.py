from apscheduler.triggers.interval import IntervalTrigger
from nonebot import require
from nonebot_plugin_apscheduler import scheduler

from .utils import file_cache, FileCache

require("nonebot_plugin_apscheduler")

scheduler.add_job(
    FileCache.prune,
    trigger=IntervalTrigger(hours=1),
    args=[file_cache],
    id="haruka_gallery_file_cache_prune",
    replace_existing=True
)
