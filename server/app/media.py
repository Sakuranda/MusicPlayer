"""Normalize downloaded DASH containers without re-encoding their AAC packets."""
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from mutagen.mp4 import MP4


def fragmented(path: Path) -> bool:
    size = path.stat().st_size
    with path.open('rb') as stream:
        while stream.tell() < size:
            offset = stream.tell()
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError('不完整的 MP4 文件头')
            length, kind = struct.unpack('>I4s', header)
            header_size = 8
            if length == 1:
                extended = stream.read(8)
                if len(extended) != 8:
                    raise ValueError('不完整的 MP4 扩展头')
                length = struct.unpack('>Q', extended)[0]
                header_size = 16
            if length == 0:
                length = size - offset
            if length < header_size or offset + length > size:
                raise ValueError('不完整的 MP4 数据')
            if kind == b'moof':
                return True
            stream.seek(offset + length)
    return False


def normalize_m4a(path: Path) -> float:
    """Atomic remux; preserve all Mutagen tags, cover and lyrics, fail closed."""
    original = MP4(path)
    if not fragmented(path) and original.info.length > 0:
        return original.info.length
    tags = dict(original.tags or {})
    fd, name = tempfile.mkstemp(prefix='.normalize-', suffix='.m4a', dir=path.parent)
    os.close(fd)
    target = Path(name)
    try:
        subprocess.run([
            'ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(path),
            '-map', '0:a:0', '-c:a', 'copy', '-map_metadata', '-1',
            '-movflags', '+faststart', str(target),
        ], check=True, capture_output=True, timeout=180)
        normalized = MP4(target)
        duration = normalized.info.length
        if duration <= 0 or fragmented(target):
            raise ValueError('封装后没有有效的音频时长')
        # Compare packet count AND compressed packet hashes, including the last
        # fragment. A successful ffmpeg exit alone does not prove completeness.
        def packets(file: Path) -> bytes:
            return subprocess.run([
                'ffprobe', '-v', 'error', '-select_streams', 'a:0',
                '-show_packets', '-show_entries', 'packet=data_hash',
                '-show_data_hash', 'sha256', '-of', 'csv=p=0', str(file),
            ], check=True, capture_output=True, timeout=180).stdout
        before = packets(path)
        if not before.strip() or before != packets(target):
            raise ValueError('封装前后音频包不一致，保留原文件')
        if normalized.tags is None:
            normalized.add_tags()
        normalized.tags.update(tags)
        normalized.save()
        target.chmod(path.stat().st_mode & 0o777)
        os.replace(target, path)
        return duration
    finally:
        target.unlink(missing_ok=True)
