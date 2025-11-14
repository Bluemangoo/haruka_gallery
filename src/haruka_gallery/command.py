import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.internal.matcher import Matcher
from nonebot.params import CommandArg

from .gallery import gallery_manager, Gallery, ImageMeta, get_random_image
from .plot import *
from .utils import get_images_from_context, download_images, CachedFile, file_cache, ArgParser
from .message_builder import MessageBuilder

gall_command = on_command("gallery", aliases={"画廊", "gall"}, force_whitespace=True, priority=5)
kan_command = on_command("看", priority=8)
shangchuan_command = on_command("上传", priority=8)
upload_command = on_command("upload", force_whitespace=True, priority=5)


@gall_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        subcommand, *params = text.split(" ", 1)
        params = params[0] if params else ""
        if subcommand == "add" or subcommand == "upload" or subcommand == "添加" or subcommand == "上传":
            return await add_image(event, params, gall_command)
        if subcommand == "remove" or subcommand == "删除":
            return await remove_image(event, params, gall_command)
        if subcommand == "modify" or subcommand == "修改":
            return await modify_image(event, params, gall_command)
        if subcommand == "move" or subcommand == "移动":
            return await move_image(event, params, gall_command)
        if subcommand == "show" or subcommand == "查看" or subcommand == "看":
            return await random_image(event, params, gall_command)
        if subcommand == "show-all" or subcommand == "查看全部" or subcommand == "看全部" or subcommand == "查看所有" or subcommand == "看所有":
            return await show_all(event, params, gall_command)
        if subcommand == "details" or subcommand == "详情":
            return await show_details(event, params, gall_command)
        if subcommand == "add-gallery" or subcommand == "创建画廊":
            return await add_gallery(event, params, gall_command)
        if subcommand == "modify-gallery" or subcommand == "修改画廊":
            return await modify_gallery(event, params, gall_command)
        if subcommand == "remove-gallery" or subcommand == "删除画廊":
            return await remove_gallery(event, params, gall_command)
        if subcommand == "clear" or subcommand == "清空画廊":
            return await clear_gallery(event, params, gall_command)
        return await reply_help(event, gall_command)
    except Exception as e:
        return await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(gall_command)


@kan_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await random_image(event, text, kan_command)
    except Exception as e:
        return await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(kan_command)


@shangchuan_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await add_image(event, text, shangchuan_command)
    except Exception as e:
        return await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(shangchuan_command)


@upload_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await add_image(event, text, upload_command)
    except Exception as e:
        return await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(upload_command)


async def reply_help(event: MessageEvent, matcher: type[Matcher]):
    help_text = (
        "画廊命令帮助 (/gall /gallery /画廊)：\n"
        "/gall {add-gallery | 创建画廊} <画廊名称> - 创建一个新的画廊，提供多个名称则作为别名\n"
        "/gall {modify-gallery | 修改画廊} <画 廊名称> [+别名] [-别名] - 修改画廊名称，使用 + 添加别名，- 删除别名\n"
        # "/gall {remove-gallery | 删除画廊} <画廊名称> - 删除指定名称的画廊\n"
        # "/gall {clear | 清空画廊} <画廊名称> - 清空指定画廊中的所有图片\n"
        "/gall {add | upload | 添加 | 上传} [force | 强制] [skip | 跳过] [gallery] <图片链接或回复图片> - 添加图片到画廊，使用 force 参数可强制添加重复图片\n"
        "/gall {modify | 修改} <图片ID> [+#标签 | -#标签 | --tag +标签1 | --tags +标签1,-标签2] [-- 备注] - 修改图片的标签和备注\n"
        "/gall {move | 移动} <目标画廊名称> <图片ID1> <图片ID2> ... - 将指定ID的图片移动到目标画廊\n"
        "/gall {remove | 删除} <图片ID> - 从画廊中删除指定ID的图片\n"
        "/gall {show | 查看 | 看} {<画廊名称> | *} [筛选条件] [数量] - 随机查看画廊中的图片，*则从所有画廊，筛选条件可使用 [#标签 | --tag 标签 | --tags 标签1,标签2] [-- 备注]，数量可使用 xN 或 N 表示 (需要在备注前面)\n"
        "/gall {show | 查看 | 看} <图片ID1> <图片ID2> ... - 查看指定ID的图片\n"
        "/gall {show-all | 查看全部 | 看全部} <画廊名称> - 查看画廊中的所有图片缩略图\n"
        "/gall {details | 详情} <图片ID> - 查看指定ID图片的详细信息\n"
        "\n"
        "alias：\n"
        "/看 - /gall show\n"
        "/上传 - /gall add"
    )
    return await MessageBuilder().text(help_text).reply_to(event).send(matcher)


