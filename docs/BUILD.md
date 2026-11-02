# 재빌드

## 준비물

- 원본 ISO `Mortal Kombat - Shaolin Monks (USA).iso` (README의 해시와 일치해야 함)를 저장소 루트에 둡니다.
- Python 3.13, `Pillow`, `numpy`, `pycdlib`, `ziglang`(MIPS 코드 컴파일·링크), `av`·`imageio-ffmpeg`(동영상 자막)
- 동영상 받아쓰기를 다시 할 때만 `faster-whisper` (`tools/movie_asr.py`)
- 글꼴(`docs/FONT_CREDITS.md`): `SeoulHangangEB.ttf`, `NanumSquareNeo-cBd.ttf`(저장소 루트), `fonts/Galmuri11.ttf`
- xdelta3 (배포 파일을 만들 때만)

## 빌드

```powershell
python tools/movie_sub.py      # 동영상 6편 자막 인코딩 → work/movie/enc/*.SFD (수십 분)
python tools/build.py          # → Mortal Kombat - Shaolin Monks (USA) [Korean].iso
```

`build.py`는 원본 ISO에서 필요한 파일을 직접 읽습니다. 동영상은 `work/movie/enc`에 인코딩된 것만 넣습니다. 동영상 인코딩은 ffmpeg 버전에 따라 결과 바이트가 달라질 수 있어, 결과 ISO 해시가 `release_manifest.json`과 다를 수 있습니다(동영상 이외 부분은 같아야 합니다).

## 배포 파일

```powershell
xdelta3 -e -0 -s "Mortal Kombat - Shaolin Monks (USA).iso" "Mortal Kombat - Shaolin Monks (USA) [Korean].iso" Mortal_Kombat_Shaolin_Monks_KO_v1.0.xdelta
```

## 와이드 패치

한글패치는 실행파일 `SLUS_210.87`을 고치므로 게임 CRC(실행파일을 4바이트 단위로 XOR한 값, `tools/emu.py`의 `elf_crc`)가 원본 `455DD546`에서 `0FFD59AD`로 바뀝니다. 새 빌드에서 실행파일이 바뀌면 CRC를 다시 계산해 `patches/SLUS-21087_<CRC>.pnach`의 이름을 맞추고, 패치 주소(`004f4b38`, `00322f2c`, `00272210`, `00272498`)의 원래 값이 그대로인지 확인합니다. 새 빌드를 릴리즈할 때는 와이드 패치도 항상 함께 첨부합니다.

## 번역 추가

- 게임 문자열: `translation/ingame_en.txt`와 `ingame_ko.txt`가 줄 단위로 대응합니다(`\n` = 줄바꿈). `ko_001~006.txt`는 작업 단위 원고이며 `tools/merge_ko.py`로 `ingame_ko.txt`에 합칩니다.
- 메모리 카드 안내: `mc_en.txt` / `mc_ko.txt`
- 동영상 자막: `translation/movie/<이름>.tsv`에 `시작초<TAB>끝초<TAB>자막`(`\n` = 줄바꿈, `#` = 주석)
