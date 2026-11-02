"""메뉴 그림 글자(프론트엔드 내부 WAD 들에 든 P2N 8bpp, 선형) 를 한글로 다시 그린다

모양: 항목 = 흰 세리프 + 적갈색 번진 그림자, 제목 = 금색 그라데이션 + 짙은 테두리·그림자,
"돌아가기" = 회색 작은 글자(왼쪽 세모 버튼 그림 유지). 모두 왼쪽 위 정렬.
내부 WAD 는 압축되지 않은 P2N 을 그대로 담으므로 같은 크기로 제자리 교체한다.
"""
import os, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, 'SeoulHangangEB.ttf')
_idx = np.arange(256)
SW = (_idx & 0xE7) | ((_idx & 8) << 1) | ((_idx & 16) >> 1)

# (번역, 모양, [(WAD 색인, 내부 오프셋), ...]) — 같은 그림이 여러 WAD 에 있으면 영어판이 쓰는 것을 모두
W, G, B = 'white', 'gold', 'back'
ITEMS = [
    ('콘텐츠', W, [(58, 0x97e80)]),
    ('옵션', W, [(58, 0x9a300)]),
    ('불러오기', W, [(58, 0x9c780)]),
    ('대전 모드', W, [(58, 0xa0c00), (131, 0x7fc80)]),
    ('협동', W, [(58, 0xa5080), (130, 0x4ca80), (131, 0x84100)]),
    ('1인 플레이', W, [(58, 0xa7500), (130, 0x4ef00), (131, 0x86580)]),
    ('밝기', W, [(58, 0xf6200), (74, 0x78080)]),
    ('컨트롤러', W, [(58, 0xfa680)]),
    ('오디오', W, [(58, 0xfeb00), (74, 0x75c00)]),
    ('게임 설정', W, [(58, 0x100f80), (74, 0x71780)]),
    ('캐릭터 선택', G, [(64, 0x61300)]),
    ('레벨 선택', G, [(64, 0x8f980), (69, 0x1da00)]),
    ('옵션', G, [(74, 0x6be80)]),
    ('모드', W, [(74, 0x85b80)]),
    ('오디오', G, [(74, 0x8a000)]),
    ('음성 음량', W, [(74, 0x8e480)]),
    ('효과음', W, [(74, 0x92900)]),
    ('음악 음량', W, [(74, 0x96d80)]),
    ('게임 설정', G, [(74, 0x9b200)]),
    ('카메라 조작', W, [(74, 0xa3680)]),
    ('대전 경기 시간', W, [(74, 0xa7b00)]),
    ('대전 라운드 수', W, [(74, 0xabf80)]),
    ('제작진', W, [(79, 0xaa300), (91, 0x9c000)]),
    ('모탈 컴뱃 2', W, [(79, 0xac780), (91, 0x9e480)]),
    ('서퍼링 2 데모', W, [(79, 0xb0c00)]),
    ('사진', W, [(79, 0xb5080), (91, 0xa2900)]),
    ('영상', W, [(79, 0xb7500), (91, 0xa4d80)]),
    ('콘셉트 아트', W, [(79, 0xb9980), (91, 0xa7200)]),
    ('경기장', W, [(79, 0xbde00), (91, 0xab680)]),
    ('콘텐츠', G, [(79, 0xd1d80), (91, 0xbf600)]),
    ('불러오기', G, [(84, 0x41300)]),
    ('돌아가기', B, [(130, 0x36d00), (131, 0x94080)]),
    ('쿵 라오', W, [(130, 0x5ca00), (131, 0x98500)]),
    ('리우 캉', W, [(130, 0x60e80), (131, 0x9c980)]),
    ('구덩이', W, [(131, 0xa0e00)]),
    ('얼음 폭포', W, [(131, 0xa5280)]),
    ('포털', W, [(131, 0xa9700)]),
]


def wads():
    return sorted({i for _, _, l in ITEMS for i, _ in l})


def text_mask(text, w, h, size, x, y):
    S = 4                                                    # 초표본화
    big = Image.new('L', (w * S, h * S), 0)
    ImageDraw.Draw(big).text((x * S, y * S), text, font=ImageFont.truetype(FONT, size * S), fill=255)
    return np.asarray(big.resize((w, h), Image.LANCZOS), np.float32) / 255


def blur(m, r, dx=0, dy=0):
    im = Image.fromarray((m * 255).astype(np.uint8)).transform(m.shape[::-1], Image.AFFINE, (1, 0, -dx, 0, 1, -dy))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def over(top_rgb, top_a, bot_rgb, bot_a):
    a = top_a + bot_a * (1 - top_a)
    rgb = (top_rgb * top_a[..., None] + bot_rgb * (bot_a * (1 - top_a))[..., None]) / np.maximum(a, 1e-6)[..., None]
    return rgb, a


