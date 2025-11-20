import io
from collections.abc import Iterable
from pathlib import Path
from typing import Optional, Union, List

from nonebot import logger, get_bot, Bot
from nonebot.adapters.onebot.v11 import MessageSegment, Message, MessageEvent
from nonebot.internal.matcher import Matcher

from .config import gallery_config
from .gallery import ImageMeta


class MessageBuilder:
    def __init__(self):
        self.message = Message()
        self._reply_id: Optional[int] = None
        self._healing_map: list[Optional[ImageMeta]] = []
        self.have_non_file_id_image = False

    def text(self, text: Optional[str], newline: bool = True):
        if text is not None:
            if newline:
                self.message.append(MessageSegment.text(text + "\n"))
            else:
                self.message.append(MessageSegment.text(text))
            self._healing_map.append(None)
        return self

    def texts(self, texts: Optional[Iterable[str]], newline: bool = True):
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
            else:
                self.have_non_file_id_image = True
                if file.suffix == ".gif":
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

    def node(self, content: "MessageBuilder", bot: Optional[Bot] = None):

        actual_content = Message()

        for i, seg in enumerate(content.message):
            meta = content._healing_map[i] if i < len(content._healing_map) else None

            if seg.type == "image" and meta:
                path_str = meta.get_image_path()
                path_obj = Path(path_str)

                if path_obj.exists():
                    if meta.suffix == ".gif":
                        new_seg = MessageSegment.image(file=path_obj.read_bytes())
                    else:
                        new_seg = MessageSegment.image(file=path_obj)
                    actual_content.append(new_seg)
                else:
                    logger.warning(f"构造转发消息时图片丢失: {path_str}")
                    actual_content.append(seg)
            else:
                actual_content.append(seg)

        if actual_content:
            last_segment = actual_content[-1]
            if last_segment.type == "text":
                text_data = last_segment.data.get("text", "")
                if text_data.endswith("\n"):
                    text_data = text_data[:-1]
                    last_segment.data["text"] = text_data

        seg = MessageSegment.node_custom(
            user_id=gallery_config.bot_id or int((bot or get_bot()).self_id),
            nickname=gallery_config.bot_name,
            content=actual_content
        )

        self.message.append(seg)
        self._healing_map.append(None)

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
            send_receipt = await matcher.send(final_message)
            if self.have_non_file_id_image:
                await self.update_file_id(send_receipt, bot or get_bot(), final_message, healing_map)
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

        await self.update_file_id(send_receipt, bot, healed_message, healing_map)

    async def update_file_id(self, send_receipt, bot: Bot, message: Message, healing_map: list[Optional[ImageMeta]]):
        try:
            message_id = send_receipt['message_id']
            sent_message_data = await bot.get_msg(message_id=message_id)
            sent_message = sent_message_data['message']
        except Exception as e3:
            logger.error(f"自愈成功，但获取新 file_id 失败: {e3}")
            return

        if len(message) != len(sent_message):
            logger.warning("自愈后消息与回执数量不匹配，无法安全更新 file_id。")
            return

        for j, sent_message in enumerate(sent_message):
            meta = healing_map[j]

            new_file_id = sent_message.get("data").get('file')

            if meta and new_file_id:
                meta.update_file_id(new_file_id)
                logger.info(f"ImageMeta {meta.id} 自愈成功, 更新 file_id: {new_file_id}")
            elif meta:
                logger.warning(f"ImageMeta {meta.id} 自愈成功, 但未在回执中找到 new_file_id。")
