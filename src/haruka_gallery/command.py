import io
import re
from enum import Enum
from zipfile import ZipFile

from nonebot import on_command, on_message, Bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.internal.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.rule import startswith

from .gallery import gallery_manager, Gallery, ImageMeta, get_random_image, get_all_image, GalleryFilter
from .message_builder import MessageBuilder, ForwardMessageBuilder
from .plot import *
from .utils import get_images_from_context, download_images, CachedFile, file_cache
from .arg_parser import ArgParser, FullArgParser, ArgValueString, ArgValueStringWithRule, ArgValueList, ArgValueAmount, \
    ArgValueEnum, ArgValueInt

gall_command = on_command("gallery", aliases={"画廊", "gall"}, force_whitespace=True, priority=5)
kan_command = on_command("看", priority=8)
shangchuan_command = on_command("上传", priority=8)
upload_command = on_command("upload", force_whitespace=True, priority=5)


@gall_command.handle()
async def _(event: MessageEvent, matcher: Matcher, bot: Bot, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        subcommand, *params = text.split(" ", 1)
        params = params[0] if params else ""
        if subcommand == "add" or subcommand == "upload" or subcommand == "添加" or subcommand == "上传":
            return await add_image(event, params, matcher, bot)
        if subcommand == "remove" or subcommand == "删除":
            return await remove_image(event, params, matcher, bot)
        if subcommand == "modify" or subcommand == "修改":
            return await modify_image(event, params, matcher, bot)
        if subcommand == "move" or subcommand == "移动":
            return await move_image(event, params, matcher, bot)
        if subcommand == "show" or subcommand == "查看" or subcommand == "看":
            return await random_image(event, params, matcher)
        if subcommand == "show-all" or subcommand == "查看全部" or subcommand == "看全部" or subcommand == "查看所有" or subcommand == "看所有":
            return await random_image(event, "全部" + params, matcher)
        if subcommand == "count":
            return await count_images(event, params, matcher)
        if subcommand == "download" or subcommand == "下载":
            return await download_image(event, params, matcher, bot)
        if subcommand == "details" or subcommand == "详情":
            return await show_details(event, params, matcher, bot)
        if subcommand == "add-gallery" or subcommand == "创建画廊":
            return await add_gallery(event, params, matcher)
        if subcommand == "modify-gallery" or subcommand == "修改画廊":
            return await modify_gallery(event, params, matcher)
        if subcommand == "remove-gallery" or subcommand == "删除画廊":
            return await remove_gallery(event, params, matcher)
        if subcommand == "list-gallery" or subcommand == "list-galleries" or subcommand == "列出画廊":
            return await list_galleries(event, params, matcher)
        if subcommand == "clear" or subcommand == "清空画廊":
            return await clear_gallery(event, params, matcher)
        if subcommand == "set-alias" or subcommand == "设置别名":
            return await set_alias(event, params, matcher)
        if subcommand == "list-alias" or subcommand == "list-aliases" or subcommand == "列出别名":
            return await list_aliases(event, params, matcher)
        if subcommand == "remove-alias" or subcommand == "删除别名":
            return await remove_alias(event, params, matcher)
        return await reply_help(event, matcher)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(matcher)
        raise e


@kan_command.handle()
async def _(event: MessageEvent, matcher: Matcher, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await random_image(event, text, matcher)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(matcher)
        raise e


@shangchuan_command.handle()
@upload_command.handle()
async def _(event: MessageEvent, matcher: Matcher, bot: Bot, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await add_image(event, text, matcher, bot)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(matcher)
        raise e


async def reply_help(_event: MessageEvent, matcher: Matcher):
    help_text = (
        "画廊命令帮助 (/gall /gallery /画廊)：\n"
        "/gall {add-gallery | 创建画廊} <画廊名称> - 创建一个新的画廊，提供多个名称则作为别名\n"
        "/gall {modify-gallery | 修改画廊} <画廊名称> [+别名] [-别名] - 修改画廊名称，使用 + 添加别名，- 删除别名\n"
        "/gall {list-galleries | 列出画廊} - 列出所有画廊\n"
        # "/gall {remove-gallery | 删除画廊} <画廊名称> - 删除指定名称的画廊\n"
        # "/gall {clear | 清空画廊} <画廊名称> - 清空指定画廊中的所有图片\n"
        "/gall count <画廊名称> [筛选条件] - 统计画廊中符合条件的图片数量\n"
        "/gall {add | upload | 添加 | 上传} <画廊名称> [force | 强制] [skip | 跳过] [replace | 替换]  <图片链接或回复图片> - 添加图片到画廊，使用 force 参数可强制添加重复图片\n"
        "/gall {modify | 修改} <图片ID> [+#标签 | -#标签 | --tag +标签1 | --tags +标签1,-标签2] [-- 备注] - 修改图片的标签和备注\n"
        "/gall {move | 移动} <目标画廊名称> <图片ID1> <图片ID2> ... - 将指定ID的图片移动到目标画廊\n"
        "/gall {remove | 删除} <图片ID> - 从画廊中删除指定ID的图片\n"
        "/gall {show | 查看 | 看} {<画廊名称> | *} [筛选条件] [排序条件] [数量] - 随机查看画廊中的图片，数量可使用 xN 或 N 表示 (需要在备注前面)\n"
        "/gall {show | 查看 | 看} <图片ID1> <图片ID2> ... - 查看指定ID的图片\n"
        "/gall {show-all | 查看全部 | 看全部} {<画廊名称> | *} [筛选条件] - 查看画廊中的所有图片缩略图\n"
        "/gall {details | 详情} <图片ID> - 查看指定ID图片的详细信息\n"
        "/gall {set-alias | 设置别名} <别名> {<画廊名称> | *} [筛选条件] - 给画廊及筛选条件添加别名，筛选条件同查看命令\n"
        "/gall {list-aliases | 列出别名} - 列出所有别名\n"
        "/gall {remove-alias | 删除别名} <别名> - 删除画廊的别名\n"
        "\n"
        "筛选条件 - 画廊名称用 * 匹配所有画廊，筛选条件可使用 [#标签 | --tag 标签 | --tags 标签1,标签2] [-- 备注]\n"
        "排序条件 - 用 --offset n 指定偏移(跳过)量，按照 id 排序，为负值则反向取; --startswith id 从指定 id 开始取"
        "\n"
        "alias：\n"
        "/看 - /gall show\n"
        "/上传 - /gall add\n"
        "\n"
        "详细用法请参考：https://github.com/Bluemangoo/haruka_gallery"
    )
    return await ForwardMessageBuilder().node(MessageBuilder().text(help_text)).send(matcher)


async def add_gallery(event: MessageEvent, params: str, matcher: Matcher):
    gallery_names: list[str] = params.split(" ")
    if len(gallery_names) == 0:
        return await reply_help(event, matcher)

    exist_names = [name for name in gallery_names if
                   gallery_manager.check_exists(name) or gallery_manager.check_filter_exists(name)]
    if len(exist_names) > 0:
        return await MessageBuilder().text(f"画廊 {', '.join(exist_names)} 已存在").reply_to(event).send(matcher)
    else:
        gallery_manager.add_gallery(gallery_names)
        return await MessageBuilder().text(f"成功创建画廊 {params}").reply_to(event).send(matcher)


async def clear_gallery(event: MessageEvent, params: str, matcher: Matcher):
    args = ArgParser(params)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)
    for image in gallery.list_images():
        image.drop()
    return await MessageBuilder().text(f"已清空画廊 {gallery_name} 中的所有图片").reply_to(event).send(matcher)


async def modify_gallery(event: MessageEvent, params: str, matcher: Matcher):
    args = ArgParser(params)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)

    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)

    names = gallery.name

    while current := args.pop():
        if current.startswith("+"):
            new_name = current[1:]
            if new_name not in names:
                names.append(new_name)
        elif current.startswith("-"):
            del_name = current[1:]
            if del_name in names:
                names.remove(del_name)

    gallery.update_name()
    return await MessageBuilder().text(f"已修改画廊名称为：{' '.join(gallery.name)}").reply_to(event).send(matcher)


