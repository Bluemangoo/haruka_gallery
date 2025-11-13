import asyncio
import io
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Union

import aiohttp
from nonebot import get_bot, logger, Bot
from nonebot.adapters.onebot.v11 import MessageEvent, Message, MessageSegment
from nonebot.internal.matcher import Matcher

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

    def __init__(self, url: str, local_path: str):
        self.url = url
        self.local_path = local_path
        self.used = False
        # current time
        self.created_at = datetime.now()
        self.extra = {}

    def __repr__(self):
        return f"<CachedFile url={self.url} local_path={self.local_path} used={self.used} created_at={self.created_at} extra={self.extra}>"

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


class DownloadCache:
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

    def new_file(self, ext: str) -> CachedFile:
        filename = self._random_filename(ext)
        filepath = os.path.join(gallery_config.cache_dir, filename)
        file = CachedFile(filename, filepath)
        return file

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
                      not file.used or (current_time - file.created_at).total_seconds() < 3600}
        keep_files = {file.local_path for file in self.files.values()}
        for filename in os.listdir(gallery_config.cache_dir):
            filepath = os.path.join(gallery_config.cache_dir, filename)
            if filepath not in keep_files:
                try:
                    os.remove(filepath)
                except Exception as e:
                    logger.warning(f"Failed to remove cached file {filepath}: {e}")


download_cache = DownloadCache()


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
    tasks = [download_cache.download(url, {"file_id": file_id}) for url, file_id in image_urls]
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

    def pop_all(self) -> Optional[str]:
        rng = self._current_range()
        if rng is None:
            return None
        start, _ = rng
        rest = self._s[start:].strip()
        self._idx = len(self._tokens)
        return rest if rest != "" else None

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


from .gallery import ImageMeta


class MessageBuilder:
    def __init__(self):
        self.message = Message()
        self._reply_id: Optional[int] = None
        self._healing_map: list[Optional[ImageMeta]] = []

    def text(self, text: Optional[str], newline: bool = True):
        if text is not None:
            if newline:
                self.message.append(MessageSegment.text(text + "\n"))
            else:
                self.message.append(MessageSegment.text(text))
            self._healing_map.append(None)
        return self

    def texts(self, texts: Optional[List[str]], newline: bool = True):
        if texts is not None:
            for text in texts:
                self.text(text, newline=newline)
        return self

    def image(self, file: Optional[Union[str, bytes, io.BytesIO, Path, ImageMeta]]):
        if file is None:
            return self

        last_segment = self.message[-1] if self.message else None
        if last_segment and last_segment.type == "text":
            text_data = last_segment.data.get("text", "")
            if text_data.endswith("\n"):
                text_data = text_data[:-1]
                last_segment.data["text"] = text_data

        segment_to_send: MessageSegment
        meta_to_map: Optional['ImageMeta'] = None

        if isinstance(file, ImageMeta):
            meta_to_map = file
            path_str = file.get_image_path()
            path_obj = Path(path_str)
            if not path_obj.exists():
                logger.warning(f"图片文件不存在: {path_str}，已清理")
                file.drop()
                return self

            if file.file_id:
                segment_to_send = MessageSegment.image(file=file.file_id)
            elif file.suffix == ".gif":
                file_content = path_obj.read_bytes()
                segment_to_send = MessageSegment.image(file=file_content)
            else:
                segment_to_send = MessageSegment.image(file=path_obj)
        else:
            segment_to_send = MessageSegment.image(file=file)

        if segment_to_send:
            self.message.append(segment_to_send)
            self._healing_map.append(meta_to_map)

        return self

    def reply_to(self, message_id_or_event: Union[int, str, MessageEvent]):
        if isinstance(message_id_or_event, MessageEvent):
            message_id_or_event = message_id_or_event.message_id
        self._reply_id = int(message_id_or_event)
        return self

    async def send(self, matcher: Matcher, bot: Optional[Bot] = None):
        if not self.message and not self._reply_id:
            logger.warning("MessageBuilder: 消息为空，取消发送。")
            return

        final_message = self.message.copy()
        healing_map = self._healing_map.copy()

        if final_message:
            last_segment = final_message[-1]
            if last_segment.type == "text":
                text_data = last_segment.data.get("text", "")
                if text_data.endswith("\n"):
                    text_data = text_data[:-1]
                    last_segment.data["text"] = text_data

        reply_id_to_use = self._reply_id

        if reply_id_to_use is not None:
            final_message.insert(0, MessageSegment.reply(reply_id_to_use))
            healing_map.insert(0, None)

        try:
            await matcher.send(final_message)
        except Exception as e:
            if '1200' in str(e):
                logger.warning(f"发送失败 (retcode={1200})，缓存失效。启动自愈...")
                bot = bot or get_bot()
                await self._handle_healing(final_message, healing_map, matcher, bot)
            else:
                logger.error(f"MessageBuilder 发送失败 (非 1200): {e}")
                raise e

    async def _handle_healing(self, failed_message: Message, healing_map: list[Optional[ImageMeta]], matcher: Matcher,
                              bot: Bot):
        """
        私有方法：处理缓存失效后的重建、重发、更新逻辑
        """
        healed_message = Message()
        new_seg_to_meta_map: dict[int, ImageMeta] = {}

        needs_healing = False

        for i, seg in enumerate(failed_message):
            if seg.type != 'image':
                healed_message.append(seg)
                continue

            meta: Optional['ImageMeta'] = healing_map[i]

            if not meta:
                healed_message.append(seg)
                continue

            needs_healing = True
            logger.debug(f"ImageMeta {meta.id} (file_id: {meta.file_id}) 失效, 换用本地路径。")
            path_str = meta.get_image_path()
            path_obj = Path(path_str)

            new_seg: MessageSegment | None = None
            if not path_obj.exists():
                logger.error(f"自愈失败：ImageMeta {meta.id} 本地文件已丢失: {path_str}")
                meta.drop()
            elif meta.suffix == ".gif":
                new_seg = MessageSegment.image(file=path_obj.read_bytes())
            else:
                new_seg = MessageSegment.image(file=path_obj)

            if new_seg:
                healed_message.append(new_seg)
                new_seg_to_meta_map[id(new_seg)] = meta

        if not needs_healing:
            logger.error("捕获 1200，但没有可自愈的图片 (没有 ImageMeta 映射)。")
            return

        try:
            logger.debug("尝试使用'治愈'后的消息发送...")
            send_receipt = await matcher.send(healed_message, reply=False)
            if not send_receipt or 'message_id' not in send_receipt:
                logger.warning("自愈后发送成功，但未收到 message_id 回执，无法更新 file_id。")
                return
        except Exception as e2:
            logger.error(f"自愈后发送依然失败: {e2}")
            return

        try:
            message_id = send_receipt['message_id']
            sent_message_data = await bot.get_msg(message_id=message_id)
            sent_message = sent_message_data['message']
        except Exception as e3:
            logger.error(f"自愈成功，但获取新 file_id 失败: {e3}")
            return

        if len(healed_message) != len(sent_message):
            logger.warning("自愈后消息与回执数量不匹配，无法安全更新 file_id。")
            return

        for j, (healed_segment, sent_message) in enumerate(zip(healed_message, sent_message)):
            meta = healing_map[j]

            new_file_id = sent_message.get("data").get('file')

            if meta and new_file_id:
                meta.update_file_id(new_file_id)
                logger.info(f"ImageMeta {meta.id} 自愈成功, 更新 file_id: {new_file_id}")
            elif meta:
                logger.warning(f"ImageMeta {meta.id} 自愈成功, 但未在回执中找到 new_file_id。")
