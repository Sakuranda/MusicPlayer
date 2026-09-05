import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mutagen.mp4 import MP4
from app.media import fragmented, normalize_m4a


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg')
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'fragmented.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=2', '-c:a', 'aac',
                        '-movflags', '+frag_keyframe+empty_moov+default_base_moof',
                        str(self.path)], check=True)
        audio = MP4(self.path)
        audio['\xa9nam'] = ['保留歌名']
        audio['\xa9lyr'] = ['[00:00.00]保留歌词']
        audio.save()

    def test_remux_preserves_packets_tags_and_becomes_seekable(self):
        self.assertTrue(fragmented(self.path))
        self.assertEqual(MP4(self.path).info.length, 0)
        duration = normalize_m4a(self.path)
        self.assertAlmostEqual(duration, 2, delta=.1)
        self.assertFalse(fragmented(self.path))
        self.assertEqual(MP4(self.path)['\xa9nam'], ['保留歌名'])
        self.assertEqual(MP4(self.path)['\xa9lyr'], ['[00:00.00]保留歌词'])
        data = self.path.read_bytes()
        self.assertEqual(normalize_m4a(self.path), duration)
        self.assertEqual(data, self.path.read_bytes())

    def test_failed_remux_does_not_replace_original(self):
        original = self.path.read_bytes()
        with patch('app.media.subprocess.run', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                normalize_m4a(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob('.normalize-*')))


if __name__ == '__main__':
    unittest.main()

class StreamingTests(unittest.TestCase):
    def test_range_head_and_auth(self):
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        from app import main
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'song.m4a'
            path.write_bytes(bytes(range(256)))
            with (patch.object(main, 'MUSIC_DIR', Path(tmp)),
                  patch.object(main, 'get_conn', return_value=Mock()),
                  patch.object(main, 'get_song', return_value={
                      'file_path': path.name, 'title': '歌', 'artist': '人'}),
                  patch.object(main, 'API_TOKEN', 'test-token'),
                  patch.object(main.auth_service, 'enabled', return_value=False)):
                client = TestClient(main.app)
                self.assertEqual(client.get('/api/stream/1').status_code, 401)
                headers = {'X-Api-Token': 'test-token'}
                response = client.get('/api/stream/1', headers={**headers, 'Range': 'bytes=0-1'})
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.content, b'\x00\x01')
                self.assertEqual(response.headers['content-range'], 'bytes 0-1/256')
                self.assertTrue(response.headers['content-disposition'].startswith('inline'))
                response = client.get('/api/stream/1', headers={**headers, 'Range': 'bytes=256-'})
                self.assertEqual(response.status_code, 416)
                response = client.head('/api/stream/1', headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b'')
                self.assertEqual(response.headers['content-length'], '256')
