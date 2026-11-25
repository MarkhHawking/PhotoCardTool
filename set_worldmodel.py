import sys, struct, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import esp as E

def z(s): return s.encode('latin1') + b'\x00'

def subrec(t, d): return t + struct.pack('<H', len(d)) + d

def read_subs(data):
    out = []
    o = 0
    while o + 6 <= len(data):
        t = data[o:o+4]; sz = struct.unpack_from('<H', data, o+4)[0]
        out.append((t, data[o+6:o+6+sz])); o += 6 + sz
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--esp', required=True)
    ap.add_argument('--box', default=r'BoxWorld\go_box.nif')
    ap.add_argument('--out', required=True)
    ap.add_argument('--mode', choices=['both','male','female'], default='both')
    a = ap.parse_args()
    src = open(a.esp, 'rb').read()
    top = E.top_records(src)
    # masters + HEDR from TES4
    tes4 = [r for r in top if r['sig'] == b'TES4'][0]
    t4 = src[tes4['data_off']:tes4['end']]
    subs = read_subs(t4)
    masters = [d.rstrip(b'\x00').decode('latin1') for t, d in subs if t == b'MAST']
    src_name = os.path.basename(a.esp)
    all_masters = masters + [src_name]
    armo = E.recs_in_group(src, b'ARMO')
    maxfid = max([r['fid'] for r in armo], default=0)
    body = bytearray()
    for r in armo:
        data = src[r['data_off']:r['data_off'] + r['size'] - 24] if False else src[r['o']+24:r['end']]
        rs = read_subs(data)
        keep = []
        for t, d in rs:
            if t in (b'MOD2', b'MOD4', b'MO2T', b'MO4T', b'MO2S', b'MO4S'):
                continue
            keep.append((t, d))
        # append after BOD2/RNAM area: simplest append at end (order-insensitive for these fields)
        if a.mode in ('both', 'male'):
            keep.append((b'MOD2', z(a.box)))
        if a.mode in ('both', 'female'):
            keep.append((b'MOD4', z(a.box)))
        newdata = b''.join(subrec(t, d) for t, d in keep)
        body += E.build_record(b'ARMO', r['fid'], r['flags'], newdata, r['vc'], r['fver'])
    # TES4 for patch
    hed = struct.pack('<fII', 1.7, len(armo), maxfid + 1)
    tes4_data = subrec(b'HEDR', hed) + subrec(b'CNAM', b'')
    for m in all_masters:
        tes4_data += subrec(b'MAST', z(m))
    tes4_rec = E.build_record(b'TES4', 0, 0, tes4_data, 0, 44)
    out = tes4_rec + E.build_grup(b'ARMO', bytes(body), 0)
    open(a.out, 'wb').write(out)
    # verify
    b2 = open(a.out, 'rb').read()
    ok = 0; got = 0
    for r in E.top_records(b2):
        if r['sig'] != b'GRUP':
            continue
        gsz = struct.unpack_from('<I', b2, r['o'] + 4)[0]
        o = r['o'] + 24
        while o + 24 <= r['o'] + gsz:
            sig, rsize, flags, fid, vc, fver, unk = struct.unpack_from('<4sIIIIHH', b2, o)
            if sig == b'ARMO':
                got += 1
                ss = read_subs(b2[o+24:o+24+rsize])
                m2 = [d for t, d in ss if t == b'MOD2']; m4 = [d for t, d in ss if t == b'MOD4']
                good = True
                if a.mode in ('both','male') and not (m2 and m2[0] == z(a.box)): good = False
                if a.mode in ('both','female') and not (m4 and m4[0] == z(a.box)): good = False
                ok += 1 if good else 0
            o += 24 + rsize
    print('esp', a.esp, 'ARMO', len(armo), 'in_group', got, 'patched ok', ok, 'size', len(out), 'masters', all_masters)

if __name__ == '__main__':
    main()
