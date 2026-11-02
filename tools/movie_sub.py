"""FMV(/FRONT/MOVIES/*.SFD)에 한국어 자막을 입힌다 (뉴룸매니아·나디아 한글패치와 같은 방식).

python tools/movie_sub.py [이름 ...]   원본 ISO 에서 SFD 를 읽어 translation/movie/<이름>.tsv 자막을 입혀 work/movie/enc/<이름>.SFD

원본: Sofdec(MPEG-1 팩, 2048바이트 섹터), 영상 MPEG-2 29.97fps(512x272 / 512x288 / 640x432), 음성 ADX(+AC3) 여러 트랙.
방법: 영상 전체를 같은 프레임 수로 다시 인코딩하고 sofdec_remux 로 영상 섹터 페이로드만 채운다.
      음성 섹터·팩 헤더·파일 크기는 원본 그대로라 ISO 의 같은 자리에 덮어쓸 수 있다.
자막: 나눔스퀘어네오 Bold, 흰 글자 + 검은 외곽선, 화면 아래 가운데.
tsv: 시작초 <TAB> 끝초 <TAB> 한국어 (줄바꿈은 \\n), # 줄은 주석
"""
import os, sys, struct, subprocess
import av
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sofdec_remux

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISO_IN = os.path.join(ROOT, 'Mortal Kombat - Shaolin Monks (USA).iso')
SUBS = os.path.join(ROOT, 'translation', 'movie')
ENC = os.path.join(ROOT, 'work', 'movie', 'enc')
FONT = os.path.join(ROOT, 'NanumSquareNeo-cBd.ttf')
FPS = 30000 / 1001
SECTOR = 2048; PACK = 12
SC = bytes([0, 0, 1])
# 이름: (ISO LBA, 크기)
MOVIES = {'OPENING': (1586337, 225660928), 'END006': (1354133, 236795904), 'END011': (1469756, 96176128),
          'FINAL': (1516717, 142581760), 'BLITZ': (176992, 44642304), 'GAUNTLET': (166159, 22185984)}


def read_orig(name):
    lba, size = MOVIES[name]
    with open(ISO_IN, 'rb') as f:
        f.seek(lba * SECTOR); return f.read(size)


def video_slots(sfd):
    out = []
    for base in range(0, len(sfd), SECTOR):
        if sfd[base:base + 4] != SC + b'\xba': continue
        c = base + PACK
        if sfd[c:c + 4] != SC + b'\xe0': continue
        ln = struct.unpack_from('>H', sfd, c + 4)[0]; end = c + 6 + ln
        p = c + 6
        while sfd[p] == 0xFF: p += 1
        if sfd[p] >> 6 == 1: p += 2
        f = sfd[p]
        p += 1 if f == 0x0F else 5 if f >> 4 == 2 else 10
        out.append((p, end - p))
    return out


def video_es(sfd):
    return b''.join(sfd[p:p + n] for p, n in video_slots(sfd))


def pic_count(es):
    n, i = 0, 0
    while True:
        i = es.find(SC + b'\x00', i)
        if i < 0: return n
        n += 1; i += 4


def load_subs(name):
    subs = []
    for ln in open(os.path.join(SUBS, name + '.tsv'), encoding='utf8').read().splitlines():
        if ln.strip() and not ln.startswith('#'):
            s, e, t = ln.split('\t', 2); subs.append((float(s), float(e), t))
    return subs


class Renderer:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.size = max(16, round(h * 0.068))              # 272 → 18px, 432 → 29px
        self.line_h = round(self.size * 1.25)
        self.stroke = 2
        self.bottom = h - round(h * 0.05)
        self.font = ImageFont.truetype(FONT, self.size)

    def __call__(self, text):
        im = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        lines = text.split('\\n'); y = self.bottom - self.line_h * len(lines)
        for ln in lines:
            d.text((self.w // 2, y + self.line_h / 2), ln, font=self.font, anchor='mm', fill=(255, 255, 255, 255),
                   stroke_width=self.stroke, stroke_fill=(0, 0, 0, 255))
            y += self.line_h
        return im


def process(name):
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    src = read_orig(name)
    es = video_es(src)
    n = pic_count(es)
    os.makedirs(ENC, exist_ok=True)
    tmp = os.path.join(ENC, name + '.src.m2v'); open(tmp, 'wb').write(es)
    c = av.open(tmp); vs = c.streams.video[0]; W, H = vs.codec_context.width, vs.codec_context.height
    render = Renderer(W, H)
    sub_at = [None] * n
    for s0, e0, t in load_subs(name):
        for fi in range(int(round(s0 * FPS)), min(n, int(round(e0 * FPS)))): sub_at[fi] = t
    out_m2v = os.path.join(ENC, name + '.m2v')
    cap = len(sofdec_remux.analyse(src)[0]) * sofdec_remux.VIDEO_PAYLOAD
    rate = int(cap * 8 / (n / FPS) * 0.80)                  # 정렬 여유 20%
    aspect = '16:9' if W * 10 // H > 15 else '4:3'
    enc = subprocess.Popen([FF, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                            '-s', '%dx%d' % (W, H), '-r', '30000/1001', '-i', '-',
                            '-c:v', 'mpeg2video', '-pix_fmt', 'yuv420p', '-b:v', str(rate), '-maxrate', str(int(rate * 1.15)),
                            '-bufsize', '1179648', '-g', '15', '-bf', '2', '-aspect', aspect,
                            '-f', 'mpeg2video', out_m2v], stdin=subprocess.PIPE)
    cache = {}; k = 0
    for fr in c.decode(video=0):
        if k >= n: break
        t = sub_at[k]
        if t:
            if t not in cache: cache[t] = render(t)
            base = fr.to_image().convert('RGBA'); base.alpha_composite(cache[t])
            enc.stdin.write(base.convert('RGB').tobytes())
        else:
            enc.stdin.write(fr.to_ndarray(format='rgb24').tobytes())
        k += 1
    c.close(); enc.stdin.close(); enc.wait(); os.remove(tmp)
    assert k == n, (k, n)
    video = open(out_m2v, 'rb').read()
    dst = sofdec_remux.remux(src, video)
    assert len(dst) == len(src)
    open(os.path.join(ENC, name + '.SFD'), 'wb').write(dst)
    os.remove(out_m2v)
    print(name, '%dx%d' % (W, H), '프레임', n, '비트레이트', rate, '영상', len(video), '/', cap, flush=True)


def preview(name, t, path):
    tmp = path + '.m2v'; open(tmp, 'wb').write(video_es(open(os.path.join(ENC, name + '.SFD'), 'rb').read()))
    c = av.open(tmp)
    for i, fr in enumerate(c.decode(video=0)):
        if i == int(t * FPS): fr.to_image().save(path); break
    c.close(); os.remove(tmp)


def patched():
    """[(ISO LBA, 새 SFD 바이트)] — 인코딩된 것만"""
    out = []
    for n, (lba, size) in MOVIES.items():
        p = os.path.join(ENC, n + '.SFD')
        if os.path.exists(p) and os.path.exists(os.path.join(SUBS, n + '.tsv')):
            d = open(p, 'rb').read(); assert len(d) == size; out.append((lba, d))
    return out


if __name__ == '__main__':
    for n in sys.argv[1:] or [n for n in MOVIES if os.path.exists(os.path.join(SUBS, n + '.tsv'))]: process(n)