def render_gold(text, w, h):
    t = text_mask(text, w, h, 37, 4, 2)
    ys = np.linspace(0, 1, h)[:, None, None]
    top, mid, bot = np.array([255, 246, 170.]), np.array([238, 180, 40.]), np.array([140, 80, 8.])
    k = np.clip(ys / 0.62, 0, 1)
    grad = np.where(ys < 0.33, top + (mid - top) * np.clip(ys / 0.33, 0, 1), mid + (bot - mid) * np.clip((ys - 0.33) / 0.33, 0, 1))
    grad = np.broadcast_to(grad, (h, w, 3))
    outline = np.clip(blur(t, 1.0) * 3.0, 0, 1)
    shadow = np.clip(blur(t, 2.2, 2, 3) * 1.6, 0, 1) * 0.8
    rgb, a = over(np.broadcast_to(np.array([45, 22, 0.]), (h, w, 3)), outline, np.zeros((h, w, 3)), shadow)
    rgb, a = over(grad, t, rgb, a)
    return np.dstack([rgb, a * 255]).clip(0, 255).astype(np.uint8)


def render_back(text, w, h, orig_rgba):
    t = text_mask(text, w, h, 19, 79, 18)
    sh = np.clip(blur(t, 1.2, 1, 1) * 1.5, 0, 1) * 0.6
    rgb, a = over(np.broadcast_to(np.array([168, 168, 168.]), (h, w, 3)), t, np.zeros((h, w, 3)), sh)
    out = np.dstack([rgb, a * 255]).clip(0, 255).astype(np.uint8)
    out[:, :78] = orig_rgba[:, :78]                          # 세모 버튼 그림 유지
    return out


def render(text, w, h, size=27):
    f = ImageFont.truetype(FONT, size)
    S = 4                                                    # 초표본화
    big = Image.new('L', (w * S, h * S), 0)
    ImageDraw.Draw(big).text((5 * S, 6 * S), text, font=ImageFont.truetype(FONT, size * S), fill=255)
    txt = np.asarray(big.resize((w, h), Image.LANCZOS), np.float32) / 255
    sh = Image.fromarray((txt * 255).astype(np.uint8)).transform((w, h), Image.AFFINE, (1, 0, -2, 0, 1, -2))
    sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(2.6)), np.float32) / 255
    sh = np.clip(sh * 1.9, 0, 1)
    ys = np.linspace(0, 1, h)[:, None]
    white = np.stack([np.full((h, w), 1.0), np.full((h, w), 1.0), np.full((h, w), 1.0)], -1)
    white *= (1 - 0.22 * np.clip((ys - 0.2) / 0.4, 0, 1))[..., None]
    shadow = np.array([0.33, 0.10, 0.05])
    a = txt + sh * 0.85 * (1 - txt)
    rgb = (white * txt[..., None] + shadow * (sh * 0.85 * (1 - txt))[..., None]) / np.maximum(a, 1e-6)[..., None]
    return np.dstack([rgb * 255, a * 255]).clip(0, 255).astype(np.uint8)


def to_p2n8(orig, rgba):
    """선형 8bpp P2N: 팔레트 0x80(CSM1, 알파 0..128), 픽셀 0x480 — 원본 헤더 유지"""
    h, w = rgba.shape[:2]
    im = Image.fromarray(rgba, 'RGBA').quantize(256, method=Image.Quantize.FASTOCTREE)
    pal = np.zeros((256, 4), np.uint8)
    p = np.asarray(im.getpalette('RGBA') or [], np.uint8).reshape(-1, 4)[:256]
    pal[:len(p)] = p
    pal[:, 3] = (pal[:, 3].astype(np.int32) * 128 + 127) // 255
    pix = np.asarray(im, np.uint8)
    out = bytearray(orig)
    pa, = struct.unpack_from('<I', orig, 0x38)
    po, = struct.unpack_from('<I', orig, 0x34)
    phys = np.zeros((256, 4), np.uint8)
    phys[SW] = pal                                           # 논리 i → 물리 SW[i]
    out[pa:pa + 1024] = phys.tobytes()
    out[po:po + w * h] = pix.tobytes()
    return bytes(out)


