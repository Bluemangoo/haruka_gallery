import os
import shutil
from os import PathLike
from pathlib import Path
from typing import Optional, Tuple

import imagehash
from PIL import Image
from nonebot import logger

from .config import gallery_config
from .data import db


def find_image(image_id: int):
    cursor = db.execute("select * from images where id=?", (image_id,))
    row = cursor.fetchone()
    if row:
        return ImageMeta.from_row(row)
    return None


class GalleryManager:
    galleries: list['Gallery']

    def __init__(self):
        self.galleries = []
        self.load_galleries()

    def add_gallery(self, name: list[str]) -> Optional['Gallery']:
        for n in name:
            if self.check_exists(n):
                return None
        gallery = Gallery.new_unchecked(name)
        self.galleries.append(gallery)
        return gallery

    def check_exists(self, name: str) -> bool:
        for gallery in self.galleries:
            if name in gallery.name:
                return True
        return False

    def find_gallery(self, name: str) -> Optional['Gallery']:
        for gallery in self.galleries:
            if name in gallery.name:
                return gallery
        return None

    def get_gallery_by_id(self, gallery_id: int):
        for gallery in self.galleries:
            if gallery.id == gallery_id:
                return gallery
        return None

    @staticmethod
    def get_image_by_id(image_id: int) -> Optional['ImageMeta']:
        cursor = db.execute("select * from images where id=?", (image_id,))
        row = cursor.fetchone()
        if row:
            return ImageMeta.from_row(row)
        return None

    def load_galleries(self):
        cursor = db.execute("select * from galleries")
        rows = cursor.fetchall()
        for row in rows:
            gallery = Gallery(
                gallery_id=row[0],
                name=row[1].split(" ")
            )
            self.galleries.append(gallery)


class Gallery:
    id: int
    name: list[str]

    def __init__(self, gallery_id: int, name: list[str]):
        self.id = gallery_id
        self.name = name

    @classmethod
    def new_unchecked(cls, name: list[str]):
        cursor = db.execute("insert into galleries (name) VALUES (?)", (" ".join(name),))
        db.commit()
        cursor = db.execute("select * from galleries where id=?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return cls(
            gallery_id=row[0],
            name=name
        )

    def add_image_unchecked(self, image_path: PathLike | str, comment, tags: list[str], uploader: str,
                            file_id: Optional[str] = None) -> 'ImageMeta':
        suffix = Path(image_path).suffix
        phash = PhashWrapper.from_image_path(image_path)
        meta = ImageMeta.new_unchecked(self, comment, tags, suffix, uploader, phash, file_id=file_id)
        image_id = meta.id
        ext = Path(image_path).suffix
        dest_dir = gallery_config.data_dir / str(self.id) / (str(image_id) + ext)
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(image_path, dest_dir)

        return meta

    def list_images(self) -> list['ImageMeta']:
        cursor = db.execute("select * from images where gallery_id=?", (self.id,))
        rows = cursor.fetchall()
        images = []
        for row in rows:
            image_meta = ImageMeta.from_row(row)
            images.append(image_meta)
        return images

    def drop(self):
        images = self.list_images()
        for image in images:
            image.drop()
        db.execute("delete from galleries where id=?", (self.id,))
        db.commit()
        gallery_path = gallery_config.data_dir / str(self.id)
        if gallery_path.exists():
            shutil.rmtree(gallery_path)

    def find_same_image(self, image: PathLike | str) -> list['ImageMeta']:
        phash = PhashWrapper.from_image_path(image)
        images = self.list_images()
        return [img for img in images if img.is_same(phash)]

    def get_random_image(self, tags: Optional[list[str]] = None, comment: Optional[str] = None, count: int = 1) -> list[
        'ImageMeta']:
        if tags is None:
            tags = []
        tag_ids_res = ImageMeta.get_tags(tags)
        if len(tag_ids_res[1]) > 0:
            return []
        tag_ids = tag_ids_res[0]
        placeholders = ', '.join(['?'] * len(tag_ids))
        search_tags = f"""
            and i.id in (
                select it.image_id
                from image_tags it
                where
                    it.tag_id in ({placeholders})
                group by
                    it.image_id
                having 
                    count(distinct it.tag_id) = ?
            )
            """ if len(tag_ids) > 0 else ""
        tags_param = (tag_ids + [len(tag_ids)]) if len(tag_ids) > 0 else []
        search_comment = " and i.comment like ? " if comment is not None else ""
        comment_param = [f"%{comment}%"] if comment is not None else []
        cursor = db.execute(f"""
            select i.*
            from images i
            where
                i.gallery_id = ? {search_comment}
                {search_tags}
            order by random()
            limit ?;
            """, [self.id] + comment_param + tags_param + [count])
        rows = cursor.fetchall()
        images = []
        for row in rows:
            image_meta = ImageMeta.from_row(row)
            images.append(image_meta)
        return images

    def update_name(self):
        db.execute("update galleries set name=? where id=?", (" ".join(self.name), self.id))
        db.commit()