async def remove_gallery(event: MessageEvent, params: str, matcher: Matcher):
    gallery_name = params.strip()
    if gallery_name == "":
        return await reply_help(event, matcher)
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)

    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)

    gallery.drop()
    return await MessageBuilder().text(f"已删除画廊 {gallery_name}").reply_to(event).send(matcher)


async def list_galleries(event: MessageEvent, _param: str, matcher: Matcher):
    galleries = gallery_manager.galleries
    if len(galleries) == 0:
        return await MessageBuilder().text("当前没有任何画廊").reply_to(event).send(matcher)
    message_builder = MessageBuilder()
    message_builder.text(f"当前画廊列表({len(galleries)})：")
    for gallery in galleries:
        message_builder.text(f"- (#{gallery.id}){' / '.join(gallery.name)} (图片数量: {gallery.count_images()})")
    return await ForwardMessageBuilder().node(message_builder).send(matcher)


async def add_image(event: MessageEvent, params: str, matcher: Matcher, bot: Bot):
    warnings = set()
    if "＃" in params:
        params = params.replace("＃", "#")
        warnings.add("检测到全角井号＃，已自动替换为半角#")
    args = ArgParser(params)

    class Mode(Enum):
        NORMAL = 0
        FORCE = 1
        SKIP = 2
        REPLACE = 3

    parser = FullArgParser()
    parser.add_optional_arg("mode", ArgValueEnum(
        {
            "force": Mode.FORCE, "强制": Mode.FORCE,
            "skip": Mode.SKIP, "跳过": Mode.SKIP,
            "replace": Mode.REPLACE, "替换": Mode.REPLACE
        }))
    parser.add_positional_arg("gallery", ArgValueStringWithRule(check_name))
    parser.add_named_arg("tag", ArgValueStringWithRule(check_name), multiple_value=True)
    parser.add_named_arg("tag", ArgValueStringWithRule(check_name), aliases_start_with=["#"], multiple_value=True)
    parser.add_named_arg("tags", ArgValueList(ArgValueStringWithRule(check_name)), multiple_value=True)
    parser.set_final_string_arg("comment", ArgValueString())
    parser.add_optional_arg("comment", ArgValueString())

    result = parser.parse(args)
    mode = result.get("mode") or Mode.NORMAL
    gallery_name = result.get("gallery")
    if gallery_name is None:
        return await reply_help(event, matcher)
    filters = gallery_manager.get_filters(gallery_name)
    gallery: Gallery = gallery_manager.find_gallery(filters.gallery)

    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)

    unknown_args = result.unknown_args
    comment = result.get("comment") or ""
    filters.tags.extend(result.get("tag") or [])
    filters.tags.extend(result.get("tags") or [])

    filters.tags = list(dict.fromkeys(filters.tags))
    if comment != "":
        filters.comment = comment
    if filters.comment is None:
        filters.comment = ""

    if gallery.require_comment:
        if filters.comment == "":
            return await MessageBuilder().text(
                f"画廊 {filters.gallery} 需要添加备注，请使用 -- 备注 内容添加备注").reply_to(
                event).send(matcher)

    message_builder = MessageBuilder().reply_to(event)
    message_builder.texts([f"警告：{warning}。" for warning in warnings])
    if len(unknown_args) > 0:
        message_builder.text(f"未知参数：{' '.join(unknown_args)}。")
        message_builder.text("tips：备注包含空格或关键字请使用如\" -- comment\"")
        return await message_builder.send(matcher)

    images = await get_images_from_context(event, bot)
    if len(images) == 0:
        return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)
    image_files = await download_images(images, bot)
    all_image_files = [img for img in image_files]

    existing_images: list[Tuple[CachedFile, list[ImageMeta]]] = []
    replaced_images: list[Tuple[CachedFile, ImageMeta]] = []
    replaced_indexes: list[int] = []
    replaced_images2: list[Tuple[ImageMeta, ImageMeta]] = []
    if mode != Mode.FORCE:
        for i, image in enumerate(image_files):
            sames = gallery.find_same_image(image.local_path)
            if sames and len(sames) > 0:
                if mode == Mode.REPLACE:
                    replaced_images.append((image, sames[0]))
                    replaced_indexes.append(i)
                else:
                    existing_images.append((image, sames))

        existing_image_files = [image for image, _ in existing_images]
        image_files = [image for image in image_files if image not in existing_image_files]

    image_obj = None
    for i, image in enumerate(image_files):
        image_obj = gallery.add_image_unchecked(image.local_path, filters.comment, filters.tags, str(event.user_id),
                                                file_id=image.extra.get("file_id"))
        if i in replaced_indexes:
            replaced_images2.append((image_obj, replaced_images[replaced_indexes.index(i)][1]))

    if len(all_image_files) > 0:
        message_builder.text(f"成功添加 {len(image_files)}/{len(all_image_files)} 张图片到画廊 {filters.gallery}。")
    if len(image_files) == 1:
        message_builder.text(f"新图片ID：{image_obj.id}。")
    if len(filters.tags) > 0:
        message_builder.text(f"添加的图片附加标签：{', '.join(filters.tags)}。")
    if filters.comment != "":
        message_builder.text(f"添加的图片附加备注：{filters.comment}。")
    if mode != Mode.SKIP and (len(existing_images) > 0 or len(replaced_images) > 0):
        if len(existing_images) > 0:
            message_builder.text(f"{len(existing_images)} 张图片已存在于画廊 {filters.gallery}：")
        if len(replaced_images) > 0:
            message_builder.text(f"{len(replaced_images)} 张图片已存在于画廊 {filters.gallery}，并被替换：")

        canvas_items: List[Tuple[Image, Image, str, str]] = []

        for image, sames in existing_images:
            img = Image.open(image.local_path)
            img.thumbnail(gallery_config.repeat_image_show_size)
            pic = sames[0]
            img2 = pic.get_image()
            img2.thumbnail(gallery_config.repeat_image_show_size)
            canvas_items.append((img, img2, "待上传图片", f"id: {pic.id}"))

        for pic_added, pic_exist in replaced_images2:
            img = pic_added.get_image()
            img.thumbnail(gallery_config.repeat_image_show_size)
            img2 = pic_exist.get_image()
            img2.thumbnail(gallery_config.repeat_image_show_size)
            canvas_items.append((img, img2, f"已上传id: {pic_added.id}", f"被替换id: {pic_exist.id}"))

        with Canvas(bg=FillBg((230, 240, 255, 255))).set_padding(8) as canvas:
            with VSplit().set_padding(0).set_sep(16).set_item_align('lt').set_content_align('lt'):
                TextBox(f"查重错误可使用\"/上传 force\"强制上传图片", TextStyle(DEFAULT_FONT, 16, BLACK))
                with Grid(row_count=int(math.sqrt(len(canvas_items) * 2)), hsep=8,
                          vsep=8).set_item_align(
                    't').set_content_align('t'):
                    for image, same, text1, text2 in canvas_items:
                        with HSplit().set_padding(0).set_sep(4):
                            with VSplit().set_padding(0).set_sep(4).set_content_align('c').set_item_align('c'):
                                ImageBox(image=image, size=gallery_config.repeat_image_show_size,
                                         image_size_mode='fit').set_content_align('c')
                                TextBox(text1, TextStyle(DEFAULT_FONT, 16, BLACK))
                            with VSplit().set_padding(0).set_sep(4).set_content_align('c').set_item_align('c'):
                                if same:
                                    ImageBox(image=same, size=gallery_config.repeat_image_show_size,
                                             image_size_mode='fit').set_content_align('c')
                                else:
                                    Spacer(w=gallery_config.repeat_image_show_size[0],
                                           h=gallery_config.repeat_image_show_size[1])
                                TextBox(text2, TextStyle(DEFAULT_FONT, 16, BLACK))
        repeat_img = await canvas.get_img()
        file = io.BytesIO()
        repeat_img.save(file, format="PNG")
        message_builder.image(file)
    for _, image in replaced_images:
        image.drop()
    await message_builder.send(matcher)
    for image in all_image_files:
        image.mark_used()
    return None


