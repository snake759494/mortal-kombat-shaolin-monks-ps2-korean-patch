"""Mortal Kombat: Shaolin Monks (SLUS-21087) 한글 패치 빌드

1. 번역(translation/*_ko.txt, 원문 *_en.txt 와 줄 대응) → 사용 음절 → 2바이트 코드(A1-FE, A1-FE)
2. 글꼴: 4bpp 텍스처(원래 VRAM 크기)에 원래 글리프 + 한글 캐시 칸, 글리프 저장소, FIF 커닝 정리
3. ELF: 한글 디코더·동적 캐시·저장소 세그먼트(0xA0000) 추가, 호출부 교체
4. 텍스트: 게임 내 문자열(4개 언어 파일 모두) · 메모리카드 문자열을 한글로, 메인 메뉴 그림 글자 교체
5. 동영상: work/movie/enc 의 자막 입힌 SFD 를 제자리에 덮어씀
6. ISO: GAMEDATA.WAD 를 이미지 끝으로 옮겨 바뀐 파일을 덧붙이고 ELF 를 제자리에 기록
"""
import os, sys, tempfile, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wadlib import *
from textfile import parse, build as tbuild
from extract_text import esc, unesc
import kfont, elfpatch, isowrite, menutex, movie_sub

ISO_OUT = os.path.join(ROOT, 'Mortal Kombat - Shaolin Monks (USA) [Korean].iso')
TR = os.path.join(ROOT, 'translation')
INGAME = (13, (11, 12, 14))        # 영어, (이탈리아어, 스페인어, 프랑스어) — 언어 설정과 무관하게 모두 한글
MC = (15, (16, 18, 19))
FONT_BIG, TEX_BIG, FONT_SMALL, TEX_SMALL = 0, 1, 2, 3


def load_pair(name):
    en = open(os.path.join(TR, name + '_en.txt'), encoding='utf-8').read().split('\n')[:-1]
    p = os.path.join(TR, name + '_ko.txt')
    ko = open(p, encoding='utf-8').read().split('\n') if os.path.exists(p) else []
    ko = (ko + [''] * len(en))[:len(en)]
    return {e: k for e, k in zip(en, ko) if k.strip()}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else ISO_OUT
    f = open(ISO_IN, 'rb'); w = Wad(f)
    maps = {'ingame': load_pair('ingame'), 'mc': load_pair('mc')}
    chars = set()
    for m in maps.values():
        for k in m.values():
            for c in unesc(k):
                if 0xAC00 <= ord(c) <= 0xD7A3:
                    chars.add(c)
                elif (ord(c) > 0x7e and c != '\xae') or (ord(c) < 0x20 and c != '\n'):
                    raise SystemExit('지원하지 않는 문자 %r in %r' % (c, k))
    chars = sorted(chars)
    kidx = {c: i for i, c in enumerate(chars)}
    print('음절', len(chars))

    def enc(s):
        return b''.join(kfont.code_of(kidx[c]) if c in kidx else c.encode('latin-1') for c in unesc(s)) + b'\0'

    changes = {}
    for name, (src, others) in (('ingame', INGAME), ('mc', MC)):
        en_items = parse(w.get(src))
        ko = [maps[name].get(esc(s)) for h, s in en_items]
        for idx in (src,) + others:
            items = parse(w.get(idx))
            assert len(items) == len(en_items)
            changes[idx] = tbuild([(h, enc(k) if k else s) for (h, s), k in zip(items, ko)])
        print(name, '번역 %d/%d' % (sum(1 for k in ko if k), len(ko)))

    for idx in menutex.wads():                                               # 메뉴 그림 글자
        changes[idx] = menutex.patch(idx, w.get(idx))
    for idx in menutex.LOADING:                                              # 로딩 화면 글자
        changes[idx] = menutex.patch_loading(w.get(idx))
    fonts = {}
    for name, L, ti, fi in (('big', kfont.BIG, TEX_BIG, FONT_BIG), ('small', kfont.SMALL, TEX_SMALL, FONT_SMALL)):
        tex, glyphs, p, prev = kfont.render(L, w.get(ti), chars)
        changes[ti] = tex
        changes[fi] = kfont.fif_clean(w.get(fi), L['norig'])
        fonts[name] = (p, glyphs)
        os.makedirs(os.path.join(ROOT, 'work'), exist_ok=True)
        kfont.preview(prev, os.path.join(ROOT, 'work', 'tex_%s.png' % name))
        print(name, '캐시 칸', p['cap'], '저장소', len(glyphs))

    r = isowrite.find_elf(f)
    elf, syms = elfpatch.patch(r, fonts, tempfile.mkdtemp())
    movies = movie_sub.patched()                                              # 자막 입힌 동영상(미리 movie_sub.py 로 인코딩)
    print('동영상', len(movies))
    isowrite.build(out, changes, elf, raw=movies)


if __name__ == '__main__':
    main()
