"""한글 글꼴: 4bpp 폰트 텍스처(P2N)와 동적 캐시용 글리프 저장소 생성

- 텍스처는 원래 VRAM 크기를 지킨다(큰 폰트 256x256 8bpp → 512x256 4bpp, 작은 폰트 128x128 8bpp → 256x128 4bpp).
  원래 라틴 글리프를 W/칸폭 열로 다시 배치하고(엔진 규칙 i % cols, i / cols), 그 아래를 한글 캐시 칸으로 비워 둔다.
- 한글 글리프는 ELF 의 저장소(0xA0000 세그먼트)에 두고, kcache.c 가 필요할 때 캐시 칸에 복사해 GS 로 올린다.
  큰 폰트: 서울한강 EB 18px, 4bpp(칸 18x21, 189바이트). 작은 폰트: 갈무리11 12px, 1bpp(칸 12x14, 28바이트).
- FIF 의 빈 항목(원래 글리프 수 이후)과 커닝 열 norig 이후를 0 으로 지워 한글 슬롯(0xF0-0xFE)에 쓰레기 커닝이 붙지 않게 한다.
"""
import os, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_idx = np.arange(256)
SW = (_idx & 0xE7) | ((_idx & 8) << 1) | ((_idx & 16) >> 1)       # CSM1 팔레트 순서

BIG = dict(name='big', W=512, H=256, cw=21, ch=21, norig=144, gw=18, bpp=4,
           font=os.path.join(ROOT, 'SeoulHangangEB.ttf'), size=18, aa=True, bottom=20, row_table=0x6ed988)
SMALL = dict(name='small', W=256, H=128, cw=12, ch=14, norig=90, gw=12, bpp=1,
             font=os.path.join(ROOT, 'fonts', 'Galmuri11.ttf'), size=12, aa=False, bottom=13, row_table=0x6e5588)