async def count_images(event: MessageEvent, params: str, matcher: Matcher):
    args = ArgParser(params)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    filters = gallery_manager.get_filters(gallery_name)

    arg_parser = FullArgParser()
    arg_parser.add_named_arg("tag", ArgValueStringWithRule(check_name), aliases_start_with=["#"], multiple_value=True)
    arg_parser.add_named_arg("tag", ArgValueList(ArgValueStringWithRule(check_name)), multiple_value=True)
    arg_parser.set_final_string_arg("comment", ArgValueString())
    arg_parser.add_optional_arg("comment", ArgValueString())

    parse_result = arg_parser.parse(args)
    comment = parse_result.get("comment") or ""
    filters.tags.extend(parse_result.get("tag") or [])

    comment = comment.strip() if comment else None
    if comment:
        filters.comment = comment
    gallery: Gallery | None = None
    if filters.gallery != "*":
        gallery: Gallery = gallery_manager.find_gallery(filters.gallery)

        if not gallery:
            return await MessageBuilder().text(f"没有找到画廊 {filters.gallery}").reply_to(event).send(matcher)

    images = get_all_image(gallery, tags=filters.tags, comment=filters.comment)
    message_builder = MessageBuilder().reply_to(event)
    message_builder.text(f"画廊 {filters.gallery} 中符合条件的图片数量为：{len(images)}")
    return await message_builder.send(matcher)


