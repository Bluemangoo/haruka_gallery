import re

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.internal.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.rule import startswith

from .gallery import gallery_manager, Gallery, ImageMeta, get_random_image
from .plot import *
from .utils import get_images_from_context, download_images, CachedFile, file_cache, ArgParser
from .message_builder import MessageBuilder, ForwardMessageBuilder

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
        if subcommand == "list-gallery" or subcommand == "list-galleries" or subcommand == "列出画廊":
            return await list_galleries(event, params, gall_command)
        if subcommand == "clear" or subcommand == "清空画廊":
            return await clear_gallery(event, params, gall_command)
        return await reply_help(event, gall_command)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(gall_command)
        raise e


@kan_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await random_image(event, text, kan_command)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(kan_command)
        raise e


@shangchuan_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await add_image(event, text, shangchuan_command)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(shangchuan_command)
        raise e


@upload_command.handle()
async def _(event: MessageEvent, args=CommandArg()):
    try:
        text: str = args.extract_plain_text().strip()
        await add_image(event, text, upload_command)
    except Exception as e:
        await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(upload_command)
        raise e


async def reply_help(_event: MessageEvent, matcher: type[Matcher]):
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
    return await ForwardMessageBuilder().node(MessageBuilder().text(help_text)).send(matcher)


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


async def list_galleries(event: MessageEvent, _param: str, matcher: type[Matcher]):
    galleries = gallery_manager.galleries
    if len(galleries) == 0:
        return await MessageBuilder().text("当前没有任何画廊").reply_to(event).send(matcher)
    message_builder = MessageBuilder()
    message_builder.text(f"当前画廊列表({len(galleries)})：")
    for gallery in galleries:
        message_builder.text(f"- {' / '.join(gallery.name)} (图片数量: {gallery.count_images()})")
    return await ForwardMessageBuilder().node(message_builder).send(matcher)


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

    tags = []
    unknown_args = []
    comment = ""
    warnings = set()
    while current := args.peek():
        if current == "--tag":
            args.pop()
            tag = args.pop()
            check_result = check_tag(tag)
            if check_result[0]:
                tags.append(tag)
                continue
            else:
                unknown_args.append(current)
                unknown_args.append(tag)
                warnings.add(check_result[1])
        elif current == "--tags":
            args.pop()
            tag_str = args.pop()
            if tag_str:
                tags = re.split(r"[，,;]+", tag_str)
                for tag in tags:
                    check_result = check_tag(tag)
                    if not check_result[0]:
                        unknown_args.append(current)
                        unknown_args.append(tag)
                        warnings.add(check_result[1])
                        continue
                tags.extend(tags)
                continue
            else:
                unknown_args.append(current)
                unknown_args.append(tag_str)
                warnings.add("标签不能为空")
        elif current == "--":
            args.pop()
            comment = args.pop_all()
            if comment.startswith("-"):
                warnings.add("备注不能以 - 开头")
                unknown_args.append(current)
                unknown_args.append(comment)
                comment = ""
            break
        elif current.startswith("#"):
            tag = args.pop()[1:]
            check_result = check_tag(tag)
            if check_result[0]:
                tags.append(tag)
            else:
                unknown_args.append(current)
                warnings.add(check_result[1])
        else:
            if current.startswith("-"):
                unknown_args.append(current)
                warnings.add("备注不能以 - 开头")
                continue
            if comment != "":
                unknown_args.append(comment)
            comment = args.pop()

    if gallery.require_comment:
        if comment == "":
            return await MessageBuilder().text(
                f"画廊 {gallery_name} 需要添加备注，请使用 -- 备注 内容添加备注").reply_to(
                event).send(matcher)

    message_builder = MessageBuilder().reply_to(event)
    message_builder.texts([f"警告：{warning}。" for warning in warnings])
    if len(unknown_args) > 0:
        message_builder.text(f"未知参数：{' '.join(unknown_args)}。")
        return await message_builder.send(matcher)

    images = await get_images_from_context(event)
    if len(images) == 0:
        return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)
    image_files = await download_images(images)
    all_image_files = [img for img in image_files]

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

    if len(all_image_files) > 0:
        message_builder.text(f"成功添加 {len(image_files)}/{len(all_image_files)} 张图片到画廊 {gallery_name}。")
    if len(image_files) == 1:
        message_builder.text(f"新图片ID：{image_obj.id}。")
    if len(tags) > 0:
        message_builder.text(f"添加的图片附加标签：{', '.join(tags)}。")
    if comment != "":
        message_builder.text(f"添加的图片附加备注：{comment}。")
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
    args = ArgParser(params)
    images = await find_gallery_images_by_arg_or_event(args, event)
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


