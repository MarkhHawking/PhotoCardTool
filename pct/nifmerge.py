# -*- coding: utf-8 -*-
"""同骨架部件合并（第一步：只做「安全合并」）

原理
----
Skyrim 的 HDPT extraParts 是**独立 NIF**：每个部件都带一整套完整骨骼节点，
只在末尾多一片 BSTriShape（+ 它自己的 skin / shader / texset / alpha）。
因为节点顺序与主 NIF 一致，所以骨骼索引可以原位沿用 —— 这是「同骨架家族」
可以安全合并的前提。

本模块只做三件事：
  1. 把部件的 7 个块（shape / skin / skindata / skinpart / shader / texset / alpha）
     追加到主 NIF 末尾，块内索引整体平移；
  2. 把这些块里的「字符串索引」平移到拼接后的字符串表；
  3. 把新 shape 挂到主 NIF 根节点的 children 里。

不做的事：不同骨架之间的骨骼重映射、节点去重、shader 合并。
"""

import os
import struct

import nifpatch as NP

SHAPE_T = 'BSTriShape'

# 块内字段偏移（字节）
NAME = 0          # 所有带名字的块：字符串索引
SHAPE_EXTRA = 4   # extraData 数量
SHAPE_SKIN = 22 * 4
SHAPE_SHADER = 23 * 4
SHAPE_ALPHA = 24 * 4
SKIN_DATA = 0
SKIN_PART = 1 * 4
SKIN_ROOT = 2 * 4
SKIN_BONES = 4 * 4
SHADER_TEXSET = 10 * 4
TEXSET_COUNT = 0


def _u32(b, off):
    return struct.unpack_from('<I', b, off)[0]


def _ref(val):
    return -1 if val == 0xFFFFFFFF else val


def _put32(b, off, val):
    struct.pack_into('<I', b, off, val & 0xFFFFFFFF)


def _net_after_name(b):
    """NiObjectNET：name 之后是 extraData 列表，返回列表之后的偏移。"""
    n = _u32(b, SHAPE_EXTRA)
    return 8 + 4 * n


def children_off(b):
    """NiNode / BSFadeNode 的 children 数量字段偏移。"""
    off = _net_after_name(b)      # -> controller
    off += 4                      # controller
    off += 4                      # flags(u32，实测不是 u16)
    off += 13 * 4                 # transform
    off += 4                      # collision
    return off


def _children(b):
    off = children_off(b)
    if off + 4 > len(b):
        raise ValueError('children 偏移越界')
    n = _u32(b, off)
    if n > 4096 or off + 4 + 4 * n > len(b):
        raise ValueError('children 数量异常: %d' % n)
    return off, n, list(struct.unpack_from('<%dI' % n, b, off + 4))


def _shape_group(h, blocks):
    """取部件里唯一的一片形状，返回 {角色: 块号}。"""
    shapes = [i for i in range(h['nb']) if NP.type_name(h, i) == SHAPE_T]
    if len(shapes) != 1:
        raise ValueError('部件里应当只有 1 片形状，实际 %d' % len(shapes))
    si = shapes[0]
    b = blocks[si]

    def _ref(v):
        return -1 if v == 0xFFFFFFFF else v

    skin = _ref(_u32(b, SHAPE_SKIN))
    shader = _ref(_u32(b, SHAPE_SHADER))
    alpha = _ref(_u32(b, SHAPE_ALPHA))
    grp = {'shape': si, 'skin': skin, 'shader': shader, 'alpha': alpha}
    if skin >= 0:
        sb = blocks[skin]
        grp['skindata'] = _ref(_u32(sb, SKIN_DATA))
        grp['skinpart'] = _ref(_u32(sb, SKIN_PART))
        grp['root'] = _ref(_u32(sb, SKIN_ROOT))
    if shader >= 0:
        grp['texset'] = _ref(_u32(blocks[shader], SHADER_TEXSET))
    return grp


