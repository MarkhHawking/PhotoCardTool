# -*- coding: utf-8 -*-
"""盒子世界模型 + ESP 生成（PhotoCardTool 附属模块）。

功能：
  build_box(template, out, tex_lists)   改写模板 nif 的两组贴图集
  scan_esp(path)                        读出 ARMO/ARMA 记录（原始子记录）
  add_records(esp_path, entries, ...)   新建或追加 ARMO/ARMA，写回 ESP
"""
import os
import struct

MAGIC = b'Gamebryo File Format, Version 20.2.0.7\n'


# ---------------- NIF 重写 ----------------
def _rebuild_nif(h, blocks):
    out = bytearray()
    out += MAGIC
    out += struct.pack('<I', h['version'])
    out += bytes([h['endian']])
    out += struct.pack('<I', h['userver'])
    out += struct.pack('<I', len(blocks))
    out += struct.pack('<I', h['bsv'])
    for s in h['hstrings']:
        b = s.encode('ascii', 'replace')
        out += bytes([len(b)]) + b
    out += struct.pack('<H', len(h['types']))
    for t in h['types']:
        b = t.encode('ascii')
        out += struct.pack('<I', len(b)) + b
    for t in h['ti']:
        out += struct.pack('<H', t)
    for b in blocks:
        out += struct.pack('<I', len(b))
    strings = h['strings']
    out += struct.pack('<I', len(strings))
    out += struct.pack('<I', max([len(s) for s in strings] + [0]))
    for s in strings:
        b = s.encode('ascii', 'replace')
        out += struct.pack('<I', len(b)) + b
    out += struct.pack('<I', h['ngroups'])
    for b in blocks:
        out += b
    out += h.get('tail', b'') or b''
    return bytes(out)


def read_texset(b, off):
    n = struct.unpack_from('<I', b, off)[0]
    pos = off + 4
    out = []
    for _ in range(n):
        L = struct.unpack_from('<I', b, pos)[0]
        pos += 4
        out.append(b[pos:pos + L].decode('latin-1'))
        pos += L
    return out


def build_texset(items):
    out = struct.pack('<I', len(items))
    for s in items:
        raw = s.encode('latin-1')
        out += struct.pack('<I', len(raw)) + raw
    return out


def build_box(template_path, out_path, tex_repl):
    """tex_repl: {block_index: [9 paths]}"""
    import nif as N
    b = open(template_path, 'rb').read()
    h = N.read_header(b)
    blocks = [b[h['offsets'][i]:h['offsets'][i] + h['sizes'][i]] for i in range(h['nb'])]
    for idx, items in tex_repl.items():
        t = N.tname(h, idx)
        if t != 'BSShaderTextureSet':
            raise ValueError('块 %d 不是 BSShaderTextureSet（是 %s）' % (idx, t))
        blocks[idx] = build_texset(items)
    data = _rebuild_nif(h, blocks)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, 'wb').write(data)
    return out_path


def nif_texsets(path):
    import nif as N
    b = open(path, 'rb').read()
    h = N.read_header(b)
    out = {}
    for i in range(h['nb']):
        if N.tname(h, i) == 'BSShaderTextureSet':
            out[i] = read_texset(b, h['offsets'][i])
    return out


def dds_wh(path):
    """DDS 头里的宽高（不依赖第三方库）。"""
    try:
        b = open(path, 'rb').read(32)
        if b[:4] != b'DDS ':
            return None
        return struct.unpack_from('<I', b, 16)[0], struct.unpack_from('<I', b, 12)[0]
    except Exception:
        return None


def remap_card_uv(path):
    """把卡片平面（5 顶点 / 3 三角）的 UV 范围拉满到 0..1（原地改写，块大小不变）。

    模板 1_go.nif 的卡片平面只取贴图中段 v≈0.184..0.812（1024² 卡片专用）。
    供图模式输出的是 2048×1024（2:1）卡片，不拉满会在盒子上裁掉上下约 37%。
    """
    import nif as N
    b = bytearray(open(path, 'rb').read())
    h = N.read_header(bytes(b))
    done = 0
    for i in range(h['nb']):
        if N.tname(h, i) != 'BSTriShape':
            continue
        sh = N.parse_tri_shape(bytes(b), h['offsets'][i])
        if not (sh['attr'] & 32) or sh['num_verts'] != 5 or sh['num_tris'] != 3:
            continue
        uvs = [v[1] for v in N.read_vertices(bytes(b), sh)]
        umin = min(u for u, _ in uvs)
        umax = max(u for u, _ in uvs)
        vmin = min(v for _, v in uvs)
        vmax = max(v for _, v in uvs)
        if umax - umin < 1e-6 or vmax - vmin < 1e-6:
            continue
        uv_off = 12 + (4 if (sh['attr'] & 16) else 0)   # 顶点 12 字节 + 可选 4 字节 bitangentX
        for k, (u, v) in enumerate(uvs):
            p = sh['vertex_off'] + k * sh['stride'] + uv_off
            struct.pack_into('<2e', b, p, (u - umin) / (umax - umin), (v - vmin) / (vmax - vmin))
        done += 1
    if done:
        open(path, 'wb').write(bytes(b))
    return done


