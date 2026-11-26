# -*- coding: utf-8 -*-
"""扫描 MOD 目录、按相对路径找贴图/XML、修正异常贴图路径。"""
import os



_index_cache = {}


def scan_mods(root):
    """列出 mods 根目录下真正的 mod。

    - 跳过 MO2 的分隔符文件夹（名字里带 _separator）；
    - 跳过空文件夹（保险：有些分隔符目录连 meta.ini 都没有）。
    """
    out = []
    if not root or not os.path.isdir(root):
        return out
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if not os.path.isdir(p):
            continue
        if '_separator' in d.lower():
            continue
        try:
            if not os.listdir(p):
                continue
        except OSError:
            continue
        if os.path.exists(os.path.join(p, 'meta.ini')) or os.path.isdir(os.path.join(p, 'meshes')) \
                or os.path.isdir(os.path.join(p, 'textures')):
            out.append(d)
    return out


def _mod_index(moddir):
    if moddir in _index_cache:
        return _index_cache[moddir]
    idx = {}
    for sub in ('textures', 'meshes', 'sound'):
        base = os.path.join(moddir, sub)
        for dp, dn, fn in os.walk(base):
            for f in fn:
                idx.setdefault(f.lower(), []).append(os.path.join(dp, f))
    _index_cache[moddir] = idx
    return idx


def find_in_mod(moddir, relpath):
    relpath = relpath.replace('/', '\\').lstrip('\\')
    p = os.path.join(moddir, *relpath.split('\\'))
    if os.path.exists(p):
        return p
    if not relpath.lower().startswith('textures\\'):
        p2 = os.path.join(moddir, 'textures', *relpath.split('\\'))
        if os.path.exists(p2):
            return p2
    base = os.path.basename(relpath).lower()
    for cand in _mod_index(moddir).get(base, []):
        if os.path.exists(cand):
            return cand
    return None


def scan_assets(moddir, nif_rel, xml_strings, tex_paths):
    """返回 [dict(kind,nif/tex/xml,rel,found)]"""
    rows = []
    nif_abs = find_in_mod(moddir, nif_rel) if nif_rel else None
    rows.append(dict(kind='穿着 NIF', rel=nif_rel, src=nif_abs))
    for x in xml_strings:
        rows.append(dict(kind='XML', rel=x, src=find_in_mod(moddir, x)))
    for t in tex_paths:
        rows.append(dict(kind='贴图', rel=t, src=find_in_mod(moddir, t)))
    return rows


def clean_tex_path(rel):
    """修 NIF 里被写坏的贴图路径。

    有些 mod 的贴图槽里混进了换行/制表符，例如
    `Textures\\X\\Hair\\sky074\ntextures\\_n.dds`（本意是 `...\\sky074_n.dds`）。
    这里把控制字符拆开：取前半段的目录+文件名，再拼上后半段的文件名。
    """
    if not rel:
        return rel
    s = rel.replace('\r', '\n').replace('\t', '\n')
    s = ''.join(ch for ch in s if ch == '\n' or ord(ch) >= 32)
    s = s.strip().strip('\x00').strip()
    if '\n' not in s:
        return s
    head, tail = s.split('\n', 1)
    head = head.strip().strip('\\')
    tail = tail.strip().strip('\\')
    if not head:
        return tail
    if not tail:
        return head
    base = head.rsplit('\\', 1)[-1]
    d = head.rsplit('\\', 1)[0] if '\\' in head else ''
    nm = base + tail.rsplit('\\', 1)[-1]
    return (d + '\\' + nm) if d else nm


def rel_to_root(path, roots):
    """把绝对路径压成相对 roots 的写法，压不了就原样返回。"""
    try:
        ap = os.path.abspath(path)
    except Exception:
        return path
    low = ap.lower()
    best = None
    for r in roots:
        if not r:
            continue
        try:
            rp = os.path.abspath(r)
        except Exception:
            continue
        rl = rp.lower().rstrip('\\')
        if low.startswith(rl + '\\') or low == rl:
            cut = len(rp) + 1 if low != rl else len(rp)
            got = ap[cut:]
            if best is None or len(got) < len(best):
                best = got
    return best or path


def _meshes_subdir(rel):
    """meshes\\a\\b\\x.nif -> a\\b（用于从源发型路径推出服装子目录）。"""
    parts = [p for p in str(rel or '').replace('/', '\\').split('\\') if p]
    if parts and parts[0].lower() == 'meshes':
        parts = parts[1:]
    return '\\'.join(parts[:-1])





# --------------------------------------------------------------------------
# BodySlide / Outfit Studio 工程文件
# --------------------------------------------------------------------------
BS_SUBDIRS = (('CalienteTools', 'BodySlide'), ('SliderSets',), ('ShapeData',))


def scan_bodyslide(moddir, nif_stem, limit=40):
    """在 mod 里找和这个发型相关的 BodySlide 工程（.osp / SliderSets *.xml）。

    命中规则：文件名含 nif_stem，或文本里出现该 NIF 名（含 .nif 或去后缀）。
    返回 [(绝对路径, 'osp'|'xml')]，最多 limit 条。
    """
    import os
    moddir = (moddir or '').strip()
    stem = (nif_stem or '').strip().lower()
    if not moddir or not stem or not os.path.isdir(moddir):
        return []
    key = stem[:-4] if stem.endswith('.nif') else stem
    out = []
    for root, dirs, files in os.walk(moddir):
        dirs[:] = [d for d in dirs if d.lower() not in ('.git', 'meshes', 'textures')]
        low = root.lower()
        if 'calientetools' not in low and 'slidersets' not in low and 'shapedata' not in low:
            continue
        for f in files:
            fl = f.lower()
            if not (fl.endswith('.osp') or fl.endswith('.xml')):
                continue
            p = os.path.join(root, f)
            hit = key in fl
            if not hit:
                try:
                    with open(p, 'r', encoding='utf-8-sig', errors='ignore') as fh:
                        txt = fh.read(400000).lower()
                    hit = (key + '.nif') in txt or ('>' + key + '<') in txt or ('"' + key + '"') in txt
                except OSError:
                    hit = False
            if hit:
                out.append((p, 'osp' if fl.endswith('.osp') else 'xml'))
                if len(out) >= limit:
                    return out
    return out


OSP_TMPL = '''<?xml version="1.0" encoding="UTF-8"?>
<SliderSet name="{name}">
    <DataFolder>CalienteTools\\BodySlide</DataFolder>
    <SourceFile>{nif}</SourceFile>
    <OutputPath>CalienteTools\\BodySlide\\ShapeData\\{name}</OutputPath>
    <OutputFile>{name}</OutputFile>
    <Shape target="hair">{shape}</Shape>
</SliderSet>
'''


def write_osp_shell(outdir, name, nif_name, shape='hair'):
    """写一个最小可用的 .osp 骨架（滑块形变仍要在 Outfit Studio 里生成）。"""
    import os
    d = os.path.join(outdir, 'CalienteTools', 'BodySlide', 'SliderSets')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + '.osp')
    with open(p, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(OSP_TMPL.format(name=name, nif=nif_name, shape=shape))
    return p
