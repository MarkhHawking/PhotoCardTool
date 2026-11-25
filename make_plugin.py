import struct, os, esp

SRC = 'work/yundao/YunDao_Hdt_Hair.esp'
OUT = 'work/out/YunDao_Tiantian_GND.esp'
STYLE = 'skyblack'
NEW_MOD4 = ('YunDao_Hdt\\GND\\%s.nif' % STYLE).encode('latin1') + b'\x00'

b = open(SRC, 'rb').read()
t0 = esp.top_records(b)[0]
subs = esp.subrecords(b, t0['data_off'], t0['end'])
hedr = struct.pack('<fII', 1.7, 1, 0x01001DE3)
cnam = [s['data'] for s in subs if s['type'] == b'CNAM'][0]
intv = [s['data'] for s in subs if s['type'] == b'INTV']
masters = [s['data'][:-1].decode('ascii') for s in subs if s['type'] == b'MAST']
print('template masters', masters, 'hedr', hedr.hex(' '), 'cnam', cnam.hex(' '))

armo = esp.recs_in_group(b, b'ARMO')
hit = [r for r in armo if b'YunDao_Hdt\\Hair\\' + STYLE.encode() + b'.nif' in b[r['data_off']:r['end']]]
assert len(hit) == 1, len(hit)
r = hit[0]
print('armo', hex(r['fid']), 'size', r['size'])

new_data = b''
for s in esp.subrecords(b, r['data_off'], r['end']):
    if s['type'] == b'MOD4':
        new_data += b'MOD4' + struct.pack('<H', len(NEW_MOD4)) + NEW_MOD4
    elif s['type'] == b'MO4T':
        continue
    else:
        new_data += s['type'] + struct.pack('<H', s['size']) + s['data']

all_masters = []
for m in masters:
    all_masters.append(m)
if 'YunDao_Hdt_Hair.esp' not in all_masters:
    all_masters.append('YunDao_Hdt_Hair.esp')

tes4 = b''
tes4 += b'HEDR' + struct.pack('<H', len(hedr)) + hedr
tes4 += b'CNAM' + struct.pack('<H', len(cnam)) + cnam
for m in all_masters:
    mb = m.encode('ascii') + b'\x00'
    tes4 += b'MAST' + struct.pack('<H', len(mb)) + mb
    tes4 += b'DATA' + struct.pack('<H', 8) + b'\x00' * 8
if intv:
    tes4 += b'INTV' + struct.pack('<H', len(intv[0])) + intv[0]

rec = esp.build_record(b'ARMO', r['fid'], 0, new_data, vc=0, fver=44)
grup = esp.build_grup(b'ARMO', rec)
out = esp.build_record(b'TES4', 0, 0, tes4, vc=0, fver=44) + grup
os.makedirs('work/out', exist_ok=True)
open(OUT, 'wb').write(out)
print('wrote', OUT, len(out), 'bytes')

# validate
b2 = open(OUT, 'rb').read()
t2 = esp.top_records(b2)[0]
s2 = esp.subrecords(b2, t2['data_off'], t2['end'])
print('masters', [s['data'][:-1].decode() for s in s2 if s['type'] == b'MAST'])
g = esp.recs_in_group(b2, b'ARMO')
print('armo count', len(g), 'fid', hex(g[0]['fid']), 'flags', hex(g[0]['flags']))
for s in esp.subrecords(b2, g[0]['data_off'], g[0]['end']):
    if s['type'] in (b'EDID', b'FULL', b'MOD4', b'MO4T', b'MODL'):
        print(' ', s['type'], repr(s['data']))
