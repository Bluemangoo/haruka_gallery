import sys
from pathlib import Path

from .gallery import gallery_manager

arg_offset = 1 if sys.argv[0].endswith('python.exe') or sys.argv[0].endswith('python3.exe') or sys.argv[0].endswith(
    'python') else 0

gallery_name = sys.argv[arg_offset + 2]
gallery = gallery_manager.find_gallery(gallery_name)
if gallery is None:
    raise ValueError(f'Gallery {gallery_name} not found.')
path = Path(sys.argv[arg_offset + 3])
if not path.exists() or not path.is_dir():
    raise FileNotFoundError(f'Dir {path} does not exist.')
with_comment = '--comment' in sys.argv

for ext in ['*.gif', '*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.webp']:
    for p in path.rglob(ext):
        if gallery.find_same_image(p):
            print("跳过相似的图片:", p)
            continue
        comment = p.stem if with_comment else ""
        gallery.add_image_unchecked(p, comment, [], "console")
        if with_comment:
            print("已添加图片及评论:", p.name)
        else:
            print("已添加图片:", p.name)
