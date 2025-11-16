# Haruka Gallery

A Nonebot Plugin Rewrite From [lunabot/gallery](https://github.com/NeuraXmy/lunabot/tree/master/src/plugins/gallery)

## Config

```env
size_limit_mb=10
thumbnail_size=[64, 64]
repeat_image_show_size=[128, 128]
canvas_limit_size=[4096, 4096]
random_image_limit=10
enable_whateat=false
```

## Requirements

When developing:

```shell
uv sync
```

When deploying:

```shell
pip install -r requirements.txt
```

## Commands

- "/gall"
- "/gallery"
- "/画廊"

直接发命令不带参数会触发帮助信息

当 enable_whateat 启用时：

- "吃什么"
- "喝什么"

这两个连接到了叫 "吃什么" 和 "喝什么" 的特殊画廊。

你可以去 [nonebot-plugin-whateat-pic](https://github.com/Cvandia/nonebot-plugin-whateat-pic/tree/main/res)
或者 [whattoeat](https://github.com/A-kirami/whattoeat/tree/master/foods) 那里找点图片来先用用。

## Deployment

记得在 `data/utils/fonts/` 底下装思源黑体，如 `SourceHanSansCN-Bold.otf` （需要多个变种）

## Manual Import

手动导入请运行 `import_from_file.py`，参数：

```shell
python import_from_file.py <proj_root> <gallery_name> <file_dir> [--comment]
```

- `proj_root`：项目根目录
- `gallery_name`：画廊名称
- `file_dir`：文件夹路径
- `--comment`：是否将文件名作为备注
