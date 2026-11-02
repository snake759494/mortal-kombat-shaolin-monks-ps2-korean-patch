"""SLUS_210.87 패치: 한글 디코더(kdec.S)·글리프 캐시(kcache.c)·글리프 저장소를 0xA0000 PT_LOAD 세그먼트로 붙이고 호출부를 바꾼다

0x80000-0x100000 은 EELOAD 잔재(0x81000-0x8e000) 외에 비어 있고 게임이 쓰지 않는다(메뉴·게임 중 RAM 확인).
"""
import os, struct, subprocess, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
SEG_VA = 0xa0000
SEG_END = 0xff000                 # 0xff000 은 테스트용 가상 패드가 씀
KF = 'kcols gw ch y0 W cap bpp glyph cache'.split()

# (호출 주소, 새 대상, 지연 슬롯에 넣을 'move a1, 폰트객체')
MOVE_A1 = {'s0': 0x02002821, 's1': 0x02202821, 's5': 0x02a02821}
# 'peek' = 커닝용 다음 글자 미리읽기(포인터+1 로 부름) → kpeek_*
CALLS = [(0x37efc8, 'big', 's0'), (0x37efd8, 'peek_big', 's0'), (0x37efec, 'small', 's0'), (0x37effc, 'peek_small', 's0'),
         (0x37faf4, 'big', 's1'), (0x37fb08, 'small', 's1'),
         (0x2f5d84, 'big', 's5'), (0x2f5d94, 'peek_big', 's5'), (0x2f5da8, 'small', 's5'), (0x2f5db8, 'peek_small', 's5')]
ORIG_TGT = {'big': 0x37fc30, 'small': 0x37fb90, 'peek_big': 0x37fc30, 'peek_small': 0x37fb90}


def assemble(tmp):
    e = os.path.join(tmp, 'k.elf')
    cc = [sys.executable, '-m', 'ziglang']
    objs = []
    for src, extra in (('kdec.S', []), ('kcache.c', ['-O2', '-ffreestanding', '-fno-builtin', '-mno-abicalls', '-fno-pic', '-G0', '-msoft-float', '-fno-stack-protector'])):
        o = os.path.join(tmp, src + '.o')
        subprocess.run(cc + ['cc', '-target', 'mipsel-freestanding', '-march=mips2', '-mabi=32', '-c'] + extra +
                       [os.path.join(TOOLS, src), '-o', o], check=True)
        objs.append(o)
    subprocess.run(cc + ['ld.lld', '-T', os.path.join(TOOLS, 'klink.ld')] + objs + ['-o', e], check=True)
    d = open(e, 'rb').read()
    shoff, = struct.unpack_from('<I', d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
    secs = [struct.unpack_from('<10I', d, shoff + i * shentsize) for i in range(shnum)]
    names = secs[shstrndx]
    blob, syms = None, {}
    for s in secs:
        nm = d[names[4] + s[0]:].split(b'\0')[0]
        if nm == b'.k':
            assert s[3] == SEG_VA
            blob = bytearray(d[s[4]:s[4] + s[5]])
        if s[1] == 2:                                  # SYMTAB
            strtab = secs[s[6]]
            for k in range(0, s[5], 16):
                n, v = struct.unpack_from('<II', d, s[4] + k)
                syms[d[strtab[4] + n:].split(b'\0')[0].decode()] = v
    return blob, syms


def patch(elf, fonts, tmp):
    """fonts: {'small': (params, glyphs), 'big': (params, glyphs)}"""
    import kfont
    blob, syms = assemble(tmp)
    kd = syms['kdata'] - SEG_VA
    blob[kd + 4:kd + 36] = kfont.param_block(fonts['small'][0])
    blob[kd + 36:kd + 68] = kfont.param_block(fonts['big'][0])
    for name in ('small', 'big'):
        p, g = fonts[name]
        while len(blob) % 16:
            blob.append(0)
        gaddr = SEG_VA + len(blob); blob += g
        while len(blob) % 16:
            blob.append(0)
        caddr = SEG_VA + len(blob); blob += bytes(p['W'] * (p['H'] - p['y0']) // 2)
        v = dict(kcols=p['cols'], gw=p['gw'], ch=p['ch'], y0=p['y0'], W=p['W'], cap=p['cap'],
                 bpp=4 if name == 'big' else 1, glyph=gaddr, cache=caddr)
        struct.pack_into('<9I', blob, syms['kf_' + name] - SEG_VA, *[v[k] for k in KF])
    assert p['cap'] <= 168
    assert SEG_VA + len(blob) <= SEG_END, hex(SEG_VA + len(blob))
    print('세그먼트 0x%x-0x%x' % (SEG_VA, SEG_VA + len(blob)))
    e = bytearray(elf)
    phoff, = struct.unpack_from('<I', e, 0x1c)
    phnum, = struct.unpack_from('<H', e, 0x2c)
    assert phnum == 1
    vaddr, filesz = struct.unpack_from('<I', e, phoff + 8)[0], struct.unpack_from('<I', e, phoff + 16)[0]
    off0 = struct.unpack_from('<I', e, phoff + 4)[0]

    def w32(va, v):
        o = va - vaddr + off0
        struct.pack_into('<I', e, o, v)

    def r32(va):
        return struct.unpack_from('<I', e, va - vaddr + off0)[0]

    for addr, kind, reg in CALLS:
        assert r32(addr) == (3 << 26) | (ORIG_TGT[kind] >> 2) and r32(addr + 4) == 0, hex(addr)
        w32(addr, (3 << 26) | (syms[('k' + kind) if kind.startswith('peek') else ('kdec_' + kind)] >> 2))
        w32(addr + 4, MOVE_A1[reg])
    # 버튼 아이콘 문자 검색(0x1a03f0)이 0xA2 를 아이콘으로 보고 한글 문자열을 쪼갬 → 0xA2 비교 무효화
    assert r32(0x1a042c) == 0x2402ffa2
    w32(0x1a042c, 0x24020100)
    # 새 PT_LOAD
    while len(e) % 16:
        e.append(0)
    foff = len(e)
    e += blob
    struct.pack_into('<8I', e, phoff + 32, 1, foff, SEG_VA, SEG_VA, len(blob), len(blob), 7, 0x10)
    struct.pack_into('<H', e, 0x2c, 2)
    return bytes(e), syms
