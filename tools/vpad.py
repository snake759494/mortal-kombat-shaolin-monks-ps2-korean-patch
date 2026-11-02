"""테스트 전용 가상 패드(배포 안 함): PINE 으로 VPAD 에 버튼 마스크를 쓰면 게임이 눌린 것으로 인식.
후크: 0x273400 (shellPad 버튼 nor 직후 andi) → CAVE 에서 VPAD OR.
마스크: SELECT=0x100 START=0x800 U=0x1000 R=0x2000 D=0x4000 L=0x8000 L2=1 R2=2 L1=4 R1=8 T=0x10 O=0x20 X=0x40 S=0x80"""
import socket, struct, sys, time
VPAD = 0x000ff000; CAVE = 0x000ff100
BTN = dict(SELECT=0x100, START=0x800, U=0x1000, R=0x2000, D=0x4000, L=0x8000, L2=1, R2=2, L1=4, R1=8, T=0x10, O=0x20, X=0x40, S=0x80)
PORT = 28311
def j(a): return (2 << 26) | (a >> 2)
def section():
    hi = 0x3c010000 | ((VPAD + 0x8000) >> 16); lo = 0x8c210000 | (VPAD & 0xffff)
    c1 = [0x00021200, 0x00441027, hi, lo, 0x00411025, j(0x212608), 0]          # sll v0,8; nor v0,v0,a0
    c2 = [0x00021200, 0x00461027, hi, lo, 0x00411025, j(0x212a40), 0]          # sll v0,8; nor v0,v0,a2
    out = ["gametitle=MK Shaolin Monks (dev vpad)"]
    for base, code in ((CAVE, c1), (CAVE + 0x40, c2)):
        out += ['patch=1,EE,%08x,word,%08x' % (base + 4*i, c) for i, c in enumerate(code)]
    out += ['patch=1,EE,00212600,word,%08x' % j(CAVE), 'patch=1,EE,00212604,word,00000000',
            'patch=1,EE,00212a38,word,%08x' % j(CAVE + 0x40), 'patch=1,EE,00212a3c,word,00000000']
    return '\n'.join(out) + '\n'
def pine(payload):
    s = socket.create_connection(('127.0.0.1', PORT), timeout=10)
    s.sendall(struct.pack('<I', len(payload) + 4) + payload)
    def rv(n):
        b = b''
        while len(b) < n:
            c = s.recv(n - len(b))
            if not c: raise EOFError
            b += c
        return b
    n = struct.unpack('<I', rv(4))[0]; body = rv(n - 4); s.close(); return body
def w32(a, v): return pine(struct.pack('<BII', 6, a, v))
def r32(a): return struct.unpack_from('<I', pine(struct.pack('<BI', 2, a)), 1)[0]
def rd(a, n):
    out = bytearray()
    for k in range(0, n, 8): out += pine(struct.pack('<BI', 3, a + k))[1:9]
    return bytes(out[:n])
def press(names, ms=200):
    m = 0
    for n in names.split('+'): m |= BTN[n]
    w32(VPAD, m); time.sleep(ms / 1000); w32(VPAD, 0); time.sleep(0.15)
if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'press':
        for k in sys.argv[2:]:
            try: time.sleep(float(k))
            except ValueError: press(k)
    elif c == 'hold': press(sys.argv[2], int(sys.argv[3]))
    elif c == 'save': print(pine(struct.pack('<BB', 9, int(sys.argv[2]))))
    elif c == 'load': print(pine(struct.pack('<BB', 0xa, int(sys.argv[2]))))