class PhashWrapper:
    def __init__(self, hash_obj: imagehash.ImageHash):
        if not isinstance(hash_obj, imagehash.ImageHash):
            raise ValueError("必须使用一个 imagehash.ImageHash 对象进行初始化。")
        self.phash = hash_obj

    @classmethod
    def from_image(cls, pil_image: Image.Image, hash_size: int = 8) -> 'PhashWrapper':
        hash_obj = imagehash.phash(pil_image, hash_size=hash_size)
        return cls(hash_obj=hash_obj)

    @classmethod
    def from_image_path(cls, image_path: str, hash_size: int = 8) -> 'PhashWrapper':
        try:
            img = Image.open(image_path)
            return cls.from_image(img, hash_size=hash_size)
        except FileNotFoundError:
            print(f"错误: 文件未找到 {image_path}")
            raise
        except Exception as e:
            print(f"加载图片时出错: {e}")
            raise

    def export_to_buffer(self) -> bytes:
        # 1. 将 pHash 对象转换为其标准的十六进制字符串表示
        hex_string = str(self.phash)

        # 2. 将该字符串编码为 bytes (即 "Buffer")
        return hex_string.encode('utf-8')

    @classmethod
    def from_buffer(cls, buffer: bytes) -> 'PhashWrapper':
        try:
            # 1. 将 bytes (Buffer) 解码回十六进制字符串
            restored_hex_string = buffer.decode('utf-8')

            # 2. 使用 imagehash 库的标准函数从十六进制重建 ImageHash 对象
            hash_obj = imagehash.hex_to_hash(restored_hex_string)

            return cls(hash_obj=hash_obj)
        except UnicodeDecodeError:
            print("错误: Buffer 不是有效的 UTF-8 编码。")
            raise
        except Exception as e:
            print(f"错误: 无法从十六进制字符串 '{restored_hex_string}' 创建哈希: {e}")
            raise

    def get_hex_string(self) -> str:
        return str(self.phash)

    def compare_distance(self, other: 'PhashWrapper') -> int:
        if not isinstance(other, PhashWrapper):
            raise TypeError("只能与另一个 PhashWrapper 实例进行比较。")
        return self.phash - other.phash

    def __str__(self) -> str:
        return self.get_hex_string()

    def __eq__(self, other) -> bool:
        if isinstance(other, PhashWrapper):
            return self.phash == other.phash
        return False

    def __sub__(self, other):
        if isinstance(other, PhashWrapper):
            return self.compare_distance(other)
        raise TypeError("只能与另一个 PhashWrapper 实例进行减法操作。")

    def __repr__(self) -> str:
        return f"<PhashWrapper hash='{self.phash}'>"


