import struct

def read_header(b):
    o = b.index(b'\n') + 1
    version = struct.unpack_from('<I', b, o)[0]; o += 4
    endian = b[o]; o += 1
    userver = struct.unpack_from('<I', b, o)[0]; o += 4
    nb = struct.unpack_from('<I', b, o)[0]; o += 4
    bsv = struct.unpack_from('<I', b, o)[0]; o += 4
    hstrings = []
    for _ in range(3):
        L = b[o]; o += 1
        hstrings.append(b[o:o+L-1].decode('latin1')); o += L
    nt = struct.unpack_from('<H', b, o)[0]; o += 2
    types = []
    for _ in range(nt):
        L = struct.unpack_from('<I', b, o)[0]; o += 4
        types.append(b[o:o+L].decode('latin1')); o += L
    ti = list(struct.unpack_from('<' + 'H'*nb, b, o)); o += 2*nb
    sizes = list(struct.unpack_from('<' + 'I'*nb, b, o)); o += 4*nb
    nstr = struct.unpack_from('<I', b, o)[0]; o += 4
    maxlen = struct.unpack_from('<I', b, o)[0]; o += 4
    strings = []
    for _ in range(nstr):
        L = struct.unpack_from('<I', b, o)[0]; o += 4
        strings.append(b[o:o+L].decode('latin1')); o += L
    ngroups = struct.unpack_from('<I', b, o)[0]; o += 4
    start = o
    offs = []
    x = start
    for s in sizes:
        offs.append(x); x += s
    return dict(version=version, endian=endian, userver=userver, nb=nb, bsv=bsv,
                hstrings=hstrings, types=types, ti=ti, sizes=sizes, strings=strings,
                ngroups=ngroups, start=start, offsets=offs, total=len(b),
                tail=b[x:])

def tname(h, i):
    return h['types'][h['ti'][i]]

def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def i32(b, o): return struct.unpack_from('<i', b, o)[0]
def f32(b, o): return struct.unpack_from('<f', b, o)[0]

def parse_avobject(b, o):
    name = i32(b, o); o += 4
    nxt = u32(b, o); o += 4
    extras = [i32(b, o + 4*i) for i in range(nxt)]; o += 4*nxt
    ctrl = i32(b, o); o += 4
    flags = u32(b, o); o += 4
    trans = struct.unpack_from('<3f', b, o); o += 12
    rot = struct.unpack_from('<9f', b, o); o += 36
    scale = f32(b, o); o += 4
    coll = i32(b, o); o += 4
    return dict(name=name, extras=extras, ctrl=ctrl, flags=flags, trans=trans, rot=rot,
                scale=scale, coll=coll), o

def parse_node(b, off):
    d, o = parse_avobject(b, off)
    nch = u32(b, o); o += 4
    d['children'] = [i32(b, o + 4*i) for i in range(nch)]; o += 4*nch
    nef = u32(b, o); o += 4
    d['effects'] = [i32(b, o + 4*i) for i in range(nef)]; o += 4*nef
    d['consumed'] = o - off
    return d

ATTR_BITS = [(16, 'vertex'), (32, 'uv'), (128, 'normal'), (256, 'tangent'),
             (512, 'colors'), (1024, 'skin'), (4096, 'eye')]

def desc_attr(desc):
    return (desc >> 40) & 0xFFFF

def attr_stride(attr):
    s = 0
    if attr & 16: s += 12
    if attr & 16: s += 4
    if attr & 32: s += 4
    if attr & 128: s += 4
    if (attr & 128) and (attr & 256): s += 4
    if attr & 512: s += 4
    if attr & 1024: s += 12
    if attr & 4096: s += 4
    return s