def code_of(k):
    return bytes((0xA1 + k // 94, 0xA1 + k % 94))


def p2n_load(d):
    w, h, bpp = struct.unpack_from('<III', d, 0x10)
    pal = np.frombuffer(d[0x80:0x480], np.uint8).reshape(256, 4)
    pix = np.frombuffer(d[0x480:0x480 + w * h], np.uint8).reshape(h, w)
    return w, h, pal[SW][pix].astype(np.int32)                   # RGBA(알파 0..128)


NWHITE = 9                                                        # 흰색 알파 단계 수(나머지 7색은 버튼 아이콘용)


HUES = [(230, 110, 220), (90, 220, 90), (50, 160, 235), (225, 45, 35)]     # □ △ × ○ 기호색


def icon_palette(rgba, mask):
    """아이콘 칸 불투명 픽셀: 기호 4색(색상별 평균) + 무채색 쪽 k-평균 3색"""
    px = rgba[mask & (rgba[..., 3] >= 96)][:, :3].astype(np.float64)
    sat = px.max(1) - px.min(1)
    out, used = [], np.zeros(len(px), bool)
    hues = np.array(HUES, np.float64)
    near = ((px[:, None] - hues[None]) ** 2).sum(2).argmin(1)
    for h in range(len(HUES)):
        sel = (sat > 80) & (near == h)
        out.append(px[sel].mean(0) if sel.any() else hues[h])
        used |= sel
    rest = px[~used & (sat <= 80)]
    k = 16 - NWHITE - len(HUES)
    c = np.quantile(rest, np.linspace(0.1, 0.9, k), axis=0)
    for _ in range(30):
        lab = ((rest[:, None] - c[None]) ** 2).sum(2).argmin(1)
        c = np.array([rest[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
    return np.rint(np.concatenate([out, c])).astype(np.int32)


def full_palette(icons):
    pal = [(255, 255, 255, round(i * 128 / (NWHITE - 1))) for i in range(NWHITE)]
    return np.array(pal + [(r, g, b, 128) for r, g, b in icons], np.int32)


def quantize(rgba, pal, icon_mask):
    """글자: 알파만으로 흰색 단계, 아이콘 칸: 사전곱 RGBA 최근접"""
    idx = np.clip(np.rint(rgba[..., 3] * (NWHITE - 1) / 128.0), 0, NWHITE - 1).astype(np.uint8)
    pm = lambda a: np.concatenate([a[..., :3] * a[..., 3:4] / 128.0, a[..., 3:4] * 2.0], -1)
    sel = icon_mask
    d = ((pm(rgba[sel])[:, None] - pm(pal)[None]) ** 2).sum(2)
    idx[sel] = d.argmin(1)
    return idx


def p2n_save4(orig, lvl, palette):
    """lvl: (H,W) 팔레트 번호 → 4bpp P2N (팔레트 0x80바이트: 0-7 @0x80, 8-15 @0xC0, 픽셀 @0x100)"""
    H, W = lvl.shape
    pal = bytearray(0x80)
    for i in range(16):
        struct.pack_into('4B', pal, (i & 7) * 4 + (i >> 3) * 0x40, *[int(v) for v in palette[i]])
    h = bytearray(orig[:0x80])
    struct.pack_into('<III', h, 0x10, W, H, 4)
    struct.pack_into('<II', h, 0x24, W * H // 2, 0x80)
    struct.pack_into('<II', h, 0x34, 0x100, 0x80)
    struct.pack_into('<I', h, 0x40, 0x100 + W * H // 2)
    return bytes(h) + bytes(pal) + pack4(lvl).tobytes()


def pack4(lvl):
    return (lvl[:, 0::2] | (lvl[:, 1::2] << 4)).astype(np.uint8)   # 왼쪽 픽셀 = 아래 니블


def glyph_metrics(L):
    f = ImageFont.truetype(L['font'], L['size'])
    top, bot = 999, -999
    for c in '한글뷁힣각낡쀍윙':
        bb = f.getbbox(c)
        top, bot = min(top, bb[1]), max(bot, bb[3])
    return f, top, bot


def layout(L):
    ncols = L['W'] // L['cw']
    y0 = ((L['norig'] + ncols - 1) // ncols) * L['ch']
    kcols = L['W'] // L['gw']
    return y0, kcols, kcols * ((L['H'] - y0) // L['ch'])


def render(L, orig_p2n, chars):
    """반환: (P2N 바이트, 글리프 저장소 바이트, 배치 파라미터, 미리보기 알파)"""
    W, H, cw, ch, gw = L['W'], L['H'], L['cw'], L['ch'], L['gw']
    ow, oh, oa = p2n_load(orig_p2n)
    rgba = np.zeros((H, W, 4), np.int32)
    imask = np.zeros((H, W), bool)
    ocols, ncols = ow // cw, W // cw
    for i in range(L['norig']):
        sx, sy = (i % ocols) * cw, (i // ocols) * ch
        dx, dy = (i % ncols) * cw, (i // ncols) * ch
        c = oa[sy:sy + ch, sx:sx + cw]
        rgba[dy:dy + ch, dx:dx + cw] = c
        op = c[..., 3] >= 64
        if op.any() and (c[op][:, :3].min(1) < 160).mean() > 0.15:     # 색 있는 칸 = 버튼 아이콘
            imask[dy:dy + ch, dx:dx + cw] = True
    palette = full_palette(icon_palette(rgba, imask))
    lvl = quantize(rgba, palette, imask)
    out = rgba[..., 3]
    y0, kcols, cap = layout(L)
    f, top, bot = glyph_metrics(L)
    gh = bot - top
    store = bytearray()
    prev = out.copy()
    for k, c in enumerate(chars):
        im = Image.new('L', (gw + 8, ch + 8), 0)
        d = ImageDraw.Draw(im)
        if not L['aa']:
            d.fontmode = '1'
        bb = f.getbbox(c)
        gx = max(0, (gw - 1 - (bb[2] - bb[0])) // 2) - bb[0]   # 잉크가 칸보다 넓으면 왼쪽 정렬(잘림 방지)
        gy = L['bottom'] + 1 - gh - top          # 글자 아래를 칸의 bottom 행에 맞춤
        d.text((4 + gx, 4 + gy), c, font=f, fill=255)
        a = np.asarray(im, np.int32)[4:4 + ch, 4:4 + gw]
        if L['bpp'] == 4:
            store += pack4(np.clip(np.rint(a * (NWHITE - 1) / 255.0), 0, NWHITE - 1).astype(np.uint8)).tobytes()
        else:
            bits = (a >= 128).astype(np.uint8)
            for row in bits:
                v = 0
                for x, b in enumerate(row):
                    v |= int(b) << x
                store += struct.pack('<H', v)
        if k < cap:                              # 미리보기용으로 캐시 칸에 앞 글자들 채움
            x, y = (k % kcols) * gw, y0 + (k // kcols) * ch
            prev[y:y + ch, x:x + gw] = (a * 128 + 127) // 255
    params = dict(cols=kcols, gw=gw, ch=ch, x0=0, y0=y0, W=W, H=H, row_table=L['row_table'], cap=cap)
    return p2n_save4(orig_p2n, lvl, palette), bytes(store), params, prev


def fif_clean(fif, norig):
    """원래 글리프 이후 항목과 커닝 열 norig 이후를 0 으로"""
    b = bytearray(fif)
    n, hdr, stride = struct.unpack_from('<III', b, 8)
    for i in range(n):
        p = hdr + i * stride
        if i >= norig:
            b[p:p + stride] = bytes(stride)
        else:
            b[p + 4 + norig:p + stride] = bytes(stride - 4 - norig)
    return bytes(b)


def param_block(p):
    return struct.pack('<5I2fI', p['cols'], p['gw'], p['ch'], p['x0'], p['y0'], 1.0 / p['W'], 1.0 / p['H'], p['row_table'])


def preview(alpha, path, scale=1):
    h, w = alpha.shape
    Image.fromarray(np.clip(alpha * 2, 0, 255).astype(np.uint8)).resize((w * scale, h * scale), Image.NEAREST).save(path)