async def move_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    args = ArgParser(params)
    message_builder = MessageBuilder().reply_to(event)
    target_gallery_name = args.pop()
    gallery = gallery_manager.find_gallery(target_gallery_name)
    if not gallery:
        return await message_builder.text(f"没有找到画廊 {target_gallery_name}").send(matcher)
    images = await find_gallery_images_by_arg_or_event(args, event)
    if len(images) == 0:
        return await message_builder.text(f"没有找到图片").send(matcher)
    for image_id, image in images:
        if image:
            image.move_to(gallery)
            message_builder.text(f"已将图片 {image_id} 移动到画廊 {target_gallery_name}。")
        else:
            message_builder.text(f"没有找到图片 {image_id}。")
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
    with_details = False
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
        elif current == "--details":
            args.pop()
            with_details = True
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

    if count > gallery_config.random_image_limit:
        return await MessageBuilder().text(f"单次查看图片数量不能超过 {gallery_config.random_image_limit} 张").reply_to(
            event).send(matcher)

    images = get_random_image(gallery, tags=tags, comment=comment, count=count)
    if len(images) == 0:
        return await MessageBuilder().text(f"画廊 {gallery_name} 中没有图片").reply_to(event).send(matcher)

    builder = MessageBuilder().reply_to(event)
    if len(unknown_args) > 0:
        builder.text(f"未知参数：{' '.join(unknown_args)}。")
    if with_details:
        if len(images) > 1:
            builder.text("多张图片不支持查看详情。")
        else:
            image = images[0]
            push_details(builder, image)
    for image in images:
        builder.image(image)
    return await builder.send(matcher)


async def show_image(event: MessageEvent, params: str, matcher: type[Matcher]):
    ids = params.split(" ")
    require_details = "--details" in ids
    if require_details:
        ids.remove("--details")
    ids = [id_str for id_str in ids if id_str.strip() != ""]
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
    if require_details:
        if len(images) > 1:
            message_builder.text("警告：多张图片不支持查看详情。")
        if len(images) == 1:
            image = images[0]
            push_details(message_builder, image)
    if len(undefined_ids) > 0:
        message_builder.text(f"未找到图片ID：{', '.join(undefined_ids)}。")
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
    image_id_str = args.peek()
    images = []
    if image_id_str and image_id_str.isdigit():
        image_id = int(args.pop())
        image = gallery_manager.get_image_by_id(image_id)
        images.append(image)
    else:
        image_id_str = None
    images.extend(await find_gallery_images_by_event(event))
    print(images)
    images: List[ImageMeta] = [i for i in images if i is not None]
    if not images:
        if image_id_str:
            return await MessageBuilder().text(f"没有找到图片ID {image_id_str}").reply_to(event).send(matcher)
        else:
            return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)

    comment: Optional[str] = None

    unknown_args = []
    warnings = set()
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


