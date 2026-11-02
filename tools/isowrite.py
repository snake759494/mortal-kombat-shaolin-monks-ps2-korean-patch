"""한글 ISO 기록: 원본 복사 → GAMEDATA.WAD 를 이미지 끝으로 옮기고 바뀐 파일을 그 뒤에 덧붙임 → 색인·ISO9660·UDF 갱신

엔진은 색인 오프셋(섹터)*2048 / 0x19000000 으로 WAD 파일 번호를 고르므로, 색인 파일은 모두 GAMEDATA.WAD
(가상 0x19000000 바이트) 안에 있어야 한다. 원본 WAD 는 407,222,272 바이트라 뒤에 약 12MB 를 덧붙일 수 있다."""
import os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wadlib import *
import udf

ELF_LBA, ELF_SLOT = 200628, 203039 - 200628     # SLUS_210.87 자리(다음 파일 WADCRC.BIN 까지)


def find_rec(f, dir_lba, dir_len, name):
    f.seek(dir_lba * SEC); d = f.read(dir_len)
    p = 0
    while p < len(d):
        ln = d[p]
        if ln == 0:
            p = (p // SEC + 1) * SEC; continue
        nl = d[p + 32]
        if d[p + 33:p + 33 + nl] == name:
            return dir_lba * SEC + p
        p += ln
    raise KeyError(name)


def set_rec(f, pos, lba, size):
    f.seek(pos + 2); f.write(struct.pack('<I', lba) + struct.pack('>I', lba) + struct.pack('<I', size) + struct.pack('>I', size))


def build(out_path, changes, elf=None, log=print, raw=()):
    """changes: {색인번호: 압축 해제된 새 내용}, raw: [(ISO LBA, 같은 크기 바이트)] 제자리 덮어쓰기(동영상)"""
    shutil.copyfile(ISO_IN, out_path)
    with open(out_path, 'r+b') as f:
        for lba, data in raw:
            f.seek(lba * SEC); f.write(data)
        f.seek(16 * SEC); pvd = f.read(SEC)
        total = struct.unpack_from('<I', pvd, 80)[0]
        root_lba, root_len = struct.unpack_from('<I', pvd, 156 + 2)[0], struct.unpack_from('<I', pvd, 156 + 10)[0]
        w = Wad(f)
        _, wad_lba, wad_size = WADS[0]
        limit = 0x19000000 // SEC
        wad_secs = wad_size // SEC
        new_lba = total
        # WAD 복사
        f.seek(wad_lba * SEC)
        rem = wad_size; dst = new_lba * SEC
        while rem:
            n = min(rem, 64 << 20)
            f.seek(wad_lba * SEC + (wad_size - rem)); buf = f.read(n)
            f.seek(dst); f.write(buf); dst += n; rem -= n
        cur = wad_secs                       # WAD 안의 섹터 위치
        for i in sorted(changes):
            raw = w.raw(i)
            nd = ewdf(raw, changes[i])
            f.seek((new_lba + cur) * SEC); f.write(nd)
            w.set_entry(i, cur, len(nd), len(changes[i]))
            cur += (len(nd) + SEC - 1) // SEC
        assert cur <= limit, ('WAD 가상 공간 초과', cur)
        new_wad_size = cur * SEC
        f.seek((new_lba + cur) * SEC - 1); f.write(b'\0')
        end = new_lba + cur + 1
        # 색인(옮긴 WAD 의 머리)
        f.seek(new_lba * SEC); f.write(w.hdr)
        # ISO9660
        set_rec(f, find_rec(f, root_lba, root_len, b'GAMEDATA.WAD;1'), new_lba, new_wad_size)
        u = udf.UDF(f)
        u.set_file('/GAMEDATA.WAD', new_lba, new_wad_size)
        if elf is not None:
            if len(elf) <= ELF_SLOT * SEC:
                elf_lba = ELF_LBA
            else:                            # 제자리에 안 들어가면 이미지 끝으로
                elf_lba = end; end += (len(elf) + SEC - 1) // SEC
            f.seek(elf_lba * SEC); f.write(elf + b'\0' * ((-len(elf)) % SEC))
            set_rec(f, find_rec(f, root_lba, root_len, b'SLUS_210.87;1'), elf_lba, len(elf))
            u.set_file('/SLUS_210.87', elf_lba, len(elf))
        f.seek(16 * SEC + 80); f.write(struct.pack('<I', end) + struct.pack('>I', end))
        u.grow(end)
        f.truncate(end * SEC)
    log('ISO %s: %d 섹터, WAD -> %d (+%d 섹터)' % (os.path.basename(out_path), end, new_lba, cur - wad_secs))


ELF_SIZE = 4934152


def find_elf(f):
    f.seek(ELF_LBA * SEC)
    return f.read(ELF_SIZE)
