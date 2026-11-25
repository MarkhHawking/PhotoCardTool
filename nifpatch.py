# -*- coding: utf-8 -*-
"""NIF 块/字符串级修补：改写贴图集路径、字符串表里的 XML 路径。

只做“读出全部块 -> 替换指定块 / 指定字符串 -> 重拼头部与块数据”。
"""
import struct

MAGIC_LINE = b'Gamebryo File Format, Version 20.2.0.7\n'


def read_header(b):
    o = b.index(b'\n') + 1
    magic = b[:o]
    version = struct.unpack_from('<I', b, o)[0]; o += 4
    endian = b[o]; o += 1
    userver = struct.unpack_from('<I', b, o)[0]; o += 4
    nb = struct.unpack_from('<I', b, o)[0]; o += 4
    bsv = struct.unpack_from('<I', b, o)[0]; o += 4
    hs = []
    for _ in range(3):
        L = b[o]; o += 1
        hs.append(b[o:o + L - 1]); o += L
    nt = struct.unpack_from('<H', b, o)[0]; o += 2
    types = []
    for _ in range(nt):
        L = struct.unpack_from('<I', b, o)[0]; o += 4
        types.append(b[o:o + L]); o += L
    ti = list(struct.unpack_from('<' + 'H' * nb, b, o)); o += 2 * nb
    sizes = list(struct.unpack_from('<' + 'I' * nb, b, o)); o += 4 * nb
    nstr = struct.unpack_from('<I', b, o)[0]; o += 4
    maxlen = struct.unpack_from('<I', b, o)[0]; o += 4
    strings = []
    for _ in range(nstr):
        L = struct.unpack_from('<I', b, o)[0]; o += 4
        strings.append(b[o:o + L]); o += L
    ngroups = struct.unpack_from('<I', b, o)[0]; o += 4
    start = o
    offs = []
    x = start
    for s in sizes:
        offs.append(x); x += s
    return dict(magic=magic, version=version, endian=endian, userver=userver, nb=nb, bsv=bsv,
                hstrings=hs, types=types, ti=ti, sizes=sizes, strings=strings,
                ngroups=ngroups, start=start, offsets=offs, total=len(b), tail=b[x:])


def load(path):
    b = open(path, 'rb').read()
    h = read_header(b)
    blocks = [b[o:o + s] for o, s in zip(h['offsets'], h['sizes'])]
    return dict(path=path, h=h, blocks=blocks)


def type_name(h, i):
    return h['types'][h['ti'][i]].decode('latin1')


def build_header(h, sizes, strings):
    out = bytearray()
    out += h['magic'] or MAGIC_LINE
    out += struct.pack('<I', h['version'])
    out += bytes([h['endian']])
    out += struct.pack('<I', h['userver'])
    out += struct.pack('<I', h['nb'])
    out += struct.pack('<I', h['bsv'])
    for s in h['hstrings']:
        out += bytes([len(s) + 1]) + s + b'\x00'
    out += struct.pack('<H', len(h['types']))
    for t in h['types']:
        out += struct.pack('<I', len(t)) + t
    out += struct.pack('<' + 'H' * h['nb'], *h['ti'])
    out += struct.pack('<' + 'I' * h['nb'], *sizes)
    out += struct.pack('<I', len(strings))
    ml = max([len(s) for s in strings] + [0])
    out += struct.pack('<I', ml)
    for s in strings:
        out += struct.pack('<I', len(s)) + s
    out += struct.pack('<I', h['ngroups'])
    return bytes(out)


def save(doc, path, blocks=None, strings=None):
    h = doc['h']
    blocks = blocks if blocks is not None else doc['blocks']
    strings = strings if strings is not None else h['strings']
    sizes = [len(b) for b in blocks]
    head = build_header(h, sizes, strings)
    data = head + b''.join(blocks) + h['tail']
    open(path, 'wb').write(data)
    return path


# ---------- texset ----------
def texset_items(blk):
    n = struct.unpack_from('<i', blk, 0)[0]
    q = 4
    items = []
    for _ in range(n):
        L = struct.unpack_from('<I', blk, q)[0]; q += 4
        items.append(blk[q:q + L]); q += L
    return items


def build_texset(items):
    out = bytearray(struct.pack('<i', len(items)))
    for it in items:
        out += struct.pack('<I', len(it)) + it
    return bytes(out)


def rewrite_texsets(doc, mapping):
    """mapping: 小写旧路径(bytes) -> 新路径(str)"""
    changed = 0
    h = doc['h']
    for i, blk in enumerate(doc['blocks']):
        if type_name(h, i) != 'BSShaderTextureSet':
            continue
        items = texset_items(blk)
        new_items = []
        hit = False
        for it in items:
            key = it.rstrip(b'\x00').lower()
            if key in mapping:
                new_items.append(mapping[key].encode('latin1') + b'\x00')
                hit = True
            else:
                new_items.append(it)
        if hit:
            doc['blocks'][i] = build_texset(new_items)
            changed += 1
    return changed


def rewrite_strings(doc, pred, new_value):
    """pred(bytes) -> bool；把匹配的字符串表项替换。"""
    strings = list(doc['h']['strings'])
    changed = 0
    for i, s in enumerate(strings):
        key = s.rstrip(b'\x00')
        if pred(key):
            strings[i] = new_value.encode('latin1') + b'\x00'
            changed += 1
    if changed:
        doc['h']['strings'] = strings
    return changed


def xml_strings(doc):
    out = []
    for s in doc['h']['strings']:
        k = s.rstrip(b'\x00')
        if k.lower().endswith(b'.xml'):
            out.append(k.decode('latin1'))
    return out


def texset_paths(doc):
    out = []
    for i, blk in enumerate(doc['blocks']):
        if type_name(doc['h'], i) != 'BSShaderTextureSet':
            continue
        for it in texset_items(blk):
            p = it.rstrip(b'\x00').decode('latin1')
            if p:
                out.append(p)
    return out