async def add_gallery(event: MessageEvent, params: str, matcher: type[Matcher]):
    gallery_names: list[str] = params.split(" ")
    if len(gallery_names) == 0:
        return await reply_help(event, matcher)

    exist_names = [name for name in gallery_names if gallery_manager.check_exists(name)]
    if len(exist_names) > 0:
        return await MessageBuilder().text(f"画廊 {', '.join(exist_names)} 已存在").reply_to(event).send(matcher)
    else:
        gallery_manager.add_gallery(gallery_names)
        return await MessageBuilder().text(f"成功创建画廊 {params}").reply_to(event).send(matcher)


async def clear_gallery(event: MessageEvent, params: str, matcher: type[Matcher]):
    args = ArgParser(params)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)
    for image in gallery.list_images():
        image.drop()
    return await MessageBuilder().text(f"已清空画廊 {gallery_name} 中的所有图片").reply_to(event).send(matcher)


async def modify_gallery(event: MessageEvent, params: str, matcher: type[Matcher]):
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


async def remove_gallery(event: MessageEvent, params: str, matcher: type[Matcher]):
    gallery_name = params.strip()
    if gallery_name == "":
        return await reply_help(event, matcher)
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)

    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)

    gallery.drop()
    return await MessageBuilder().text(f"已删除画廊 {gallery_name}").reply_to(event).send(matcher)


async def add_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    args = ArgParser(params)
    is_force = args.check_and_pop("force") or args.check_and_pop("强制")
    is_skip = args.check_and_pop("skip") or args.check_and_pop("跳过")
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    is_force = is_force or args.check_and_pop("force") or args.check_and_pop("强制")
    is_skip = is_skip or args.check_and_pop("skip") or args.check_and_pop("跳过")
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)

    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)

    images = await get_images_from_context(event)
    if len(images) == 0:
        return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)
    image_files = await download_images(images)
    all_image_files = [img for img in image_files]

    tags = []
    unknown_args = []
    comment = ""
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
            if comment != "":
                unknown_args.append(comment)
            comment = args.pop()

    existing_images: list[Tuple[CachedFile, list[ImageMeta]]] = []
    if not is_force:
        for image in image_files:
            sames = gallery.find_same_image(image.local_path)
            if sames and len(sames) > 0:
                existing_images.append((image, sames))

        existing_image_files = [image for image, _ in existing_images]
        image_files = [image for image in image_files if image not in existing_image_files]

    image_obj = None
    for image in image_files:
        image_obj = gallery.add_image_unchecked(image.local_path, comment, tags, str(event.user_id),
                                                file_id=image.extra.get("file_id"))

    message_builder = MessageBuilder().reply_to(event)
    if len(unknown_args) > 0:
        message_builder.text(f"未知参数：{' '.join(unknown_args)}。\n")
    if len(all_image_files) > 0:
        message_builder.text(f"成功添加 {len(image_files)}/{len(all_image_files)} 张图片到画廊 {gallery_name}。")
    if len(image_files) == 1:
        message_builder.text(f"新图片ID：{image_obj.id}。")
    if len(tags) > 0:
        message_builder.text(f"添加的图片附加标签：{', '.join(tags)}。")
    if comment != "":
        message_builder.text(f"添加的图片附加评论：{comment}。")
    if not is_skip and len(existing_images) > 0:
        message_builder.text(f"{len(existing_images)} 张图片已存在于画廊 {gallery_name}：")

        with Canvas(bg=FillBg((230, 240, 255, 255))).set_padding(8) as canvas:
            with VSplit().set_padding(0).set_sep(16).set_item_align('lt').set_content_align('lt'):
                TextBox(f"查重错误可使用\"/上传 force\"强制上传图片", TextStyle(DEFAULT_FONT, 16, BLACK))
                with Grid(row_count=int(math.sqrt(len(existing_images) * 2)), hsep=8, vsep=8).set_item_align(
                        't').set_content_align('t'):
                    for image, sames in existing_images:
                        img = Image.open(image.local_path)
                        pic = sames[0]
                        img2 = pic.get_image()
                        img2.thumbnail(gallery_config.repeat_image_show_size)
                        with HSplit().set_padding(0).set_sep(4):
                            with VSplit().set_padding(0).set_sep(4).set_content_align('c').set_item_align('c'):
                                ImageBox(image=img, size=gallery_config.repeat_image_show_size,
                                         image_size_mode='fit').set_content_align('c')
                                TextBox(f"待上传图片", TextStyle(DEFAULT_FONT, 16, BLACK))
                            with VSplit().set_padding(0).set_sep(4).set_content_align('c').set_item_align('c'):
                                if img2:
                                    ImageBox(image=img2, size=gallery_config.repeat_image_show_size,
                                             image_size_mode='fit').set_content_align('c')
                                else:
                                    Spacer(w=gallery_config.repeat_image_show_size[0],
                                           h=gallery_config.repeat_image_show_size[1])
                                TextBox(f"id: {pic.id}", TextStyle(DEFAULT_FONT, 16, BLACK))
        repeat_img = await canvas.get_img()
        file = file_cache.new_file(".png")
        repeat_img.save(file.local_path)
        message_builder.image(file.local_path)
    await message_builder.send(matcher)
    for image in all_image_files:
        image.mark_used()
    return None