async def show_details(event: MessageEvent, params: str, matcher: type[Matcher]):
    arg = ArgParser(params)
    image_id_str = arg.peek()
    image = await find_gallery_image_by_arg_or_event(arg, event)
    if not image:
        if image_id_str:
            return await MessageBuilder().text(f"没有找到图片ID {image_id_str}").reply_to(event).send(matcher)
        else:
            return await MessageBuilder().text(f"没有找到图片").reply_to(event).send(matcher)

    message_builder = MessageBuilder().reply_to(event)
    push_details(message_builder, image)
    message_builder.image(image)
    return await message_builder.send(matcher)


if gallery_config.enable_whateat:
    whateat_command = on_message(
        rule=startswith("吃什么"),
        priority=8
    )
    whatdrink_command = on_message(
        rule=startswith("喝什么"),
        priority=8
    )


    @whateat_command.handle()
    async def _(event: MessageEvent):
        try:
            text = str(event.get_message()).strip()[3:].strip()
            await what_eat(event, text, whateat_command, True)
        except Exception as e:
            await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(whateat_command)
            raise e


    @whatdrink_command.handle()
    async def _(event: MessageEvent):
        try:
            text = str(event.get_message()).strip()[3:].strip()
            await what_eat(event, text, whatdrink_command, False)
        except Exception as e:
            await MessageBuilder().text(f"命令执行出错：{str(e)}").reply_to(event).send(whatdrink_command)
            raise e


    async def what_eat(event: MessageEvent, params: str, matcher: type[Matcher], eat_or_drint: bool = True):
        if not params in ["", ".", ",", "。", "，", "？", "?"]:
            return None
        gallery_name = "吃什么" if eat_or_drint else "喝什么"
        gallery = gallery_manager.find_gallery(gallery_name)
        if not gallery:
            return await MessageBuilder().text(f"没有找到画廊 {gallery_name}").reply_to(event).send(matcher)
        images = get_random_image(gallery, count=1)
        if not images:
            return await MessageBuilder().text(f"画廊 {gallery_name} 中没有图片").reply_to(event).send(matcher)
        image = images[0]
        builder = MessageBuilder().reply_to(event)
        builder.text(f"🎉{gallery_config.bot_name}建议你{'吃' if eat_or_drint else '喝'}🎉")
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


async def find_gallery_image_by_arg_or_event(arg_parser: ArgParser, event: MessageEvent) -> ImageMeta | None:
    image: ImageMeta | None
    image_id_str = arg_parser.peek()
    if image_id_str is None or not image_id_str.isdigit():
        image = await find_gallery_image_by_event(event)
    else:
        arg_parser.pop()
        image_id = int(image_id_str)
        image = gallery_manager.get_image_by_id(image_id)
    return image


async def find_gallery_images_by_arg_or_event(arg_parser: ArgParser, event: MessageEvent) -> list[
    tuple[str, ImageMeta]]:
    image_ids = arg_parser.pop_all().split(" ")
    image_ids = [i for i in image_ids if i.strip()]
    images = [(image_id, gallery_manager.get_image_by_id(image_id)) for image_id in image_ids]
    images.extend([("", image) for image in await find_gallery_images_by_event(event)])
    return images


async def find_gallery_image(image: tuple[str, str | None]) -> ImageMeta | None:
    # search by file_id
    if image[1]:
        found_images = gallery_manager.get_images_by_file_id(image[1])
        if len(found_images) > 0:
            return found_images[0]

    # search by image content
    image_file = (await download_images([image]))[0]
    for gallery in gallery_manager.galleries:
        sames = gallery.find_same_image(image_file.local_path)
        if sames and len(sames) > 0:
            return sames[0]
    return None


async def find_gallery_image_by_event(event: MessageEvent) -> ImageMeta | None:
    images = await get_images_from_context(event)

    return await find_gallery_image(images[0]) if len(images) > 0 else None


async def find_gallery_images_by_event(event: MessageEvent) -> list[ImageMeta]:
    images = await get_images_from_context(event)
    found_images = []
    for image in images:
        img = await find_gallery_image(image)
        if img:
            found_images.append(img)
    return found_images