async def remove_image(event: MessageEvent, params: str, matcher: Matcher, bot: Bot):
    args = ArgParser(params)
    images = await find_gallery_images_by_arg_or_event(args, event, bot)
    message_builder = MessageBuilder().reply_to(event)
    if len(images) == 0:
        return await message_builder.text(f"没有找到图片").send(matcher)
    for image_id, image in images:
        if not image:
            message_builder.text(f"没有找到图片 {image_id}。")
            continue

        gallery = image.gallery
        image.drop()
        message_builder.text(f"已从画廊 {gallery.name} 中删除图片 {image_id}。")
    return await message_builder.send(matcher)


async def move_image(event: MessageEvent, params: str, matcher: Matcher, bot: Bot):
    args = ArgParser(params)
    message_builder = MessageBuilder().reply_to(event)
    target_gallery_name = args.pop()
    gallery = gallery_manager.find_gallery(target_gallery_name)
    if not gallery:
        return await message_builder.text(f"没有找到画廊 {target_gallery_name}").send(matcher)
    images = await find_gallery_images_by_arg_or_event(args, event, bot)
    if len(images) == 0:
        return await message_builder.text(f"没有找到图片").send(matcher)
    for image_id, image in images:
        if image:
            image.move_to(gallery)
            message_builder.text(f"已将图片 {image.id} 移动到画廊 {target_gallery_name}。")
        else:
            message_builder.text(f"没有找到图片 {image_id}。")
    return await message_builder.send(matcher)


async def download_image(event: MessageEvent, params: str, matcher: Matcher, bot: Bot):
    if not isinstance(event, GroupMessageEvent):
        return None
    if not await SUPERUSER(bot, event):
        return None

    warnings = set()
    if "＃" in params:
        params = params.replace("＃", "#")
        warnings.add("检测到全角井号＃，已自动替换为半角#")
    args = ArgParser(params)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    filters = gallery_manager.get_filters(gallery_name)

    arg_parser = FullArgParser()
    arg_parser.add_named_arg("tag", ArgValueStringWithRule(check_name), aliases_start_with=["#"], multiple_value=True)
    arg_parser.add_named_arg("tag", ArgValueList(ArgValueStringWithRule(check_name)), multiple_value=True)
    arg_parser.set_final_string_arg("comment", ArgValueString())
    arg_parser.add_optional_arg("count", ArgValueAmount())
    arg_parser.add_optional_arg("comment", ArgValueString())

    parse_result = arg_parser.parse(args)
    if parse_result.errors:
        builder = MessageBuilder().reply_to(event)
        for warning in warnings:
            builder.text(f"警告：{warning}。")
        if len(parse_result.unknown_args) > 0:
            builder.text(f"未知参数：{' '.join(parse_result.unknown_args)}。")
            builder.text("tips：本命令可选位置参数为图片数量，按备注筛选请使用如\" -- comment\"")
        for error in parse_result.errors:
            builder.text(f"参数解析错误：{error}。")
        return await builder.send(matcher)

    comment = parse_result.get("comment") or ""
    filters.tags.extend(parse_result.get("tag") or [])

    comment = comment.strip() if comment else None
    if comment:
        filters.comment = comment
    gallery: Gallery | None = None
    if filters.gallery != "*":
        gallery: Gallery = gallery_manager.find_gallery(filters.gallery)

        if not gallery:
            return await MessageBuilder().text(f"没有找到画廊 {filters.gallery}").reply_to(event).send(matcher)

    if filters.gallery == "*" and len(filters.tags) == 0 and filters.comment is None:
        return await MessageBuilder().text("参数不足，查看全部需要指定至少一个筛选条件").reply_to(event).send(matcher)

    images = get_all_image(gallery, tags=filters.tags, comment=filters.comment)
    if len(images) == 0:
        return await MessageBuilder().text("没有找到符合条件的图片").reply_to(event).send(matcher)
    message_builder = MessageBuilder().reply_to(event)
    for warning in warnings:
        message_builder.text(f"警告：{warning}。")
    message_builder.text(f"找到 {len(images)} 张符合条件的图片，正在打包...")
    receipt = await message_builder.send(matcher)
    if not receipt:
        raise RuntimeError("发送消息失败，无法继续打包图片")
    msg_id = receipt["message_id"]
    await bot.call_api("set_msg_emoji_like", message_id=msg_id, emoji_id="128064", set=True)

    zip_file = file_cache.new_file(".zip")
    with ZipFile(zip_file.local_path, "w") as zipf:
        for image in images:
            path = image.get_image_path()
            zipf.write(path, arcname=os.path.basename(path))
    await bot.call_api("set_msg_emoji_like", message_id=msg_id, emoji_id="128064", set=False)
    await bot.call_api("set_msg_emoji_like", message_id=msg_id, emoji_id="128235", set=True)
    await bot.call_api('upload_group_file', **{
        'group_id': int(event.group_id),
        'file': f'file://{os.path.abspath(zip_file.local_path)}',
        'name': str(filters) + ".zip",
        'folder': "/",
    })
    await bot.call_api("set_msg_emoji_like", message_id=msg_id, emoji_id="128235", set=False)
    return None