async def remove_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    image_id = params.strip()
    if image_id == "":
        return await reply_help(event, matcher)
    image = gallery_manager.get_image_by_id(image_id)
    if image:
        gallery = image.gallery
        image.drop()
        return await MessageBuilder().text(f"已从画廊 {gallery.name} 中删除图片 {image_id}").reply_to(event).send(
            matcher)
    return await MessageBuilder().text(f"没有找到图片 {image_id}").reply_to(event).send(matcher)


async def move_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    args = ArgParser(params)
    target_gallery_name = args.pop()
    image_ids = args.pop_all().split(" ")
    gallery = gallery_manager.find_gallery(target_gallery_name)
    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {target_gallery_name}").reply_to(event).send(matcher)
    if len(image_ids) == 0:
        return await reply_help(event, matcher)
    message_builder = MessageBuilder().reply_to(event)
    for image_id in image_ids:
        image = gallery_manager.get_image_by_id(image_id)
        if image:
            image.move_to(gallery)
            message_builder.text(f"已将图片 {image_id} 移动到画廊 {target_gallery_name}。\n")
        else:
            message_builder.text(f"没有找到图片 {image_id}。\n")
    return await message_builder.send(matcher)


async def random_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    args = ArgParser(params)
    if args.peek(2) == "全部" or args.peek(2) == "所有":
        args.pop(2)
        return await show_all(event, args.pop_all(), matcher)
    gallery_name = args.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)

    if gallery_name.isdigit():
        return await show_image(event, params, matcher)
    unknown_args = []
    tags = []

    count = 1
    count_str = ""
    comment = None
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
            if count_str != "":
                unknown_args.append(count_str)
            count_str = args.pop()
            s = count_str

            if s.startswith("x"):
                s = s[1:]
            if not s.isdigit():
                unknown_args.append(count_str)
                count_str = ""
                continue
            count = int(s)
    gallery: Gallery | None = None
    if gallery_name != "*":
        gallery: Gallery = gallery_manager.find_gallery(gallery_name)

        if not gallery:
            return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)

    images = get_random_image(gallery, tags=tags, comment=comment, count=count)
    if len(images) == 0:
        return await MessageBuilder().text(f"画廊 {gallery_name} 中没有图片").reply_to(event).send(matcher)

    builder = MessageBuilder().reply_to(event)
    if len(unknown_args) > 0:
        builder.text(f"未知参数：{' '.join(unknown_args)}。\n")
    for image in images:
        builder.image(image)
    return await builder.send(matcher)


