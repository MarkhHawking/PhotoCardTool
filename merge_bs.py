import struct, os, sys
sys.path.insert(0, '.')
import nif, gend

BODY = r'D:/Modding/MO2/mods/Baka Haeun UNP（BHUNP）/CalienteTools/BodySlide/ShapeData/BHUNP 3BBB Advanced/BHUNP 3BBB Advanced Ver 2.nif'
HAIR = 'work/yundao/meshes/YunDao_Hdt/Hair/tiantianblack.nif'
V7 = 'work/out/YunDao_Tiantian_v7/Meshes/YunDao_Hdt/GND/tiantianblack.nif'
OUT = 'work/out/bsbody'
TEX0 = 'Textures\\YunDao_Hdt\\Hair\\tiantian.dds'
TEX1 = 'Textures\\YunDao_Hdt\\Hair\\tiantian_n.dds'

def hair_geo(path):
    b = open(path, 'rb').read(); h = nif.read_header(b)
    shapes = [i for i in range(h['nb']) if nif.tname(h, i) == 'BSTriShape']
    parts = [i for i in range(h['nb']) if nif.tname(h, i) == 'NiSkinPartition']
    pos, uvs, tris, seen = [], [], [], set()
    picked = []
    for si in shapes:
        d, _ = nif.parse_avobject(b, h['offsets'][si]); nm = h['strings'][d['name']]
        if not nm.lower().startswith('hair'):
            continue
        part = min([p for p in parts if p > si])
        ps = nif.parse_skin_partition(b, h['offsets'][part], h['userver'])
        p, u, t = nif.partition_geometry(b, ps)
        sig = (len(p), tuple(round(x, 2) for x in p[0]), tuple(round(x, 2) for x in p[len(p)//2]))
        picked.append((nm, part, len(p), len(t)//3, sig in seen))
        if sig in seen:
            continue
        seen.add(sig)
        base = len(pos); pos.extend(p); uvs.extend(u); tris.extend(base + x for x in t)
    return pos, uvs, tris, picked

pos, uvs, tris, picked = hair_geo(HAIR)
print('picked', picked, 'total', len(pos), len(tris)//3)
xs=[p[0] for p in pos]; ys=[p[1] for p in pos]; zs=[p[2] for p in pos]
cx, cy, minz = (min(xs)+max(xs))/2.0, (min(ys)+max(ys))/2.0, min(zs)
print('restore offset', round(cx,3), round(cy,3), round(minz,3))

gend.build_gnd('hair', pos, uvs, tris, TEX0, TEX1, process='', author='', out='work/tmp_hair_gnd.nif')
g = open('work/tmp_hair_gnd.nif','rb').read(); gh = nif.read_header(g)
gi = {nif.tname(gh,i): i for i in range(gh['nb'])}
shape_i = gi['BSTriShape']
shape = bytearray(g[gh['offsets'][shape_i]:gh['offsets'][shape_i]+gh['sizes'][shape_i]])

v7 = open(V7,'rb').read(); vh = nif.read_header(v7); vi = {nif.tname(vh,i): i for i in range(vh['nb'])}
si = vi['BSLightingShaderProperty']; ti_ = vi['BSShaderTextureSet']
sh = bytearray(v7[vh['offsets'][si]:vh['offsets'][si]+vh['sizes'][si]])
tx = bytearray(v7[vh['offsets'][ti_]:vh['offsets'][ti_]+vh['sizes'][ti_]])
print('blocks shape/shader/tex', len(shape), len(sh), len(tx))

shp = nif.parse_tri_shape(bytes(shape), 0)
vo, stride, nv = shp['vertex_off'], shp['stride'], shp['num_verts']
assert stride == 28
for i in range(nv):
    o = vo + i*stride
    x, y, z = struct.unpack_from('<3f', shape, o)
    struct.pack_into('<3f', shape, o, x + cx, y + cy, z + minz)
bcx, bcy, bcz = (min(xs)+max(xs))/2.0, (min(ys)+max(ys))/2.0, (minz+max(zs))/2.0
rad = ((max(xs)-min(xs))**2 + (max(ys)-min(ys))**2 + (max(zs)-minz)**2) ** 0.5 / 2.0
struct.pack_into('<3ff', shape, 72, bcx, bcy, bcz, rad)
print('shape', len(shape), 'V', nv, 'T', shp['num_tris'])

b = open(BODY, 'rb').read(); h = nif.read_header(b)
nb = h['nb']; types = h['types']; ti = h['ti']; sizes = h['sizes']; strings = h['strings']
def tindex(name):
    if name not in types:
        types.append(name)
    return types.index(name)
new_ti = [tindex('BSTriShape'), tindex('BSLightingShaderProperty'), tindex('BSShaderTextureSet')]
new_strings = strings + ['hair']
hair_str = len(new_strings) - 1
nb0 = bytearray(shape); nb1 = bytearray(sh)
struct.pack_into('<i', nb0, 0, hair_str)
struct.pack_into('<i', nb0, 88, -1)
struct.pack_into('<i', nb0, 92, nb + 1)
struct.pack_into('<i', nb0, 96, -1)
struct.pack_into('<i', nb1, 0, hair_str)
struct.pack_into('<i', nb1, 40, nb + 2)
new_blocks = [bytes(nb0), bytes(nb1), bytes(tx)]
root = bytearray(b[h['offsets'][0]:h['offsets'][0]+sizes[0]])
o = 72
nch = struct.unpack_from('<I', root, o)[0]
print('root children', nch)
new_root = bytearray(root[:o]) + struct.pack('<I', nch+1) + root[o+4:o+4+4*nch] + struct.pack('<i', nb) + root[o+4+4*nch:]
new_sizes = [len(new_root)] + sizes[1:] + [len(x) for x in new_blocks]
new_ti_all = list(ti) + new_ti
data = [bytes(new_root)] + [b[h['offsets'][i]:h['offsets'][i]+sizes[i]] for i in range(1, nb)] + new_blocks
total_nb = nb + 3
out = bytearray()
out += g[:g.index(b'\n') + 1]
out += struct.pack('<I', h['version']) + bytes([h['endian']]) + struct.pack('<I', h['userver']) + struct.pack('<I', total_nb) + struct.pack('<I', h['bsv'])
for s0 in h['hstrings']:
    sb = s0.encode('latin1'); out += bytes([len(sb)+1]) + sb + b'\x00'
out += struct.pack('<H', len(types))
for t in types:
    tb = t.encode('latin1'); out += struct.pack('<I', len(tb)) + tb
for x in new_ti_all: out += struct.pack('<H', x)
for s0 in new_sizes: out += struct.pack('<I', s0)
out += struct.pack('<I', len(new_strings)) + struct.pack('<I', max(len(s0) for s0 in new_strings))
for s0 in new_strings:
    sb = s0.encode('latin1'); out += struct.pack('<I', len(sb)) + sb
out += struct.pack('<I', 0)
for d0 in data: out += d0
out += b'\x01\x00\x00\x00\x00\x00\x00\x00'
d = OUT + '/CalienteTools/BodySlide/ShapeData/BHUNP 3BBB Advanced'
os.makedirs(d, exist_ok=True)
p = d + '/YunDao Tiantian Body.nif'
open(p, 'wb').write(out)
print('wrote', p, len(out), 'nb', total_nb)
bb = open(p,'rb').read(); hh = nif.read_header(bb)
print('verify nb', hh['nb'], 'start', hex(hh['start']), 'tail', len(hh['tail']), 'total', len(bb))
for i in range(hh['nb']):
    if nif.tname(hh,i) in ('BSTriShape','NiTriShape'):
        dd,_ = nif.parse_avobject(bb, hh['offsets'][i]); nm = hh['strings'][dd['name']]
        if nm.lower().startswith('hair'):
            t = nif.parse_tri_shape(bb, hh['offsets'][i])
            print('hair', i, nm, t['num_verts'], t['num_tris'], 'end==size', (t['end']-hh['offsets'][i]) == hh['sizes'][i])