class ImageMeta:
    thumb_path: Optional[Path] = None
    id: int
    gallery: Gallery
    comment: str
    tags: list[str]
    suffix: str
    uploader: str
    phash: PhashWrapper
    file_id: Optional[str] = None
    create_time: int

    def __init__(self, image_id: int, gallery: Gallery, comment: str, tags: list[str], suffix: str, uploader: str,
                 phash: PhashWrapper, create_time: int, file_id: Optional[str] = None):
        self.thumb_path = None
        self.id = image_id
        self.gallery = gallery
        self.comment = comment
        self.tags = tags
        self.suffix = suffix
        self.uploader = uploader
        self.phash = phash
        self.file_id = file_id
        self.create_time = create_time

    def __repr__(self):
        return f"<ImageMeta id={self.id} gallery_id={self.gallery.id} comment='{self.comment}' tags={self.tags} " \
               f"suffix='{self.suffix}' uploader='{self.uploader}' file_id='{self.file_id}' phash='{self.phash}'>"

    @classmethod
    def new_unchecked(cls, gallery: Gallery, comment: str, tags: list[str], suffix: str, uploader: str,
                      phash: PhashWrapper, file_id: Optional[str] = None) -> 'ImageMeta':
        binary_phash = phash.export_to_buffer()
        tag_ids = ImageMeta.get_or_create_tags(tags)
        cursor = db.execute(
            "insert into images (gallery_id, comment, suffix, uploader, file_id, phash) VALUES (?,?,?,?,?,?)",
            (gallery.id, comment, suffix, uploader, file_id, binary_phash))
        db.commit()
        cursor = db.execute("select * from images where id=?", (cursor.lastrowid,))
        row = cursor.fetchone()
        image_id = row[0]
        for tag_id in tag_ids:
            db.execute("insert into image_tags (image_id, tag_id) VALUES (?,?)", (image_id, tag_id))
        db.commit()
        return ImageMeta(
            image_id=image_id,
            gallery=gallery,
            comment=comment,
            tags=tags,
            suffix=suffix,
            uploader=uploader,
            file_id=file_id,
            phash=phash,
            create_time=row[8]
        )

    @classmethod
    def from_row(cls, row) -> 'ImageMeta':
        gallery = GalleryManager().get_gallery_by_id(row[1])
        image_id = row[0]
        cursor = db.execute("select tag_id from image_tags where image_id=?", (image_id,))
        tag_rows = cursor.fetchall()
        tag_ids = [tag_row[0] for tag_row in tag_rows]
        tags = []
        for tag_id in tag_ids:
            cursor = db.execute("select name from tags where id=?", (tag_id,))
            tag_row = cursor.fetchone()
            if tag_row:
                tags.append(tag_row[0])
        phash = PhashWrapper.from_buffer(row[5])
        return cls(
            image_id=image_id,
            gallery=gallery,
            comment=row[2],
            tags=tags,
            suffix=row[3],
            uploader=row[4],
            phash=phash,
            file_id=row[6],
            create_time=row[7]
        )

    @staticmethod
    def get_tags(tags: list[str]) -> Tuple[list[int], list[str]]:
        tag_ids = []
        undefined_tags = []
        for tag in tags:
            cursor = db.execute("select id from tags where name=?", (tag,))
            result = cursor.fetchone()
            if result is None:
                undefined_tags.append(tag)
            else:
                tag_id = result[0]
                tag_ids.append(tag_id)

        return tag_ids, undefined_tags

    @staticmethod
    def get_or_create_tags(tags: list[str]) -> list[int]:
        tag_ids = []
        for tag in tags:
            result = None
            while result is None:
                cursor = db.execute("select id from tags where name=?", (tag,))
                result = cursor.fetchone()
                if result is None:
                    db.execute("insert into tags (name) VALUES (?)", (tag,))
                    db.commit()
            tag_id = result[0]
            tag_ids.append(tag_id)
        return tag_ids

    def get_file_name(self) -> str:
        return f"{self.id}{self.suffix}"

    def get_image_path(self) -> Path:
        image_path = gallery_config.data_dir / str(self.gallery.id) / self.get_file_name()
        if not image_path.exists():
            raise FileNotFoundError("Image file not found")
        return image_path

    def update_tags(self, new_tags: list[str]):
        tag_ids = ImageMeta.get_or_create_tags(new_tags)
        cursor = db.execute("select tag_id from image_tags where image_id=?", (self.id,))
        rows = cursor.fetchall()
        current_tag_ids = [row[0] for row in rows]
        for tag_id in current_tag_ids:
            if tag_id not in tag_ids:
                db.execute("delete from image_tags where image_id=? and tag_id=?", (self.id, tag_id))
        for tag_id in tag_ids:
            if tag_id not in current_tag_ids:
                db.execute("insert into image_tags (image_id, tag_id) VALUES (?,?)", (self.id, tag_id))
        db.commit()
        self.tags = new_tags

    def update_comment(self, new_comment: str):
        db.execute("update images set comment=? where id=?", (new_comment, self.id))
        db.commit()
        self.comment = new_comment

    def update_file_id(self, new_file_id: Optional[str]):
        db.execute("update images set file_id=? where id=?", (new_file_id, self.id))
        db.commit()
        self.file_id = new_file_id

    def drop(self):
        db.execute("delete from images where id=?", (self.id,))
        db.commit()
        image_path = self.get_image_path()
        if image_path.exists():
            image_path.unlink()

    def get_image(self) -> Image.Image:
        image_path = self.get_image_path()
        return Image.open(image_path)

    def is_same(self, other: PhashWrapper, threshold: int = 5) -> bool:
        distance = self.phash - other
        return distance <= threshold

    def ensure_thumb(self):
        try:
            if self.thumb_path is None:
                self.thumb_path = gallery_config.cache_dir / "thumbnails" / f"{self.id}_thumb.jpg"
            self.thumb_path.parent.mkdir(parents=True, exist_ok=True)
            if not os.path.exists(self.thumb_path):
                img = Image.open(self.get_image_path()).convert('RGB')
                img.thumbnail(gallery_config.thumbnail_size)
                img.save(self.thumb_path, format='JPEG', optimize=True, quality=85)
        except Exception as e:
            logger.warning(f'生成画廊图片 {self.id} 缩略图失败: {e}')
            self.thumb_path = None


gallery_manager = GalleryManager()
gallery_manager.load_galleries()