async def show_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    ids = params.split(" ")
    images = []
    message_builder = MessageBuilder().reply_to(event)
    undefined_ids = []
    for id_str in ids:
        if id_str.strip().isdigit():
            image_id = int(id_str)
            image = gallery_manager.get_image_by_id(image_id)
            if image:
                images.append(image)
            else:
                undefined_ids.append(id_str)
    if len(undefined_ids) > 0:
        message_builder.text(f"未找到图片ID：{', '.join(undefined_ids)}。\n")
    for image in images:
        message_builder.image(image)
    return await message_builder.send(matcher)


async def show_all(event: MessageEvent, params: str, matcher: type[Matcher]):
    arg = ArgParser(params)
    gallery_name = arg.pop()
    if gallery_name is None:
        return await reply_help(event, matcher)
    gallery: Gallery = gallery_manager.find_gallery(gallery_name)
    if not gallery:
        return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)
    images = gallery.list_images()

    message_builder = MessageBuilder().reply_to(event)
    with Canvas(bg=FillBg((230, 240, 255, 255))).set_padding(8) as canvas:
        with Grid(row_count=int(math.sqrt(len(images))), hsep=4, vsep=4):
            for image in images:
                thumb_file = image.get_thumb()
                with VSplit().set_padding(0).set_sep(2).set_content_align('c').set_item_align('c'):
                    if thumb_file:
                        ImageBox(image=Image.open(thumb_file.local_path), size=gallery_config.thumbnail_size,
                                 image_size_mode='fit').set_content_align('c')
                    else:
                        Spacer(w=gallery_config.thumbnail_size[0], h=gallery_config.thumbnail_size[1])
                    TextBox(f"id: {image.id}", TextStyle(DEFAULT_FONT, 12, BLACK))
    canvas_image = await canvas.get_img()
    file = file_cache.new_file(".png")
    canvas_image.save(file.local_path)
    message_builder.image(file.local_path)
    return await message_builder.send(matcher)


async def modify_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    args = ArgParser(params)
    image_id_str = args.pop()
    if image_id_str is None or not image_id_str.isdigit():
        return await reply_help(event, matcher)
    image_id = int(image_id_str)
    image = gallery_manager.get_image_by_id(image_id)
    if not image:
        return await MessageBuilder().text(f"没有找到图片ID {image_id}").reply_to(event).send(matcher)

    tags = image.tags.copy()
    comment = image.comment

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
            break
        else:
            unknown_args.append(args.pop())

    for tag_op in proc_tag:
        if tag_op.startswith("+"):
            tag = tag_op[1:]
            if tag not in tags:
                tags.append(tag)
        elif tag_op.startswith("-"):
            tag = tag_op[1:]
            if tag in tags:
                tags.remove(tag)

    message_builder = MessageBuilder().reply_to(event)
    if len(unknown_args) > 0:
        message_builder.text(f"未知参数：{' '.join(unknown_args)}。\n")
        return await message_builder.send(matcher)

    modified = False
    if set(image.tags) != set(tags):
        message_builder.text(f"已修改图片ID {image_id}：")
        modified = True
        image.update_tags(list(set(tags)))
        message_builder.text(f"tag 为 {', '.join(image.tags)}")
    if image.comment != comment:
        if not modified:
            message_builder.text(f"已修改图片ID {image_id}：")
            modified = True
        message_builder.text(f"comment 由 \"{image.comment}\" 修改为 \"{comment}\"")
        image.update_comment(comment)
    if not modified:
        message_builder.text(f"图片ID {image_id} 未做任何修改。")
    return await message_builder.send(matcher)


async def show_details(event: MessageEvent, params: str, matcher: type[Matcher]):
    image_id_str = params.strip()
    if image_id_str is None or not image_id_str.isdigit():
        return await reply_help(event, matcher)
    image_id = int(image_id_str)
    image = gallery_manager.get_image_by_id(image_id)
    if not image:
        return await MessageBuilder().text(f"没有找到图片ID {image_id}").reply_to(event).send(matcher)

    message_builder = MessageBuilder().reply_to(event)
    message_builder.text(f"图片ID: {image.id}")
    message_builder.text(f"所属画廊: {' '.join(image.gallery.name)}")
    message_builder.text(f"标签: {', '.join(image.tags)}")
    message_builder.text(f"备注: {image.comment}")
    message_builder.text(f"上传者ID: {image.uploader}")
    message_builder.text(f"添加时间: {image.create_time}")
    message_builder.image(image)
    return await message_builder.send(matcher)