def parse_tri_shape(b, off):
    d, o = parse_avobject(b, off)
    d['bound_center'] = struct.unpack_from('<3f', b, o); o += 12
    d['bound_radius'] = f32(b, o); o += 4
    d['skin'] = i32(b, o); o += 4
    d['shader'] = i32(b, o); o += 4
    d['alpha'] = i32(b, o); o += 4
    desc = struct.unpack_from('<Q', b, o)[0]; o += 8
    d['desc'] = desc
    d['attr'] = desc_attr(desc)
    d['has'] = [n for bit, n in ATTR_BITS if d['attr'] & bit]
    d['num_tris'] = struct.unpack_from('<H', b, o)[0]; o += 2
    d['num_verts'] = struct.unpack_from('<H', b, o)[0]; o += 2
    d['data_size'] = u32(b, o); o += 4
    d['stride'] = attr_stride(d['attr'])
    d['vertex_off'] = o
    d['tris_off'] = o + d['num_verts'] * d['stride']
    d['end'] = d['tris_off'] + d['num_tris'] * 6
    d['consumed'] = d['end'] - off + 4
    return d

def read_vertices(b, sh):
    off = sh['vertex_off']; stride = sh['stride']; attr = sh['attr']
    out = []
    for i in range(sh['num_verts']):
        p = off + i*stride
        pos = struct.unpack_from('<3f', b, p); q = p + 12
        if attr & 16: q += 4
        uv = struct.unpack_from('<2e', b, q) if attr & 32 else None
        if attr & 32: q += 4
        nrm = None
        if attr & 128:
            nx, ny, nz, s = struct.unpack_from('<3bB', b, q); q += 4
            nrm = (nx/127.0, ny/127.0, nz/127.0, s)
            if attr & 256: q += 4
        out.append((pos, uv, nrm))
    return out

def read_triangles(b, sh):
    return [struct.unpack_from('<3H', b, sh['tris_off'] + 6*i) for i in range(sh['num_tris'])]

def parse_skin_partition(b, off, userver):
    o = off
    numP = u32(b, o); o += 4
    dataSize = u32(b, o); o += 4
    vSize = u32(b, o); o += 4
    desc = struct.unpack_from('<Q', b, o)[0]; o += 8
    attr = desc_attr(desc)
    vcount = dataSize // vSize if vSize else 0
    vstart = o
    o += dataSize
    parts = []
    for _ in range(numP):
        nv, nt, nb, ns, nw = struct.unpack_from('<5H', b, o); o += 10
        bones = struct.unpack_from('<'+'H'*nb, b, o); o += 2*nb
        hm = b[o]; o += 1
        vmap = struct.unpack_from('<'+'H'*nv, b, o) if hm else None
        if hm: o += 2*nv
        hw = b[o]; o += 1
        if hw: o += 4*nv*nw
        o += 2*ns
        hf = b[o]; o += 1
        tris = None
        if ns == 0:
            tris = struct.unpack_from('<'+'H'*(3*nt), b, o); o += 6*nt
        else:
            o += 2*sum(struct.unpack_from('<'+'H'*ns, b, off+0))
        hb = b[o]; o += 1
        if hb: o += nv*nw
        o += 2
        pdesc = struct.unpack_from('<Q', b, o)[0]; o += 8
        trisCopy = struct.unpack_from('<'+'H'*(3*nt), b, o); o += 6*nt
        parts.append(dict(nv=nv, nt=nt, nb=nb, nw=nw, bones=bones, vmap=vmap, tris=tris, trisCopy=trisCopy, desc=pdesc))
    return dict(vstart=vstart, vcount=vcount, vSize=vSize, desc=desc, attr=attr, parts=parts, end=o, consumed=o-off)

def partition_geometry(b, ps):
    """return (positions list, uvs list, triangles list) from a parsed NiSkinPartition"""
    attr = ps['attr']; stride = ps['vSize']; base = ps['vstart']
    pos = []
    uvs = []
    for i in range(ps['vcount']):
        p = base + i*stride
        pos.append(struct.unpack_from('<3f', b, p))
        q = p + 12 + 4  # skip bitangent X
        uv = struct.unpack_from('<2e', b, q)
        uvs.append(uv)
    tris = []
    for pt in ps['parts']:
        tris.extend(pt['tris'])
    return pos, uvs, tris
