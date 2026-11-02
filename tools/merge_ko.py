"""translation/ko_00N.txt 조각 → translation/ingame_ko.txt (원문 ingame_en.txt 와 줄 대응) 합치기·검사

ko_001~004: 1~700줄 순서대로, ko_005·006: '줄번호<TAB>번역'. 기호뿐인 줄은 빈 줄(원문 유지),
(PH) 페이탈리티 자리표시는 자동 번역.
"""
import os, re, sys

T = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'translation')
SYMS = '=^$#*~|{}<>@`]\\'
NAMES = {'Sub-Zero': '서브제로', 'Scorpion': '스콜피온', 'Baraka': '바라카', 'Reptile': '렙타일', 'Kitana': '키타나',
         'Johnny Cage': '조니 케이지', 'Liu Kang': '리우 캉', 'Kung Lao': '쿵 라오'}


def rd(n):
    return open(os.path.join(T, n), encoding='utf-8').read().split('\n')


en = rd('ingame_en.txt')[:-1]
ko = []
for f in ('ko_001', 'ko_002', 'ko_003', 'ko_004'):
    ko += rd(f + '.txt')[:-1]
assert len(ko) == 700, len(ko)
ko += [''] * (len(en) - 700)
for i in range(700, len(en)):
    m = re.fullmatch(r'\(PH\) (.+) lvl (\d) Fatality \((\d+)\)( Inputs)?', en[i])
    if m:
        ko[i] = '(PH) %s 레벨 %s 페이탈리티 (%s)%s' % (NAMES[m[1]], m[2], m[3], ' 입력' if m[4] else '')
for f in ('ko_005', 'ko_006'):
    for l in rd(f + '.txt'):
        if l:
            n, t = l.split('\t', 1)
            assert not ko[int(n) - 1], n
            ko[int(n) - 1] = t
bad = 0
for i, (e, k) in enumerate(zip(en, ko)):
    if not k:
        continue
    if re.findall(r'%[sd]', e) != re.findall(r'%[sd]', k):
        print('서식', i + 1, e, k); bad += 1
    if sorted(c for c in e if c in SYMS) != sorted(c for c in k if c in SYMS):
        print('기호', i + 1, repr(e), repr(k)); bad += 1
miss = [i + 1 for i, k in enumerate(ko) if not k and not re.fullmatch(r'[{}<>*~|^ ]*', en[i])]
print('빠짐', miss, '문제', bad)
open(os.path.join(T, 'ingame_ko.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(ko) + '\n')