async def random_image(event: MessageEvent, params: str, matcher: Matcher):
    warnings = set()
    if "＃" in params:
        params = params.replace("＃", "#")
        warnings.add("检测到全角井号＃，已自动替换为半角#")
    args = ArgParser(params)
    need_all = False
    if args.peek(2) == "全部" or args.peek(2) == "所有":
        args.pop(2)
        need_all = True
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)

    if not need_all and gallery_name.replace("-", "").isdigit():
        return await show_image(event, params, matcher)
    unknown_args = []

    filters = gallery_manager.get_filters(gallery_name)

    arg_parser = FullArgParser()
    arg_parser.add_named_arg("tag", ArgValueStringWithRule(check_name), aliases_start_with=["#"], multiple_value=True)
    arg_parser.add_named_arg("tag", ArgValueList(ArgValueStringWithRule(check_name)), multiple_value=True)
    arg_parser.add_named_flag("details")
    arg_parser.add_named_flag("raw")
    arg_parser.set_final_string_arg("comment", ArgValueString())
    arg_parser.add_optional_arg("count", ArgValueAmount())
    arg_parser.add_named_arg("offset", ArgValueInt())
    arg_parser.add_named_arg("startswith", ArgValueInt())
    arg_parser.add_optional_arg("comment", ArgValueString())
    arg_parser.add_named_flag("each")

    parse_result = arg_parser.parse(args)
    count = parse_result.get("count") or 1
    comment = parse_result.get("comment") or ""
    offset: int | None = parse_result.get("offset")
    offset_startswith: int | None = parse_result.get("startswith")
    if offset is None and offset_startswith is not None:
        offset = 0
    with_details = parse_result.get("details") or False
    is_raw = parse_result.get("raw") or False
    require_each = parse_result.get("each") or False
    filters.tags.extend(parse_result.get("tag") or [])
    warnings.update(parse_result.errors)  # 只有这个功能可以这么做

    comment = comment.strip() if comment else None
    if comment:
        filters.comment = comment
    gallery: Gallery | None = None
    if filters.gallery != "*":
        gallery: Gallery = gallery_manager.find_gallery(filters.gallery)

        if not gallery:
            return await MessageBuilder().text(f"没有找到画廊 {filters.gallery}").reply_to(event).send(matcher)

    if need_all and filters.gallery == "*" and len(filters.tags) == 0 and filters.comment is None:
        return await MessageBuilder().text("参数不足，查看全部需要指定至少一个筛选条件").reply_to(event).send(matcher)

    # 看全部则 count 一定是 1 不会出问题
    len_limit = 100 if require_each else gallery_config.random_image_limit
    if count > len_limit:
        return await MessageBuilder().text(f"单次查看图片数量不能超过 {len_limit} 张").reply_to(event).send(matcher)

    if need_all:
        images = get_all_image(gallery, tags=filters.tags, comment=filters.comment)
        return await show_all(event, images, matcher)

    if offset is not None:
        all_images = get_all_image(gallery, tags=filters.tags, comment=filters.comment)
        if offset_startswith is not None:
            if offset >= 0:
                idx = next((i for i, img in enumerate(all_images) if img.id >= offset_startswith), len(all_images))
                target_pool = all_images[idx:]
            else:
                idx = next((i for i in range(len(all_images) - 1, -1, -1) if all_images[i].id <= offset_startswith), -1)
                target_pool = all_images[:idx + 1]
        else:
            target_pool = all_images
        if abs(offset) > len(target_pool):
            return await MessageBuilder().text(f"偏移量越界！当前范围只有 {len(target_pool)} 张").reply_to(event).send(
                matcher)
        images = target_pool[offset: offset + count] if offset >= 0 else target_pool[offset - count: offset]
    else:
        images = get_random_image(gallery, tags=filters.tags, comment=filters.comment, count=count)
    if len(images) == 0:
        return await MessageBuilder().text(f"画廊 {filters.gallery} 中找不到符合条件的图片").reply_to(event).send(
            matcher)

    builder = MessageBuilder().reply_to(event)
    for warning in warnings:
        builder.text(f"警告：{warning}。")
    if len(unknown_args) > 0:
        builder.text(f"未知参数：{' '.join(unknown_args)}。")
        builder.text("tips：本命令可选位置参数为图片数量，按备注筛选请使用如\" -- comment\"")
    if with_details:
        if len(images) > 1:
            builder.text("多张图片不支持查看详情。")
        else:
            image = images[0]
            push_details(builder, image)
    if require_each:
        parent = ForwardMessageBuilder()
        if len(builder.message) > 0:
            parent.node(builder)
        for image in images:
            builder = MessageBuilder()
            builder.image(image, is_raw=is_raw)
            parent.node(builder)
        return await parent.send(matcher)
    for image in images:
        builder.image(image, is_raw=is_raw)
    return await builder.send(matcher)


