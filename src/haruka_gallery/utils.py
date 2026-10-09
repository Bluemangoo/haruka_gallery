import asyncio
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters.onebot.v11.bot import Bot

from .config import gallery_config

COMMON_IMAGE_EXTS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/svg+xml": ".svg",
}


class CachedFile:
    url: str
    local_path: str
    used: bool
    created_at: datetime
    extra: dict
    timeout: int

    def __init__(self, url: str, local_path: str, timeout: int = 3600):
        self.url = url
        self.local_path = local_path
        self.used = False
        self.created_at = datetime.now()
        self.extra = {}
        self.timeout = timeout

    def __repr__(self):
        return f"<CachedFile url={self.url} local_path={self.local_path} used={self.used} created_at={self.created_at} extra={self.extra} timeout={self.timeout}>"

    @property
    def path(self):
        return Path(self.local_path)

    def mark_used(self):
        self.used = True

    def renewed(self):
        self.created_at = datetime.now()
        self.used = False
        return self

    def update_extra(self, extra: dict | None):
        if extra:
            self.extra.update(extra)
        return self

    def update_timeout(self, timeout: int):
        self.timeout = timeout
        return self


class FileCache:
    files: dict[str, CachedFile]

    def __init__(self):
        self.files = {}
        if not os.path.exists(gallery_config.cache_dir):
            os.makedirs(gallery_config.cache_dir)

    @staticmethod
    def _extension_from_content_type(ct: str) -> str:
        """Return an extension (including leading dot) for a given content-type."""
        if not ct:
            return ""
        ct = ct.split(";")[0].strip().lower()
        if ct in COMMON_IMAGE_EXTS:
            return COMMON_IMAGE_EXTS[ct]
        ext = mimetypes.guess_extension(ct) or ""
        if ext == ".jpe":
            ext = ".jpg"
        return ext

    def _random_filename(self, ext: str) -> str:
        import uuid
        name = str(uuid.uuid4()) + ext
        while name in self.files.values():
            name = str(uuid.uuid4()) + ext
        return name

    def new_file(self, ext: str, filename_without_ext: Optional[str] = None, timeout=3600) -> CachedFile:
        """
        ext: like ".jpg"
        """
        filename = (filename_without_ext + ext) if filename_without_ext else self._random_filename(ext)
        filepath = os.path.join(gallery_config.cache_dir, filename)
        file = CachedFile(filename, filepath, timeout=timeout)
        self.files[filename] = file
        return file

    def get_file(self, url: str, try_load: bool = False) -> Optional[CachedFile]:
        file = self.files.get(url)
        if try_load and not file:
            filepath = os.path.join(gallery_config.cache_dir, url)
            if os.path.exists(filepath):
                file = CachedFile(url, filepath)
                self.files[url] = file
        return file

    def take_over_files(self, re_expr: str, ignore_case=False, timeout: int = 3600) -> int:
        import re
        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(re_expr, flags)
        count = 0
        for filename in os.listdir(gallery_config.cache_dir):
            if pattern.match(filename):
                self.get_file(filename, try_load=True).update_timeout(timeout)
                count += 1
        return count

    async def download(self, url: str, extra: dict | None = None, bot: Bot | None = None) -> CachedFile:
        if url in self.files:
            return self.files[url].renewed().update_extra(extra)
        for attempt in range(2):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 400 and attempt == 0 and bot:
                        try:
                            logger.debug(await bot.call_api("get_rkey"))
                        except Exception as e:
                            logger.warning(f"尝试刷新 rkey 失败: {e}")
                        continue
                    if resp.status != 200:
                        raise Exception(f"下载文件 {url[:32]}... 失败: {resp.status} {resp.reason}")
                    content_type = resp.headers.get("Content-Type", "")
                    ext = self._extension_from_content_type(content_type)
                    filename = self._random_filename(ext)
                    filepath = os.path.join(gallery_config.cache_dir, filename)
                    file = CachedFile(url, filepath)
                    self.files[url] = file
                    with open(filepath, "wb") as f:
                        f.write(await resp.read())
                    return file.update_extra(extra)
        assert False, "Unreachable"

    async def prune(self):
        current_time = datetime.now()
        self.files = {url: file for url, file in self.files.items() if
                      not file.used or (current_time - file.created_at).total_seconds() < file.timeout}
        keep_files = {file.local_path for file in self.files.values()}
        for filename in os.listdir(gallery_config.cache_dir):
            filepath = os.path.join(gallery_config.cache_dir, filename)
            if filepath not in keep_files:
                try:
                    os.remove(filepath)
                    logger.debug(f"Removed cached file: {filepath}")
                except Exception as e:
                    logger.warning(f"Failed to remove cached file {filepath}: {e}")


file_cache = FileCache()


async def get_images_from_context(event: MessageEvent, bot: Bot):
    images: list[Tuple[str, Optional[str]]] = []
    messages = [msg for msg in event.message]
    if event.reply:
        messages.extend(event.reply.message)
    while len(messages) > 0:
        seg = messages.pop(0)
        message_type = seg["type"] if isinstance(seg, dict) and seg.get("type") else seg.type
        message_data = seg["data"] if isinstance(seg, dict) and seg.get("data") else seg.data

        if message_type == "image":
            images.append((message_data['url'], message_data.get('file')))
        elif message_type == 'mface':
            if 'url' in message_data:
                images.append((message_data['url'], message_data.get('file')))
        elif message_type == "forward":
            if content := message_data.get("content"):
                if isinstance(content, list):
                    for item in content:
                        messages.extend(item.get("message", []))
                    continue
            result = await bot.call_api('get_forward_msg', **{'id': str(message_data['id'])})
            for item in result['messages']:
                messages.extend(item['message'])
        elif message_type == "json":
            try:
                json_data = json.loads(message_data["data"])

                if json_data.get("app") == "com.tencent.multimsg":
                    forward_id = json_data.get("meta", {}).get("detail", {}).get("resid")
                    if forward_id:
                        result = await bot.call_api('get_forward_msg', **{'id': str(forward_id)})
                        for item in result['messages']:
                            messages.extend(item['message'])

            except Exception as e:
                logger.warning(f"解析 JSON 消息段失败: {e}")

    return images


async def download_images(image_urls: list[str | Tuple[str, Optional[str]]], bot: Bot | None = None) -> list[CachedFile]:
    tasks = [file_cache.download(url, {"file_id": file_id}, bot) for url, file_id in image_urls]
    downloaded_files = await asyncio.gather(*tasks)
    return list(downloaded_files)