def merge(base_path, part_paths, out_path, log=print, skip_dup=False):
    """把若干同骨架部件合并进主 NIF，写出 out_path。返回统计 dict。"""
    base = NP.load(base_path)
    bh, blocks = base['h'], [bytearray(b) for b in base['blocks']]
    strings = list(bh['strings'])
    nb0 = len(blocks)
    nstr0 = len(strings)

    root = 0
    roff, rcnt, rkids = _children(blocks[root])
    if root >= nb0:
        raise ValueError('根节点异常')

    stats = {'base': base_path, 'parts': [], 'blocks': nb0, 'skipped': []}
    new_types = []          # 追加块对应的类型名（按追加顺序）

    # 主 NIF 里已有网格的指纹（用 NiSkinPartition 的原始字节判断"同一个网格"）
    have = set()
    for i in range(nb0):
        if NP.type_name(bh, i) != SHAPE_T:
            continue
        sb0 = blocks[i]
        sk = _u32(sb0, SHAPE_SKIN)
        if sk == 0xFFFFFFFF or sk >= nb0:
            continue
        kb0 = blocks[sk]
        pt = _u32(kb0, SKIN_PART)
        if pt != 0xFFFFFFFF and pt < nb0:
            have.add(bytes(blocks[pt]))

    for pp in part_paths:
        part = NP.load(pp)
        ph, pblocks = part['h'], part['blocks']
        grp = _shape_group(ph, pblocks)
        pt_idx = grp.get('skinpart', -1)
        if skip_dup and pt_idx is not None and pt_idx >= 0:
            blob = bytes(pblocks[pt_idx])
            if blob in have:
                log('跳过 %s：这组网格主 NIF 里已经有了' % os.path.basename(pp))
                stats['skipped'].append(pp)
                continue
        # 角色 -> 新块号
        order = ['shape', 'skin', 'skindata', 'skinpart', 'shader', 'texset', 'alpha']
        mapping = {}
        new_n = len(blocks)
        for role in order:
            idx = grp.get(role, -1)
            if idx is None or idx < 0:
                continue
            mapping[idx] = new_n + len(mapping)
        # 复制块
        for role in order:
            idx = grp.get(role, -1)
            if idx is None or idx < 0:
                continue
            blocks.append(bytearray(pblocks[idx]))
            new_types.append(NP.type_name(ph, idx))
        # 重写引用
        def remap(buf, off):
            v = _u32(buf, off)
            if v == 0xFFFFFFFF:
                return
            _put32(buf, off, mapping.get(v, v))

        sb = blocks[mapping[grp['shape']]]
        # 字符串索引平移
        v = _u32(sb, NAME)
        if v != 0xFFFFFFFF:
            _put32(sb, NAME, v + nstr0)
        for off in (SHAPE_SKIN, SHAPE_SHADER, SHAPE_ALPHA):
            remap(sb, off)
        if grp.get('skin', -1) >= 0 and grp['skin'] in mapping:
            kb = blocks[mapping[grp['skin']]]
            remap(kb, SKIN_DATA)
            remap(kb, SKIN_PART)
            # SKIN_ROOT 指向骨骼节点，节点区位不变，保持原值
        if grp.get('shader', -1) >= 0 and grp['shader'] in mapping:
            hb = blocks[mapping[grp['shader']]]
            v = _u32(hb, NAME)
            if v != 0xFFFFFFFF:
                _put32(hb, NAME, v + nstr0)
            remap(hb, SHADER_TEXSET)
        # 注意：BSShaderTextureSet 里的贴图路径是「内联的长度前缀字符串」，
        # 不是字符串表索引，所以整块原样复制、不做平移。
        if pt_idx is not None and pt_idx >= 0:
            have.add(bytes(pblocks[pt_idx]))
        # 部件字符串整表追加
        strings.extend(ph['strings'])
        # 挂到根节点
        rkids.append(mapping[grp['shape']])
        stats['parts'].append({
            'path': pp,
            'shape_block': mapping[grp['shape']],
            'skin_block': mapping.get(grp['skin'], -1),
            'shader_block': mapping.get(grp['shader'], -1),
        })

    # 重写根节点 children
    rb = blocks[root]
    new_kids = struct.pack('<%dI' % len(rkids), *rkids)
    rb[roff:roff + 4] = struct.pack('<I', len(rkids))
    # bytearray 切片赋值会自动伸缩，新孩子直接拼在数组尾部
    rb[roff + 4:roff + 4 + 4 * rcnt] = new_kids

    # 更新头部的块类型索引（类型表可能要给新块补一项）
    types = list(bh['types'])
    ti = list(bh['ti'])
    for nm in new_types:
        bnm = nm.encode('latin1')
        if bnm not in types:
            types.append(bnm)
        ti.append(types.index(bnm))
    bh['types'] = types
    bh['ti'] = ti
    bh['nb'] = len(blocks)
    doc = {'path': out_path, 'h': bh, 'blocks': blocks}
    NP.save(doc, out_path, blocks=blocks, strings=strings)

    stats['blocks_after'] = len(blocks)
    stats['strings_after'] = len(strings)
    stats['children'] = len(rkids)
    log('合并完成：%d 块 / %d 字符串 / 根节点子项 %d'
        % (stats['blocks_after'], stats['strings_after'], stats['children']))
    return stats