async def show_image(event: MessageEvent, params: str, matcher: Matcher):
    ids = params.split(" ")
    require_details = "--details" in ids
    if require_details:
        ids.remove("--details")
    require_each = "--each" in ids
    if require_each:
        ids.remove("--each")
    is_raw = "--raw" in ids
    if is_raw:
        ids.remove("--raw")
    ids = [id_str for id_str in ids if id_str.strip() != ""]
    images = []
    message_builder = MessageBuilder().reply_to(event)
    undefined_ids = []
    for id_str in ids:
        lst = parse_single_image_str(id_str)
        if len(lst) == 0:
            undefined_ids.append(id_str)
        else:
            for i in lst:
                image = gallery_manager.get_image_by_id(int(i))
                if image:
                    images.append(image)
                else:
                    undefined_ids.append(id_str)

    len_limit = 100 if require_each else gallery_config.random_image_limit
    if len(images) > len_limit:
        message_builder.text(f"单次查看图片数量不能超过 {len_limit} 张")
        return await message_builder.send(matcher)
    if require_details:
        if len(images) > 1:
            message_builder.text("警告：多张图片不支持查看详情。")
        if len(images) == 1:
            image = images[0]
            push_details(message_builder, image)
    if len(undefined_ids) > 0:
        message_builder.text(f"未找到图片ID：{', '.join(undefined_ids)}。")
    if require_each:
        parent = ForwardMessageBuilder()
        if len(message_builder.message) > 0:
            parent.node(message_builder)
        for image in images:
            builder = MessageBuilder()
            builder.image(image, is_raw=is_raw)
            parent.node(builder)
        return await parent.send(matcher)
    for image in images:
        message_builder.image(image, is_raw=is_raw)
    return await message_builder.send(matcher)


async def show_all(event: MessageEvent, images: list[ImageMeta], matcher: Matcher):
    images = [(i, i.get_thumb_image()) for i in images]

    message_builder = MessageBuilder().reply_to(event)
    with Canvas(bg=FillBg((230, 240, 255, 255))).set_padding(8) as canvas:
        with Grid(row_count=int(math.sqrt(len(images))), hsep=4, vsep=4):
            for image in images:
                with VSplit().set_padding(0).set_sep(2).set_content_align('c').set_item_align('c'):
                    if image[1]:
                        ImageBox(image=image[1], size=gallery_config.thumbnail_size,
                                 image_size_mode='fit').set_content_align('c')
                    else:
                        Spacer(w=gallery_config.thumbnail_size[0], h=gallery_config.thumbnail_size[1])
                    TextBox(f"id: {image[0].id}", TextStyle(DEFAULT_FONT, 12, BLACK))
    canvas_image = await canvas.get_img()
    file = io.BytesIO()
    canvas_image.save(file, format="PNG")
    message_builder.image(file)
    return await message_builder.send(matcher)


async def modify_image(event: MessageEvent, params: str, matcher: Matcher, bot: Bot):
    warnings = set()
    if "＃" in params:
        params = params.replace("＃", "#")
        warnings.add("检测到全角井号＃，已自动替换为半角#")
    args = ArgParser(params)
    image_id_str = args.peek()
    images = []
    if image_id_str:
        image_ids = parse_single_image_str(image_id_str)
        image_ids = [s.strip() for s in image_ids if s.strip().isdigit()]
        if image_ids:
            args.pop()
        for image_id_s in image_ids:
            image_id = int(image_id_s)
            image = gallery_manager.get_image_by_id(image_id)
            images.append(image)
    else:
        image_id_str = None
    images.extend(await find_gallery_images_by_event(event, bot))
    images: List[ImageMeta] = [i for i in images if i is not None]
    if not images:
        if image_id_str:
            return await MessageBuilder().text(f"没有找到图片ID {image_id_str}").reply_to(event).send(matcher)
        else:
            return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)

    comment: Optional[str] = None

    unknown_args = []
    proc_tag = []

    while current := args.peek():
        if current == "--tag":
            args.pop()
            tag = args.pop()
            if tag.startswith("+") or tag.startswith("-"):
                proc_tag.append(tag)
            else:
                unknown_args.append(current)
                unknown_args.append(tag)
        elif current == "--tags":
            args.pop()
            tag_str = args.pop()
            if tag_str and not tag_str.startswith("--"):
                for tag in re.split(r"[，,;]+", tag_str):
                    if tag.startswith("+") or tag.startswith("-"):
                        proc_tag.append(tag)
                    else:
                        unknown_args.append(tag)
            else:
                unknown_args.append(current)
                unknown_args.append(tag_str)
        elif current.startswith("+#"):
            tag = args.pop()[2:]
            proc_tag.append("+" + tag)
        elif current.startswith("-#"):
            tag = args.pop()[2:]
            proc_tag.append("-" + tag)
        elif current == "--":
            args.pop()
            comment = args.pop_all()
            if comment.startswith("-"):
                warnings.add("备注不能以 - 开头")
                unknown_args.append(current)
                unknown_args.append(comment)
                comment = None
            break
        else:
            unknown_args.append(args.pop())

    tags_list: List[List[str]] = []

    for image in images:
        tags = image.tags.copy()
        for tag_op in proc_tag:
            if tag_op.startswith("+"):
                tag = tag_op[1:]
                check_result = check_tag(tag)
                if not check_result[0]:
                    unknown_args.append(tag_op)
                    warnings.add(check_result[1])
                    continue
                if tag not in tags:
                    tags.append(tag)
            elif tag_op.startswith("-"):
                tag = tag_op[1:]
                if tag in tags:
                    tags.remove(tag)
        tags_list.append(tags)

    message_builder = MessageBuilder().reply_to(event)
    for warning in warnings:
        message_builder.text(f"警告：{warning}。")
    if len(unknown_args) > 0:
        message_builder.text(f"未知参数：{' '.join(unknown_args)}。")
        message_builder.text("tips：本命令无位置参数，备注请使用如\" -- comment\"，标签请使用 +#tag 或 -#tag")
        return await message_builder.send(matcher)

    if comment == "":
        stop = False
        for image in images:
            if image.gallery.require_comment:
                MessageBuilder().text(f"画廊 {image.gallery.name} 需要添加备注，请使用 -- 内容 添加备注")
                stop = True
        if stop:
            return await message_builder.send(matcher)

    for image, tags in zip(images, tags_list):
        modified = False
        if set(image.tags) != set(tags):
            message_builder.text(f"已修改图片ID {image.id}：")
            modified = True
            image.update_tags(list(set(tags)))
            message_builder.text(f"tag 为 {', '.join(image.tags)}")
        if comment is not None and image.comment != comment:
            if not modified:
                message_builder.text(f"已修改图片ID {image.id}：")
                modified = True
            message_builder.text(f"comment 由 \"{image.comment}\" 修改为 \"{comment}\"")
            image.update_comment(comment)
        if not modified:
            message_builder.text(f"图片ID {image.id} 未做任何修改。")
    if len(message_builder.message) > 10:
        return await ForwardMessageBuilder().node(message_builder).send(matcher)
    return await message_builder.send(matcher)