# ---------------- ESP ----------------
def _scan(o, end, b):
    recs = []
    while o < end:
        sig = b[o:o + 4]
        if sig == b'GRUP':
            size = struct.unpack_from('<I', b, o + 4)[0]
            recs += _scan(o + 24, o + size, b)
            o += size
        else:
            size, flags, fid, vc, fver, unk = struct.unpack_from('<IIIIHH', b, o + 4)
            subs = []
            p = o + 24
            e = p + size
            while p < e:
                t = b[p:p + 4]
                sz = struct.unpack_from('<H', b, p + 4)[0]
                subs.append((t, b[p + 6:p + 6 + sz]))
                p += 6 + sz
            recs.append(dict(sig=sig, fid=fid, flags=flags, fver=fver, vc=vc, unk=unk, subs=subs,
                             raw=b[o:o + 24 + size], off=o))
            o += 24 + size
    return recs


def scan_esp(path):
    b = open(path, 'rb').read()
    recs = _scan(0, len(b), b)
    tes4 = [r for r in recs if r['sig'] == b'TES4']
    return recs, (tes4[0] if tes4 else None)


def sub_get(rec, sig):
    for t, d in rec['subs']:
        if t == sig:
            return d
    return None


def sub_all(rec, sig):
    return [d for t, d in rec['subs'] if t == sig]


def _z(s):
    return s.encode('cp1252', 'replace') + b'\x00'


def _model_path(s):
    return s.replace('/', '\\').encode('cp1252', 'replace') + b'\x00'


def build_record(sig, fid, subs, flags=0, fver=44, vc=0):
    body = b''.join(t + struct.pack('<H', len(d)) + d for t, d in subs)
    return sig + struct.pack('<IIIIHH', len(body), flags, fid, vc, fver, 0) + body


def build_grup(label, records):
    body = b''.join(records)
    size = 24 + len(body)
    return b'GRUP' + struct.pack('<I', size) + label + struct.pack('<iII', 0, 0, 0) + body


def _entries_from(recs):
    """把 ARMO/ARMA 记录整理成 {armo:{fid,edid,full,...}, arma:{...}}"""
    armos = {}
    armas = {}
    for r in recs:
        if r['sig'] == b'ARMA':
            armas[r['fid']] = r
        elif r['sig'] == b'ARMO':
            armos[r['fid']] = r
    out = []
    for fid, a in armos.items():
        link = sub_get(a, b'MODL')
        arma = armas.get(struct.unpack('<I', link)[0]) if link and len(link) == 4 else None
        out.append(dict(armo=a, arma=arma))
    return out


def describe(path):
    recs, tes4 = scan_esp(path)
    out = []
    for e in _entries_from(recs):
        a = e['armo']
        edid = (sub_get(a, b'EDID') or b'').rstrip(b'\x00').decode('cp1252', 'replace')
        full = (sub_get(a, b'FULL') or b'').rstrip(b'\x00').decode('cp1252', 'replace')
        mod4 = (sub_get(a, b'MOD4') or b'').rstrip(b'\x00').decode('cp1252', 'replace')
        mod3 = ''
        if e['arma'] is not None:
            mod3 = (sub_get(e['arma'], b'MOD3') or b'').rstrip(b'\x00').decode('cp1252', 'replace')
        out.append(dict(fid=a['fid'], edid=edid, full=full, mod4=mod4, mod3=mod3))
    return out


def _races_of(arma):
    out = []
    for d in sub_all(arma, b'MODL'):
        if len(d) == 4:
            fid = struct.unpack('<I', d)[0]
            if 0 < fid < 0x01000000:      # 只保留 Skyrim.esm 的种族
                out.append(fid)
    return out


def _keywords_of(armo):
    kwda = sub_get(armo, b'KWDA')
    if not kwda:
        return []
    return [struct.unpack_from('<I', kwda, i)[0] for i in range(0, len(kwda) - 3, 4)
            if struct.unpack_from('<I', kwda, i)[0] < 0x01000000]


def model_surface(shape_name, txst_fid, index=1):
    """ARMO 的 MO2S/MO4S：{count=1, [nameLen, name, TXST FormID, index]}。
    按 Dint BDOR 的做法，name = 盒子 NIF 里卡片那块的 BSTriShape 名（1_go.nif 里就是 '1'），
    引擎据此把该形状的贴图换成 TXST 里的那套。"""
    nm = shape_name.encode('cp1252', 'replace')
    return (struct.pack('<II', 1, len(nm)) + nm
            + struct.pack('<I', txst_fid) + struct.pack('<I', index))