def scan_parts(base_path, part_paths):
    """给界面用：逐个部件返回 {path, name, verts, dup, error}。

    dup=True 表示这片网格主 NIF 里已经有了（合并时会被跳过）。
    """
    base = NP.load(base_path)
    bh, blocks = base['h'], base['blocks']
    have = set()
    for i in range(bh['nb']):
        if NP.type_name(bh, i) != SHAPE_T:
            continue
        b = blocks[i]
        sk = _ref(_u32(b, SHAPE_SKIN))
        if sk < 0 or sk >= bh['nb']:
            continue
        pt = _ref(_u32(blocks[sk], SKIN_PART))
        if pt >= 0 and pt < bh['nb']:
            have.add(bytes(blocks[pt]))

    out = []
    for pp in part_paths:
        d = {'path': pp, 'name': os.path.basename(pp),
             'verts': 0, 'dup': False, 'error': ''}
        try:
            p = NP.load(pp)
            ph, pb = p['h'], p['blocks']
            grp = _shape_group(ph, pb)
            try:
                from pct.scene import load_scene
                d['verts'] = len(load_scene(pp)['pos'])
            except Exception:
                d['verts'] = 0
            pt = grp.get('skinpart', -1)
            if pt >= 0 and pt < len(pb):
                d['dup'] = bytes(pb[pt]) in have
        except Exception as exc:
            d['error'] = str(exc)
        out.append(d)
    return out


def merge_parts(part_paths, out_path, log=print):
    """只把「勾选的部件」合并成一个新 NIF（不含参考 NIF 本体）。

    以第一个部件作为骨架宿主（每个部件都自带完整骨骼），其余部件并进去。
    """
    if not part_paths:
        raise ValueError('至少给一个部件')
    if len(part_paths) == 1:
        raise ValueError('只有一个部件，不需要合并')
    host = part_paths[0]
    log('骨架宿主：%s' % os.path.basename(host))
    st = merge(host, part_paths[1:], out_path, log=log, skip_dup=False)
    st['host'] = host
    return st


def verify(path, log=print):
    """合并后的结构自检：块引用、字符串索引、顶点数。"""
    d = NP.load(path)
    h, blocks = d['h'], d['blocks']
    nb = h['nb']
    nstr = len(h['strings'])
    bad = []
    shapes = []
    for i in range(nb):
        tn = NP.type_name(h, i)
        if tn != SHAPE_T:
            continue
        b = blocks[i]
        shapes.append(i)
        for name, off in (('skin', SHAPE_SKIN), ('shader', SHAPE_SHADER),
                          ('alpha', SHAPE_ALPHA)):
            v = _u32(b, off)
            if v != 0xFFFFFFFF and v >= nb:
                bad.append('shape %d %s -> %d' % (i, name, v))
        v = _u32(b, NAME)
        if v != 0xFFFFFFFF and v >= nstr:
            bad.append('shape %d name -> %d' % (i, v))
    for i in range(nb):
        if NP.type_name(h, i) != 'NiSkinInstance':
            continue
        b = blocks[i]
        for name, off in (('data', SKIN_DATA), ('partition', SKIN_PART)):
            v = _u32(b, off)
            if v >= nb:
                bad.append('skin %d %s -> %d' % (i, name, v))
        v = _u32(b, SKIN_ROOT)
        if v >= nb:
            bad.append('skin %d root -> %d' % (i, v))
        nbones = _u32(b, SKIN_BONES - 4)
        for k in range(nbones):
            v = _u32(b, SKIN_BONES + 4 * k)
            if v >= nb:
                bad.append('skin %d bone[%d] -> %d' % (i, k, v))
    res = {'shapes': len(shapes), 'blocks': nb, 'strings': nstr, 'bad': bad}
    log('自检：%d 块 / %d 片形状 / %d 字符串 / 问题 %d 处'
        % (nb, len(shapes), nstr, len(bad)))
    for x in bad[:10]:
        log('  ✗ ' + x)
    return res


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='合并同骨架 NIF 部件')
    ap.add_argument('base', help='主 NIF')
    ap.add_argument('parts', nargs='+', help='部件 NIF（可多个）')
    ap.add_argument('-o', '--out', required=True, help='输出 NIF')
    a = ap.parse_args(argv)
    st = merge(a.base, a.parts, a.out)
    verify(a.out)
    print('->', a.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
