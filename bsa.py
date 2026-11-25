# -*- coding: utf-8 -*-
"""极简 BSA 读取器：只做“这个贴图在不在某个 BSA 里”的判断，不解压。

自动识别两种布局：
  * SSE / FO4（版本 105）：每个文件夹一条 24 字节记录 + 长度前缀文件夹名 +
    该文件夹的 16 字节文件记录（名字在最后的文件名块里）
  * 老版 Skyrim（版本 103/104）：文件夹记录表(16 字节) + 文件记录表(16 字节) +
    文件夹名块 + 文件名块（都是 NUL 分隔）
哈希值不用，因为我们按名字枚举。

用法：
    import bsa
    names = bsa.list_files(r'...\\Skyrim - Textures0.bsa')   # {'textures\\...': size}
    idx   = bsa.build_index([r'...\\Data'])                   # {'textures\\...': bsa 路径}
    hit   = bsa.find(idx, 'textures\\cubemaps\\shinyglass_e.dds')
"""

import os
import struct

MAGIC = b'BSA\0'
HEADER = 36

_cache = {}          # path -> (mtime, {name: size})
_index_cache = {}    # tuple(dirs) -> {name: bsa_path}


def is_bsa(path):
    try:
        with open(path, 'rb') as f:
            return f.read(4) == MAGIC
    except OSError:
        return False


def _dec(x):
    return x.decode('latin-1', 'replace').replace('/', '\\')


def _read_bstr(f):
    n = f.read(1)
    if not n:
        return None
    ln = n[0]
    if ln == 0:
        return b''
    raw = f.read(ln)
    return raw.split(b'\0', 1)[0]


def _parse_v105(f, nfold, nfile, tfld, tfile):
    out = {}
    names = []
    # 先是 nfold 条 24 字节文件夹记录，之后才是「名字 + 该文件夹的文件记录」
    recs = []
    for _ in range(nfold):
        rec = f.read(24)
        if len(rec) < 24:
            return None
        _h, cnt, _unk, _ofs = struct.unpack('<QIIQ', rec)
        recs.append(cnt)
    for cnt in recs:
        fname = _read_bstr(f)
        if fname is None:
            return None
        base = _dec(fname or b'')
        for _ in range(cnt):
            fr = f.read(16)
            if len(fr) < 16:
                return None
            _fh, size, _fo = struct.unpack('<QII', fr)
            names.append(((base + '\\' if base else ''), size & 0x3FFFFFFF if size >> 31 else size))
    flens = []
    buf = f.read(tfile)
    if len(buf) < tfile:
        return None
    flens = [x for x in buf.split(b'\0')]
    while flens and flens[-1] == b'':
        flens.pop()
    if len(flens) != len(names):
        return None
    for (base, size), nm in zip(names, flens):
        out[(base + _dec(nm)).lower()] = size
    return out or None


def _parse_legacy(f, nfold, nfile, tfld, tfile):
    folders = []
    for _ in range(nfold):
        rec = f.read(16)
        if len(rec) < 16:
            return None
        _h, cnt, _o = struct.unpack('<QII', rec)
        folders.append(cnt)
    sizes = []
    for _ in range(nfile):
        rec = f.read(16)
        if len(rec) < 16:
            return None
        _h, size, _o = struct.unpack('<QII', rec)
        sizes.append(size & 0x3FFFFFFF if size >> 31 else size)
    fb = f.read(tfld)
    nb = f.read(tfile)
    if len(fb) < tfld or len(nb) < tfile:
        return None
    fnames = [x for x in fb.split(b'\0') if x]
    flens = [x for x in nb.split(b'\0') if x]
    if len(fnames) < nfold or len(flens) < nfile:
        return None
    out = {}
    i = 0
    for cnt, fname in zip(folders, fnames):
        base = _dec(fname)
        for _ in range(cnt):
            if i >= nfile:
                break
            nm = _dec(flens[i])
            out[((base + '\\' if base else '') + nm).lower()] = sizes[i]
            i += 1
    return out or None


def list_files(path):
    """返回 {小写'folder\\file': 字节大小}；读不了则返回 {}。"""
    try:
        st = os.stat(path)
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == st.st_mtime:
        return hit[1]
    out = {}
    try:
        with open(path, 'rb') as f:
            head = f.read(HEADER)
            if len(head) < HEADER or head[:4] != MAGIC:
                return {}
            _m, ver, _o, _a, nfold, nfile, tfld, tfile, _ff = struct.unpack('<4sIIIIIIII', head)
            f.seek(HEADER)
            out = _parse_v105(f, nfold, nfile, tfld, tfile) or {}
            if not out:
                f.seek(HEADER)
                out = _parse_legacy(f, nfold, nfile, tfld, tfile) or {}
    except (OSError, struct.error):
        return {}
    _cache[path] = (st.st_mtime, out)
    return out


def bsa_in_dir(d, recursive=False):
    res = []
    try:
        if recursive:
            for dp, _dn, fn in os.walk(d):
                for n in fn:
                    if n.lower().endswith('.bsa'):
                        res.append(os.path.join(dp, n))
        else:
            for n in os.listdir(d):
                p = os.path.join(d, n)
                if n.lower().endswith('.bsa') and os.path.isfile(p):
                    res.append(p)
    except OSError:
        pass
    return res


def build_index(dirs, log=None):
    """把若干目录（含其第一层 .bsa）建成 名称->bsa 路径 的索引。"""
    key = tuple(os.path.abspath(d) for d in dirs if d and os.path.isdir(d))
    if key in _index_cache:
        return _index_cache[key]
    idx = {}
    for d in key:
        for p in bsa_in_dir(d):
            names = list_files(p)
            if log and names:
                log('  BSA %s：%d 个文件' % (os.path.basename(p), len(names)))
            for n in names:
                idx.setdefault(n, p)
    _index_cache[key] = idx
    return idx


def find(idx, rel):
    if not idx or not rel:
        return None
    r = rel.strip().lstrip('\\/').replace('/', '\\').lower()
    hit = idx.get(r)
    if hit:
        return hit
    for pre in ('textures\\', 'meshes\\'):
        if r.startswith(pre):
            hit = idx.get(r[len(pre):])
            if hit:
                return hit
    return None


def clear_cache():
    _cache.clear()
    _index_cache.clear()


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        names = list_files(p)
        print('%s -> %d 个文件' % (p, len(names)))
        for k in list(names)[:5]:
            print('   ', k, names[k])
