"""번역 원문표 생성: translation/{ingame,mc}_en.txt (중복 제거한 영어 원문, 한 줄에 하나, 줄바꿈은 \\n)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wadlib import *
from textfile import parse

OUT = os.path.join(ROOT, 'translation')


def esc(b):
    s = b.rstrip(b'\0').decode('latin-1')
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def unesc(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            out.append({'n': '\n', 't': '\t', '\\': '\\'}.get(n, '\\' + n)); i += 2
        else:
            out.append(c); i += 1
    return ''.join(out)


if __name__ == '__main__':
    f = open(ISO_IN, 'rb'); w = Wad(f)
    for name, idx in (('ingame', 13), ('mc', 15)):
        seen = []
        for h, s in parse(w.get(idx)):
            e = esc(s)
            if e not in seen:
                seen.append(e)
        open(os.path.join(OUT, name + '_en.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(seen) + '\n')
        print(name, len(seen))
    for i in (11, 12, 13, 14, 15, 16, 18, 19):
        print(i, len(parse(w.get(i))))