async def show_details(event: MessageEvent, params: str, matcher: Matcher, bot: Bot):
    arg = ArgParser(params)
    image_id_str = arg.peek()
    image = await find_gallery_image_by_arg_or_event(arg, event, bot)
    if not image:
        if image_id_str:
            return await MessageBuilder().text(f"没有找到图片ID {image_id_str}").reply_to(event).send(matcher)
        else:
            return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)

    message_builder = MessageBuilder().reply_to(event)
    push_details(message_builder, image)
    message_builder.image(image)
    return await message_builder.send(matcher)


async def set_alias(event: MessageEvent, params: str, matcher: Matcher):
    warnings = set()
    if "＃" in params:
        params = params.replace("＃", "#")
        warnings.add("检测到全角井号＃，已自动替换为半角#")
    args = ArgParser(params)
    alias = args.pop()
    if alias is None:
        return await reply_help(event, matcher)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)

    unknown_args = []
    tags = []
    comment: str | None = None
    while current := args.peek():
        if current == "--tag":
            args.pop()
            tag = args.pop()
            if tag and not tag.startswith("-"):
                tags.append(tag)
                continue
            else:
                unknown_args.append(current)
                unknown_args.append(tag)
        elif current == "--tags":
            args.pop()
            tag_str = args.pop()
            if tag_str and not tag_str.startswith("-"):
                tags.extend(re.split(r"[，,;]+", tag_str))
                continue
            else:
                unknown_args.append(current)
                unknown_args.append(tag_str)
        elif current == "--":
            args.pop()
            comment = args.pop_all()
            break
        elif current.startswith("#"):
            tag = args.pop()[1:]
            if tag.strip() != "":
                tags.append(tag)
                continue
        else:
            unknown_args.append(args.pop())

    comment = comment.strip() if comment else None

    if len(unknown_args) > 0:
        message_builder = MessageBuilder().reply_to(event)
        message_builder.text(f"未知参数：{' '.join(unknown_args)}。")
        for warning in warnings:
            message_builder.text(f"警告：{warning}。")
        return await message_builder.send(matcher)

    message_builder = MessageBuilder().reply_to(event)

    if len(warnings) > 0:
        for warning in warnings:
            message_builder.text(f"警告：{warning}。")

    filters = GalleryFilter(gallery=gallery_name, tags=tags, comment=comment)
    gallery_manager.set_filters(alias, filters)

    message_builder.text(f"已设置别名 {alias} 对应")
    if gallery_name != "*":
        message_builder.text(f"画廊 {gallery_name}")
    if len(tags) > 0:
        message_builder.text(f"标签 {', '.join(tags)}")
    if comment:
        message_builder.text(f"备注 {comment}")
    return await message_builder.send(matcher)


async def list_aliases(event: MessageEvent, _params: str, matcher: Matcher):
    aliases = gallery_manager.list_filters()
    if len(aliases) == 0:
        return await MessageBuilder().text("当前没有任何别名").reply_to(event).send(matcher)
    message_builder = MessageBuilder().reply_to(event)
    message_builder.text(f"当前别名列表({len(aliases)})：")
    for name, filters in aliases.items():
        text = f"- {name} -> "
        if filters.gallery != "*":
            text += f"画廊: {filters.gallery} "
        if len(filters.tags) > 0:
            text += f"标签: {', '.join(filters.tags)} "
        if filters.comment:
            text += f"备注: {filters.comment}"
        message_builder.text(text)
    return await ForwardMessageBuilder().node(message_builder).send(matcher)


async def remove_alias(event: MessageEvent, params: str, matcher: Matcher):
    alias = params.strip()
    if alias == "":
        return await reply_help(event, matcher)
    if not gallery_manager.check_filter_exists(alias):
        return await MessageBuilder().text(f"没有找到别名 {alias}").reply_to(event).send(matcher)
    gallery_manager.remove_filters(alias)
    return await MessageBuilder().text(f"已删除别名 {alias}").reply_to(event).send(matcher)


