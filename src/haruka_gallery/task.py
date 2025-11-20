from apscheduler.triggers.interval import IntervalTrigger
from nonebot import require

from .utils import file_cache, FileCache

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

scheduler.add_job(
    FileCache.prune,
    trigger=IntervalTrigger(hours=1),
    args=[file_cache],
    id="haruka_gallery_file_cache_prune",
    replace_existing=True
)
