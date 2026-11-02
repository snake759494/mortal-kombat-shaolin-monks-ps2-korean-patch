"""동영상 영어 음성 받아쓰기(faster-whisper, 받아쓰기만 — 번역은 직접) → work/movie/asr/<이름>.txt"""
import os, sys, numpy as np, av
from faster_whisper import WhisperModel
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = os.path.join(ROOT, 'work', 'movie')


def audio(path, track=0):
    c = av.open(path); s = [x for x in c.streams if x.type == 'audio'][track]
    rs = av.AudioResampler(format='s16', layout='mono', rate=16000); out = []
    for p in c.demux(s):
        for fr in p.decode():
            for r in rs.resample(fr): out.append(r.to_ndarray().ravel())
    c.close()
    return np.concatenate(out).astype(np.float32) / 32768


if __name__ == '__main__':
    os.makedirs(os.path.join(M, 'asr'), exist_ok=True)
    m = WhisperModel(os.environ.get('ASR_MODEL', 'medium'), device='cpu', compute_type='int8', cpu_threads=4)
    for n in sys.argv[1:]:
        a = audio(os.path.join(M, 'orig', n + '.SFD'))
        segs, _ = m.transcribe(a, language='en', vad_filter=True, word_timestamps=False)
        with open(os.path.join(M, 'asr', n + '.txt'), 'w', encoding='utf-8') as f:
            for s in segs: f.write('%.2f\t%.2f\t%s\n' % (s.start, s.end, s.text.strip()))
        print(n, 'done', flush=True)
