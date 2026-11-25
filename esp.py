import struct

HDR = 24

def rd(b, o):
    sig, size, flags, fid, vc, fver, unk = struct.unpack_from('<4sIIIIHH', b, o)
    return dict(sig=sig, size=size, flags=flags, fid=fid, data_off=o+HDR, o=o, end=o+HDR+size,
                vc=vc, fver=fver, unk=unk)

def subrecords(b, start, end):
    out = []
    o = start
    while o < end:
        t = b[o:o+4]; sz = struct.unpack_from('<H', b, o+4)[0]
        out.append(dict(type=t, off=o, data=b[o+6:o+6+sz], size=sz))
        o += 6 + sz
    return out

def top_records(b):
    o = 0
    out = []
    while o < len(b):
        sig = b[o:o+4]
        if sig in (b'GRUP',):
            gsz = struct.unpack_from('<I', b, o+4)[0]
            out.append(dict(sig=sig, o=o, end=o+gsz))
            o += gsz
        else:
            r = rd(b, o)
            out.append(r)
            o = r['end']
    return out

def find_records(b, sig, within=None):
    """yield record dicts of given signature by scanning all GRUPs"""
    out = []
    o = 0
    while o < len(b):
        s = b[o:o+4]
        if s == b'GRUP':
            gsz = struct.unpack_from('<I', b, o+4)[0]
            label = b[o+8:o+12]
            o += 24  # GRUP header 24 bytes: sig,size,label(u32),groupType(i32),stamp,unk
            # walk children
            sub = o
            while sub < o - 0:  # handled below
                break
            # simpler: recurse into payload
            out.extend(_scan_group(b, o, o+gsz-24))
            o += gsz - 24
        else:
            r = rd(b, o)
            if r['sig'] == sig:
                out.append(r)
            o = r['end']
    return out

def _scan_group(b, o, end):
    out = []
    while o < end:
        s = b[o:o+4]
        if s == b'GRUP':
            gsz = struct.unpack_from('<I', b, o+4)[0]
            out.extend(_scan_group(b, o+24, o+gsz))
            o += gsz
        else:
            r = rd(b, o)
            out.append(r)
            o = r['end']
    return out

def walk(b, sigs=None):
    o = 0
    out = []
    while o < len(b):
        s = b[o:o+4]
        if s == b'GRUP':
            gsz = struct.unpack_from('<I', b, o+4)[0]
            label = b[o+8:o+12]
            out.append(('GRUP', label, o, gsz))
            o += gsz
        else:
            r = rd(b, o)
            if sigs is None or r['sig'] in sigs:
                out.append(('REC', r))
            o = r['end']
    return out

def recs_in_group(b, group_label):
    """return record dicts inside first top-level GRUP with label"""
    o = 0
    while o < len(b):
        s = b[o:o+4]
        if s == b'GRUP':
            gsz = struct.unpack_from('<I', b, o+4)[0]
            label = b[o+8:o+12]
            if label == group_label:
                return _scan_group(b, o+24, o+gsz)
            o += gsz
        else:
            o = rd(b, o)['end']
    return []

def make_tes4(template_tes4_data, masters):
    """rebuild TES4 data: copy HEDR + CNAM, drop old MAST/DATA, append new masters"""
    keep = []
    o = 0
    while o < len(template_tes4_data):
        t = template_tes4_data[o:o+4]; sz = struct.unpack_from('<H', template_tes4_data, o+4)[0]
        if t not in (b'MAST', b'DATA', b'MAST'):
            keep.append(template_tes4_data[o:o+6+sz])
        o += 6 + sz
    out = b''.join(keep)
    for m in masters:
        mb = m.encode('ascii') + b'\x00'
        out += b'MAST' + struct.pack('<H', len(mb)) + mb
        out += b'DATA' + struct.pack('<H', 8) + b'\x00'*8
    return out

def build_record(sig, fid, flags, data, vc=0, fver=44):
    return sig + struct.pack('<I', len(data)) + struct.pack('<I', flags) + struct.pack('<I', fid) + \
        struct.pack('<I', vc) + struct.pack('<H', fver) + struct.pack('<H', 0) + data

def build_grup(label, children, gtype=0):
    size = 24 + len(children)
    body = b'GRUP' + struct.pack('<I', size) + label + struct.pack('<i', gtype) + struct.pack('<I', 0) + struct.pack('<I', 0)
    return body + children
