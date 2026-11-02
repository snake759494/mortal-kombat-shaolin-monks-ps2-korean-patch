import struct
def parse(d):
  n,=struct.unpack_from('<I',d,0);p=4;out=[]
  for i in range(n):
    h,l=struct.unpack_from('<II',d,p);p+=8
    out.append((h,d[p:p+l]));p+=l
  assert p==len(d),(p,len(d))
  return out
def build(items):
  b=struct.pack('<I',len(items))
  for h,s in items: b+=struct.pack('<II',h,len(s))+s
  return b