def make_txst(edid, tx00, tx01, tx05, fid):
    r"""TXST：TX00=卡片 dds、TX01=玻璃法线、TX05=环境贴图；路径相对 Data\Textures。"""
    subs = [(b'EDID', _z(edid)), (b'OBND', b'\x00' * 12)]
    for tag, val in ((b'TX00', tx00), (b'TX01', tx01), (b'TX05', tx05)):
        if val:
            subs.append((tag, val.replace('/', '\\').encode('cp1252', 'replace') + b'\x00'))
    subs.append((b'DNAM', b'\x00\x00'))
    return build_record(b'TXST', fid, subs)


def make_entry(armo_rec, arma_rec, edid, full, worn_nif, box_nif, arm_fid, armo_fid,
               txst_fid=None, shape_name='1'):
    """生成新的 ARMA + ARMO 记录（世界模型=盒子）。"""
    bod2 = sub_get(armo_rec, b'BOD2') or b'\x00\x00\x00\x00\x02\x00\x00\x00'
    abod2 = sub_get(arma_rec, b'BOD2') or bod2
    dnam_a = sub_get(arma_rec, b'DNAM') or b'\x00' * 12
    data = sub_get(armo_rec, b'DATA') or struct.pack('<ff', 100.0, 0.2)
    kws = _keywords_of(armo_rec)

    arma_subs = [
        (b'EDID', _z(edid + '_AA')),
        (b'BOD2', abod2),
        (b'RNAM', struct.pack('<I', 0x19)),
        (b'DNAM', dnam_a),
        (b'MOD3', _model_path(worn_nif)),
    ]
    races = _races_of(arma_rec) or [0x19]
    for r in races:
        arma_subs.append((b'MODL', struct.pack('<I', r)))

    hash_ph = b'\x02\x00\x00\x00' + b'\x00' * 8
    armo_subs = [
        (b'EDID', _z(edid)),
        (b'OBND', b'\x00' * 12),
        (b'FULL', _z(full)),
        (b'MOD2', _model_path(box_nif)),
    ]
    if txst_fid:
        # 与 Dint BDOR 一致：MOD2/MOD4 共用同一个盒子 NIF，靠 MO2S/MO4S 换卡片贴图
        armo_subs += [(b'MO2T', hash_ph),
                      (b'MO2S', model_surface(shape_name, txst_fid)),
                      (b'MOD4', _model_path(box_nif)),
                      (b'MO4T', hash_ph),
                      (b'MO4S', model_surface(shape_name, txst_fid))]
    else:
        armo_subs.append((b'MOD4', _model_path(box_nif)))
    armo_subs += [
        (b'BOD2', bod2),
        (b'RNAM', struct.pack('<I', 0x19)),
    ]
    if kws:
        armo_subs.append((b'KSIZ', struct.pack('<I', len(kws))))
        armo_subs.append((b'KWDA', b''.join(struct.pack('<I', k) for k in kws)))
    armo_subs += [
        (b'MODL', struct.pack('<I', arm_fid)),
        (b'DATA', data),
        (b'DNAM', b'\x00' * 4),
    ]
    return (build_record(b'ARMA', arm_fid, arma_subs),
            build_record(b'ARMO', armo_fid, armo_subs))


def _tes4_bytes(tes4, num_records, next_id):
    subs = []
    for t, d in tes4['subs']:
        if t == b'HEDR':
            subs.append((t, struct.pack('<fII', 1.7, num_records, next_id)))
        elif t in (b'MAST', b'DATA'):
            continue
        else:
            subs.append((t, d))
    subs.append((b'MAST', b'Skyrim.esm\x00'))
    subs.append((b'DATA', b'\x00' * 8))
    return build_record(b'TES4', 0, subs, flags=0)


def write_esp(path, entries, tes4, existing_records=None, base_fid=0x800, txsts=()):
    """entries: list of (arma_bytes, armo_bytes)；txsts: 新增 TXST 记录字节列表。
    existing_records 非空则保留其全部记录（按原顺序、原字节），再把新记录追加到对应组。"""
    order, groups = [], {}

    def _put(sig, raw):
        if sig not in groups:
            groups[sig] = []
            order.append(sig)
        groups[sig].append(raw)

    for r in (existing_records or []):
        sig = r['sig']
        if sig == b'TES4':
            continue
        _put(sig, r.get('raw') or build_record(sig, r['fid'], r['subs'], r['flags'], r['fver'], r['vc']))
    for raw in txsts:
        _put(b'TXST', raw)
    for e in entries:
        _put(b'ARMA', e[0])
        _put(b'ARMO', e[1])

    n = sum(len(v) for v in groups.values())
    nextid = base_fid
    for sig in order:
        for r in groups[sig]:
            nextid = max(nextid, struct.unpack_from('<I', r, 12)[0])
    nextid += 1
    data = _tes4_bytes(tes4, n, nextid)
    for sig in order:
        data += build_grup(sig, groups[sig])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'wb').write(data)
    return path
