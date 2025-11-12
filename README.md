# Haruka Gallery

A Nonebot Plugin Rewrite From [lunabot/gallery](https://github.com/NeuraXmy/lunabot/tree/master/src/plugins/gallery)

## Config

```env
size_limit_mb=10
thumbnail_size=[64, 64]
repeat_image_show_size=[128, 128]
canvas_limit_size=[4096, 4096]
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

## Deployment

记得在 `data/utils/fonts/` 底下装思源黑体，如 `SourceHanSansCN-Bold.otf` （需要多个变种）
