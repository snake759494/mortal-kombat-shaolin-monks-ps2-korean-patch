"""GAMEDATA.WAD~WAJ (PWF 색인 + EWDF raw-deflate 파일) 읽기/쓰기"""
import struct, zlib, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO_IN = os.path.join(ROOT, 'Mortal Kombat - Shaolin Monks (USA).iso')
SEC = 2048
# (이름, ISO LBA, 크기) — 원본 이미지 기준
WADS = [('GAMEDATA.WAD', 203053, 407222272), ('GAMEDATA.WAE', 401892, 418308096),
        ('GAMEDATA.WAF', 606144, 413184000), ('GAMEDATA.WAG', 807894, 416487424),
        ('GAMEDATA.WAH', 1011257, 377632768), ('GAMEDATA.WAI', 1195648, 55541760),
        ('GAMEDATA.WAJ', 1222768, 269035520)]
NENT = 0x1be3
IDX_OFF = 0x20


def wadsec_to_iso(s):
    for _, l, sz in WADS:
        n = sz // SEC
        if s < n:
            return l + s
        s -= n
    raise ValueError(s)


def wad_base(k):
    """k 번째 WAD 파일의 가상 섹터 시작"""
    return sum(sz // SEC for _, _, sz in WADS[:k])


class Wad:
    def __init__(self, f):
        self.f = f
        f.seek(WADS[0][1] * SEC)
        self.hdr = bytearray(f.read(IDX_OFF + 8 * NENT))

    def entry(self, i):
        lo, hi = struct.unpack_from('<II', self.hdr, IDX_OFF + i * 8)
        if not hi >> 31:
            return None
        return lo & 0x3fffff, (lo >> 22) | ((hi & 0xfff) << 10), (hi >> 12) & 0x7ffff

    def set_entry(self, i, off, size, usize):
        x = (usize + 15) // 8 + 1
        assert off < 1 << 22 and size < 1 << 22 and x < 1 << 19
        lo = off | ((size & 0x3ff) << 22)
        hi = (1 << 31) | (x << 12) | (size >> 10)
        struct.pack_into('<II', self.hdr, IDX_OFF + i * 8, lo, hi)

    def raw(self, i):
        off, size, _ = self.entry(i)
        self.f.seek(wadsec_to_iso(off) * SEC)
        return self.f.read(size)

    def get(self, i):
        d = self.raw(i)
        assert d[:4] == b'EWDF'
        us, hl = struct.unpack_from('<II', d, 4)
        u = zlib.decompressobj(-15).decompress(d[hl:])
        assert len(u) == us
        return u


def ewdf(orig_raw, data):
    """원본 EWDF 헤더(이름·해시)를 유지하고 내용만 다시 압축"""
    hl = struct.unpack_from('<I', orig_raw, 8)[0]
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = c.compress(data) + c.flush()
    h = bytearray(orig_raw[:hl])
    struct.pack_into('<I', h, 4, len(data))
    return bytes(h) + body
