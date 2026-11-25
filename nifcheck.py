import struct, sys, os

class R:
    def __init__(self, data):
        self.d = data; self.o = 0
        self.strings = []
    def u8(self):
        v = self.d[self.o]; self.o += 1; return v
    def u16(self):
        v = struct.unpack_from('<H', self.d, self.o)[0]; self.o += 2; return v
    def u32(self):
        v = struct.unpack_from('<I', self.d, self.o)[0]; self.o += 4; return v
    def u64(self):
        v = struct.unpack_from('<Q', self.d, self.o)[0]; self.o += 8; return v
    def f32(self):
        v = struct.unpack_from('<f', self.d, self.o)[0]; self.o += 4; return v
    def s(self):
        n = self.u32()
        raw = self.d[self.o:self.o+n]; self.o += n
        return raw.decode('cp1252', 'replace')
    def sref(self, i):
        if i < len(self.strings):
            return self.strings[i]
        s = self.s()
        self.strings.append(s)
        return s
    def ref(self):
        return self.u32()

def parse(path):
    d = open(path, 'rb').read()
    r = R(d)
    magic = d.split(b'\n', 1)[0].decode('ascii', 'replace')
    r.o = len(magic) + 1
    version = r.u32()
    endian = r.u8()
    userver = r.u32()
    num_blocks = r.u32()
    bs_version = r.u32() if version >= 0x14020007 else 0
    # header strings
    for _ in range(3):
        r.strings.append(r.s())
    ntypes = r.u16()
    type_idx = [r.u32() for _ in range(ntypes)]
    types = [r.sref(i) for i in type_idx]
    block_type = [types[r.u16()] for _ in range(num_blocks)]
    if bs_version >= 100:
        sizes = [r.u32() for _ in range(num_blocks)]
    else:
        sizes = [0]*num_blocks
    blocks = []
    off = r.o
    for i, sz in enumerate(sizes):
        blocks.append(off); off += sz
    return dict(data=d, r=r, version=version, userver=userver, bs=bs_version,
                num=num_blocks, types=block_type, sizes=sizes, offs=blocks,
                strings=r.strings, hdr=r.strings[:3])

def sref_at(r, idx, d, off):
    """Read a string ref located at absolute offset off; idx is the reference value."""
    if idx < len(r.strings):
        return r.strings[idx]
    save = r.o
    r.o = off
    s = r.s()
    r.strings.append(s)
    r.o = save
    return s

def analyze(path):
    g = parse(path)
    d = g['data']; r = g['r']
    out = {'file': path, 'version': hex(g['version']), 'blocks': g['num'],
           'strings_head': g['hdr'], 'size': len(d)}
    from collections import Counter
    cnt = Counter(g['types'])
    out['blocktypes'] = dict(cnt)
    skin = []
    for i, t in enumerate(g['types']):
        if t == 'BSDismemberSkinInstance':
            r.o = g['offs'][i]
            data_ref = r.ref(); part_ref = r.ref(); skel = r.ref(); nb = r.u32()
            bones = [r.ref() for _ in range(nb)]
            nparts = r.u32()
            parts = [(r.u16(), r.u16()) for _ in range(nparts)]
            skin.append({'block': i, 'size': g['sizes'][i], 'numBones': nb,
                         'boneRefs': bones, 'numPartitions': nparts, 'parts': parts,
                         'skeletonRoot': skel, 'skinData': data_ref, 'partition': part_ref})
    out['dismember'] = skin
    # NiSkinPartition counts
    sp = []
    for i, t in enumerate(g['types']):
        if t == 'NiSkinPartition':
            r.o = g['offs'][i]
            n = r.u32()
            ps = []
            for _ in range(n):
                nv = r.u16(); nt = r.u16(); nbn = r.u16(); wpv = r.u16()
                ps.append({'verts': nv, 'tris': nt, 'bones': nbn, 'weightsPerVertex': wpv})
                # skip bone refs + weights to keep going is complex; just record and stop
                break
            sp.append({'block': i, 'numPartitions': n, 'first': ps[0] if ps else None})
    out['skpart'] = sp
    return out

for p in sys.argv[1:]:
    try:
        print(p)
        a = analyze(p)
        print('  version', a['version'], 'blocks', a['blocks'], 'size', a['size'])
        print('  header strings', a['strings_head'])
        print('  blocktypes', a['blocktypes'])
        for s in a['dismember']:
            print('  BSDismember block', s['block'], 'numBones', s['numBones'],
                  'partitions', s['numPartitions'], s['parts'], 'size', s['size'])
        for s in a['skpart']:
            print('  NiSkinPartition block', s['block'], 'n', s['numPartitions'], s['first'])
    except Exception as e:
        print('  ERR', type(e).__name__, e)