if gallery_config.enable_whateat:
    whateat_command = on_message(
        rule=startswith("吃什么"),
        priority=8
    )
    whatdrink_command = on_message(
        rule=startswith("喝什么"),
        priority=8
    )
    whatafternoon_command = on_message(
        rule=startswith(
            (
                "下午茶吃什么",
                "吃什么下午茶",
                "吃什么小蛋糕",
                "墨菲时间到"
            )
        ),
        priority=8
    )


    @whateat_command.handle()
    async def _(event: MessageEvent):
        try:
            text = str(event.get_message()).strip()[3:].strip()
            await what_eat(event, text, whateat_command, "eat")
        except Exception as e:
            await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(whateat_command)
            raise e


    @whatdrink_command.handle()
    async def _(event: MessageEvent):
        try:
            text = str(event.get_message()).strip()[3:].strip()
            await what_eat(event, text, whatdrink_command, "drink")
        except Exception as e:
            await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(whatdrink_command)
            raise e


    @whatafternoon_command.handle()
    async def _(event: MessageEvent):
        try:
            text = str(event.get_message()).strip()
            if text.startswith("下午茶吃什么"):
                text = text[6:].strip()
            elif text.startswith("吃什么下午茶"):
                text = text[6:].strip()
            elif text.startswith("吃什么小蛋糕"):
                text = text[6:].strip()
            elif text.startswith("墨菲时间到"):
                text = text[5:].strip()
            await what_eat(event, text, whatafternoon_command, "afternoon")
        except Exception as e:
            await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(whatafternoon_command)
            raise e


    async def what_eat(event: MessageEvent, params: str, matcher: Matcher | type['Matcher'], command_type: str):
        if not params in ["", ".", ",", "。", "，", "？", "?", "!", "！"]:
            return None
        if command_type == "eat":
            gallery_name = "吃什么"
            action = "吃"
        elif command_type == "drink":
            gallery_name = "喝什么"
            action = "喝"
        elif command_type == "afternoon":
            gallery_name = "下午茶"
            action = "吃"
        else:
            return None
        gallery = gallery_manager.find_gallery(gallery_name)
        if not gallery:
            return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)
        images = get_random_image(gallery, count=1)
        if not images:
            return await MessageBuilder().text(f"画廊 {gallery_name} 中没有图片").reply_to(event).send(matcher)
        image = images[0]
        builder = MessageBuilder().reply_to(event)
        builder.text(f"🎉{gallery_config.bot_name}建议你{action}🎉")
        builder.text(image.comment)
        builder.image(image)
        return await builder.send(matcher)


def push_details(builder: MessageBuilder, image: ImageMeta):
    builder.text(f"图片ID: {image.id}")
    builder.text(f"所属画廊: {' '.join(image.gallery.name)}")
    builder.text(f"标签: {', '.join(image.tags)}")
    builder.text(f"备注: {image.comment}")
    builder.text(f"上传者ID: {image.uploader}")
    builder.text(f"添加时间: {image.create_time}")


def check_tag(tag: str) -> Tuple[bool, str | None]:
    if tag.strip() == "":
        return False, "标签不能为空"
    if tag.startswith("-"):
        return False, "标签不能以 - 开头"
    return True, None


async def find_gallery_image_by_arg_or_event(arg_parser: ArgParser, event: MessageEvent, bot: Bot) -> ImageMeta | None:
    image: ImageMeta | None
    image_id_str = arg_parser.peek()
    if image_id_str is None or not image_id_str.isdigit():
        image = await find_gallery_image_by_event(event, bot)
    else:
        arg_parser.pop()
        image_id = int(image_id_str)
        image = gallery_manager.get_image_by_id(image_id)
    return image


def parse_single_image_str(image_id_str: str) -> list[str]:
    image_ids = []
    if not image_id_str.strip():
        return image_ids
    if '-' in image_id_str:
        parts = image_id_str.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            start_id = int(parts[0])
            end_id = int(parts[1])
            if start_id > end_id:
                start_id, end_id = end_id, start_id
            image_ids.extend([str(i) for i in range(start_id, end_id + 1)])
        else:
            image_ids.append(image_id_str)
    else:
        image_ids.append(image_id_str)
    return image_ids


async def find_gallery_images_by_arg_or_event(arg_parser: ArgParser, event: MessageEvent, bot: Bot) -> list[
    tuple[str, ImageMeta]]:
    image_ids = arg_parser.pop_all().split(" ")
    image_ids_copy: list[str] = image_ids
    image_ids = []
    for image_id_str in image_ids_copy:
        image_ids.extend(parse_single_image_str(image_id_str))

    images = [(image_id, gallery_manager.get_image_by_id(image_id)) for image_id in image_ids]
    images.extend([("", image) for image in await find_gallery_images_by_event(event, bot)])
    return images


async def find_gallery_image(image: tuple[str, str | None], bot: Bot) -> ImageMeta | None:
    # search by file_id
    if image[1]:
        found_images = gallery_manager.get_images_by_file_id(image[1])
        if len(found_images) > 0:
            return found_images[0]

    # search by image content
    image_file = (await download_images([image], bot))[0]
    for gallery in gallery_manager.galleries:
        sames = gallery.find_same_image(image_file.local_path)
        if sames and len(sames) > 0:
            return sames[0]
    return None


async def find_gallery_image_by_event(event: MessageEvent, bot: Bot) -> ImageMeta | None:
    images = await get_images_from_context(event, bot)

    return await find_gallery_image(images[0], bot) if len(images) > 0 else None


async def find_gallery_images_by_event(event: MessageEvent, bot: Bot) -> list[ImageMeta]:
    images = await get_images_from_context(event, bot)
    found_images = []
    for image in images:
        img = await find_gallery_image(image, bot)
        if img:
            found_images.append(img)
    return found_images


def check_name(name: str) -> bool:
    return not (name.startswith("-") or name.startswith("#") or name.startswith("＃") or name.strip() == "")
