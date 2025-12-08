import asyncio
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Union, OrderedDict

import aiohttp
from nonebot import get_bot, logger
from nonebot.adapters.onebot.v11 import MessageEvent

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


class FileLRUCache:
    def __init__(self, max_size_mb: float = 20):
        self.capacity_bytes = int(max_size_mb * 1024 * 1024)  # mb
        self.max_file_size = int(self.capacity_bytes / 20)
        self.current_size = 0
        self.cache = OrderedDict()

    def __repr__(self):
        return f"<FileLRUCache current_size={self.current_size} bytes, capacity={self.capacity_bytes} bytes, file_count={len(self.cache)}>"

    @staticmethod
    def _resolve_path(path: Union[str, Path]) -> Path:
        return Path(path).resolve()

    def read(self, path: Union[str, Path]) -> bytes:
        key = self._resolve_path(path)

        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]

        with open(key, 'rb') as f:
            content = f.read()

        content_size = len(content)

        if content_size > self.max_file_size:
            return content

        while self.current_size + content_size > self.capacity_bytes:
            removed_path, removed_content = self.cache.popitem(last=False)
            self.current_size -= len(removed_content)

        self.cache[key] = content
        self.current_size += content_size

        return content

    def drop(self, path: Union[str, Path]) -> bool:
        key = self._resolve_path(path)

        if key in self.cache:
            content = self.cache.pop(key)
            self.current_size -= len(content)
            return True
        return False

    def clear(self):
        self.cache.clear()
        self.current_size = 0


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
        self.memory_lru = FileLRUCache()
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

    async def download(self, url: str, extra: dict | None = None) -> CachedFile:
        if url in self.files:
            return self.files[url].renewed().update_extra(extra)

        async with aiohttp.ClientSession() as session:
            async with session.get(url, verify_ssl=False) as resp:
                if resp.status != 200:
                    raise Exception(f"下载文件 {os.truncate(url, 32)} 失败: {resp.status} {resp.reason}")
                content_type = resp.headers.get("Content-Type", "")
                ext = self._extension_from_content_type(content_type)
                filename = self._random_filename(ext)
                filepath = os.path.join(gallery_config.cache_dir, filename)
                file = CachedFile(url, filepath)
                self.files[url] = file
                with open(filepath, "wb") as f:
                    f.write(await resp.read())
                return file.update_extra(extra)

    async def prune(self):
        current_time = datetime.now()
        self.files = {url: file for url, file in self.files.items() if
                      not file.used or (current_time - file.created_at).total_seconds() < file.timeout}
        keep_files = {file.local_path for file in self.files.values()}
        for filename in os.listdir(gallery_config.cache_dir):
            filepath = os.path.join(gallery_config.cache_dir, filename)
            if filepath not in keep_files:
                try:
                    self.memory_lru.drop(filepath)
                    os.remove(filepath)
                    logger.debug(f"Removed cached file: {filepath}")
                except Exception as e:
                    logger.warning(f"Failed to remove cached file {filepath}: {e}")

    def read_content(self, file_or_url: str | CachedFile) -> bytes:
        target_path = None

        if isinstance(file_or_url, CachedFile):
            target_path = file_or_url.local_path
        elif isinstance(file_or_url, str):
            cf = self.get_file(file_or_url)
            if cf:
                target_path = cf.local_path
            else:
                target_path = file_or_url

        if target_path and os.path.exists(target_path):
            return self.memory_lru.read(target_path)

        raise FileNotFoundError(f"File not found: {file_or_url}")


file_cache = FileCache()


async def get_images_from_context(event: MessageEvent):
    images: list[Tuple[str, Optional[str]]] = []
    messages = [msg for msg in event.message]
    bot = get_bot()
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


async def download_images(image_urls: list[str | Tuple[str, Optional[str]]]) -> list[CachedFile]:
    tasks = [file_cache.download(url, {"file_id": file_id}) for url, file_id in image_urls]
    downloaded_files = await asyncio.gather(*tasks)
    return downloaded_files


class ArgParser:
    def __init__(self, s: Optional[str]):
        self._s: str = s or ""
        self._tokens: List[Tuple[int, int]] = []
        self._idx: int = 0
        self._build_tokens()

    def _build_tokens(self) -> None:
        self._tokens.clear()
        s = self._s
        n = len(s)
        i = 0
        while i < n:
            while i < n and s[i] == " ":
                i += 1
            if i >= n:
                break
            start = i
            while i < n and s[i] != " ":
                i += 1
            end = i
            if start < end:
                self._tokens.append((start, end))

    def _current_range(self) -> Optional[Tuple[int, int]]:
        self._skip_empty_tokens()
        if self._idx >= len(self._tokens):
            return None
        return self._tokens[self._idx]

    def _skip_empty_tokens(self) -> None:
        while self._idx < len(self._tokens):
            start, end = self._tokens[self._idx]
            if start < end and self._s[start:end].strip() != "":
                break
            self._idx += 1

    def peek(self, chars: Optional[int] = None) -> Optional[str]:
        rng = self._current_range()
        if rng is None:
            return None
        start, end = rng
        token = self._s[start:end]
        if chars is None:
            res = token.strip()
        else:
            if not isinstance(chars, int) or chars <= 0:
                return None
            take = min(chars, end - start)
            res = token[:take].strip()
        return res if res != "" else None

    def pop(self, chars: Optional[int] = None) -> Optional[str]:
        rng = self._current_range()
        if rng is None:
            return None
        start, end = rng
        token = self._s[start:end]
        if chars is None:
            res = token.strip()
            self._idx += 1
            # 防守：跳过任何空 token（不太可能）
            self._skip_empty_tokens()
            return res if res != "" else None
        else:
            if not isinstance(chars, int) or chars <= 0:
                return None
            token_len = end - start
            if chars >= token_len:
                # 忽略多余，只消费整个 token
                res = token.strip()
                self._idx += 1
                self._skip_empty_tokens()
                return res if res != "" else None
            else:
                part = token[:chars].strip()
                new_start = start + chars
                # new_start < end 因为 chars < token_len
                self._tokens[self._idx] = (new_start, end)
                # 更新后再做一次防守性跳过（一般不跳过，但保持一致）
                self._skip_empty_tokens()
                return part if part != "" else None

    def pop_all(self) -> str:
        rng = self._current_range()
        if rng is None:
            return ""
        start, _ = rng
        rest = self._s[start:].strip()
        self._idx = len(self._tokens)
        return rest

    def check_and_pop(self, expected: str) -> bool:
        token = self.peek()
        if token == expected:
            self.pop()
            return True
        return False

    def remaining_count(self) -> int:
        self._skip_empty_tokens()
        return max(0, len(self._tokens) - self._idx)

    def __repr__(self) -> str:
        rng = self._current_range()
        cur = None
        if rng:
            cur = self._s[rng[0]:rng[1]]
        return f"<ArgParser current={cur!r} remaining={self.remaining_count()}>"
