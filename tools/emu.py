"""테스트 전용: 작업 폴더의 포터블 PCSX2 를 백그라운드(최소화·비활성)로 실행/종료, 상태 저장으로 화면·RAM 획득"""
import subprocess, sys, os, time, glob, zipfile, struct, ctypes
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMU = os.path.join(R, 'work', 'emu'); PIDF = os.path.join(EMU, 'emu.pid')
sys.path.insert(0, os.path.dirname(__file__))
import vpad
def elf_crc(iso):
    import pycdlib
    i = pycdlib.PyCdlib(); i.open(iso); r = i.get_record(iso_path='/SLUS_210.87;1')
    with open(iso, 'rb') as f: f.seek(r.extent_location() * 2048); d = f.read(r.data_length)
    i.close(); c = 0
    for (x,) in struct.iter_unpack('<I', d[:len(d) // 4 * 4]): c ^= x
    return c
def launch(iso, state=None):
    crc = elf_crc(iso)
    os.makedirs(os.path.join(EMU, 'cheats'), exist_ok=True)
    open(os.path.join(EMU, 'cheats', '%08X.pnach' % crc), 'w').write(vpad.section())
    si = subprocess.STARTUPINFO(); si.dwFlags = 1; si.wShowWindow = 7   # SW_SHOWMINNOACTIVE
    args = [os.path.join(EMU, 'pcsx2-mk.exe'), '-batch', '-nogui']
    if state: args += ['-statefile', state]
    p = subprocess.Popen(args + ['--', os.path.abspath(iso)], cwd=EMU, startupinfo=si)
    open(PIDF, 'w').write(str(p.pid)); print('pid', p.pid)
    hide(p.pid)
def hide(pid):
    u = ctypes.windll.user32
    for _ in range(100):
        hs = []
        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(h, l):
            pp = ctypes.c_ulong(); u.GetWindowThreadProcessId(ctypes.c_void_p(h), ctypes.byref(pp))
            if pp.value == pid and u.IsWindowVisible(ctypes.c_void_p(h)): hs.append(h)
            return True
        u.EnumWindows(cb, 0)
        if hs:
            time.sleep(1.0)
            for h in hs: u.ShowWindow(ctypes.c_void_p(h), 7)
            return
        time.sleep(0.2)
def stop():
    if os.path.exists(PIDF):
        subprocess.run(['taskkill', '/F', '/PID', open(PIDF).read().strip()], capture_output=True); os.remove(PIDF)
def member(p, name):
    import zstandard
    with zipfile.ZipFile(p) as z: i = z.getinfo(name)
    with open(p, 'rb') as f:
        f.seek(i.header_offset); h = f.read(30); n, e = struct.unpack_from('<HH', h, 26); f.seek(n + e, 1)
        raw = f.read(i.compress_size)
    if i.compress_type == 0: return raw
    if i.compress_type == 93: return zstandard.ZstdDecompressor().decompress(raw, max_output_size=i.file_size)
    with zipfile.ZipFile(p) as z: return z.read(name)
def latest():
    ps = glob.glob(os.path.join(EMU, 'sstates', '*.p2s'))
    best = None; bt = -1
    for q in ps:
        try: t = os.path.getmtime(q)
        except OSError: continue
        if t > bt: best, bt = q, t
    return best
def snap(tag, slot=9):
    old = latest(); t = os.path.getmtime(old) if old else 0
    vpad.pine(struct.pack('<BB', 9, slot))
    for _ in range(300):
        p = latest()
        if p and os.path.exists(p) and os.path.getmtime(p) > t: time.sleep(1.0); break
        time.sleep(0.1)
    out = os.path.join(R, 'work', 'shot_%s.png' % tag)
    try: open(out, 'wb').write(member(p, 'Screenshot.png'))
    except KeyError: print('no screenshot member', zipfile.ZipFile(p).namelist())
    if '--ram' in sys.argv: open(os.path.join(R, 'work', 'ram_%s.bin' % tag), 'wb').write(member(p, 'eeMemory.bin'))
    if '--v' in sys.argv: print(out)
if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'launch': launch(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif c == 'stop': stop()
    elif c == 'snap': snap(sys.argv[2])
