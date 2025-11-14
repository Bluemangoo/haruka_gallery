from .process_pool import is_main_process
if is_main_process():
    import nonebot

    nonebot.init()

    from .command import *
    from .task import *