def decode(blob):
    w, h = struct.unpack_from('<II', blob, 0x10)
    pal = np.frombuffer(blob[0x80:0x480], np.uint8).reshape(256, 4)[SW].astype(np.int32)
    pix = np.frombuffer(blob[0x480:0x480 + w * h], np.uint8).reshape(h, w)
    c = pal[pix]
    c[..., 3] = np.clip(c[..., 3] * 255 // 128, 0, 255)
    return c.astype(np.uint8)


def patch(idx, wad_bytes):
    d = bytearray(wad_bytes)
    for ko, style, locs in ITEMS:
        for i, off in locs:
            if i != idx:
                continue
            assert d[off:off + 4] == b'P2N\0'
            w, h, bpp = struct.unpack_from('<III', d, off + 0x10)
            ty, po = struct.unpack_from('<II', d, off + 0x30)
            assert bpp == 8 and ty == 3 and po == 0x480, (idx, hex(off), w, h, bpp, ty)
            n = 0x480 + w * h
            orig = bytes(d[off:off + n])
            img = render_gold(ko, w, h) if style == G else render_back(ko, w, h, decode(orig)) if style == B else render(ko, w, h)
            d[off:off + n] = to_p2n8(orig, img)
    return bytes(d)


# 로딩 화면(512x512 8bpp, 스위즐 type 10): 위쪽 가운데 금색 "LOADING" → "불러오는 중"
LOADING = [132, 133, 134, 618, 619, 620]


def _swz(w, h):
    y, x = np.mgrid[0:h, 0:w]
    bl = (y & ~0xf) * w + (x & ~0xf) * 2
    ss = (((y + 2) >> 2) & 1) * 4
    py = (((y & ~3) >> 1) + (y & 1)) & 7
    cl = py * w * 2 + ((x + ss) & 7) * 4
    bn = ((y >> 1) & 1) + ((x >> 2) & 2)
    return bl + cl + bn                                      # 화면 (y,x) → 파일 안 바이트 위치


def patch_loading(p2n):
    d = bytearray(p2n)
    w, h, bpp = struct.unpack_from('<III', d, 0x10)
    ty, po, pa = struct.unpack_from('<III', d, 0x30)
    assert (w, h, bpp, ty) == (512, 512, 8, 10)
    pos = _swz(w, h)
    pix = np.frombuffer(bytes(d[po:po + w * h]), np.uint8)[pos].copy()
    pal = np.frombuffer(bytes(d[pa:pa + 1024]), np.uint8).reshape(256, 4)[SW].astype(np.int32)
    rgb = pal[pix][..., :3]
    lum = rgb.sum(-1)
    y0, y1, x0, x1 = 20, 110, 120, 392
    ys, xs = np.nonzero(lum[y0:y1, x0:x1] > 60)
    ty0, ty1, tx0, tx1 = ys.min() + y0, ys.max() + y0, xs.min() + x0, xs.max() + x0
    dark = int(np.argmin(np.where(pal[:, 3] >= 120, pal[:, :3].sum(-1), 9999)))
    pix[ty0 - 3:ty1 + 4, tx0 - 3:tx1 + 4] = dark
    cw, chh = 240, 48
    g = render_gold('불러오는 중', cw, chh).astype(np.float32)
    tm = ImageFont.truetype(FONT, 37).getbbox('불러오는 중')
    gx = (tx0 + tx1) // 2 - (tm[2] + 8) // 2
    gy = (ty0 + ty1) // 2 - chh // 2 + 2
    reg = pal[pix[gy:gy + chh, gx:gx + cw]][..., :3].astype(np.float32)
    a = g[..., 3:] / 255
    comp = g[..., :3] * a + reg * (1 - a)
    cand = np.nonzero(pal[:, 3] >= 120)[0]
    cp = pal[cand, :3].astype(np.float32)
    dist = ((comp[:, :, None, :] - cp[None, None]) ** 2).sum(-1)
    pix[gy:gy + chh, gx:gx + cw] = cand[np.argmin(dist, -1)]
    buf = np.frombuffer(bytes(d[po:po + w * h]), np.uint8).copy()
    buf[pos] = pix
    d[po:po + w * h] = buf.tobytes()
    return bytes(d)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wadlib import Wad, ISO_IN
    w = Wad(open(ISO_IN, 'rb'))
    tiles = []
    for idx in wads():
        d = patch(idx, w.get(idx))
        for ko, style, locs in ITEMS:
            for i, off in locs:
                if i == idx:
                    c = decode(d[off:]).astype(np.float32); a = c[..., 3:] / 255
                    tiles.append(Image.fromarray((c[..., :3] * a + np.array([60, 60, 60]) * (1 - a)).astype(np.uint8)))
    W = 512; H = sum(t.height for t in tiles[:24])
    sheet = Image.new('RGB', (W * 2, H))
    y = 0
    for k, t in enumerate(tiles[:48]):
        sheet.paste(t, ((k // 24) * W, (k % 24) * 64))
    sheet.save(os.path.join(ROOT, 'work', 'menu_labels.png'))
    d = patch_loading(w.get(LOADING[0]))
    pos = _swz(512, 512)
    pal = np.frombuffer(d[0x80:0x480], np.uint8).reshape(256, 4)[SW]
    Image.fromarray(pal[np.frombuffer(d[0x480:0x480 + 512 * 512], np.uint8)[pos]][..., :3]).crop((96, 0, 416, 128)).resize((960, 384), Image.NEAREST).save(os.path.join(ROOT, 'work', 'loading.png'))
