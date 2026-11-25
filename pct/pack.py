# -*- coding: utf-8 -*-
"""make_pack：复制并改写 NIF/DDS/XML，生成世界模型盒子与 ESP 记录。"""
import os
import shutil
import struct
import time
import traceback

import bsa
import boxesp
import nifpatch

from .mods import clean_tex_path
from .paths import APP_DIR


class MissingTexture(Exception):
    pass


# ==================== 盒子 + ESP ====================
def _read_scene_src(src_esp):
    import boxesp
    return boxesp.describe(src_esp)


def make_pack(*, src_esp, style_edid, moddir, nif_name, box_name, xml_name, msub, tsub,
               bsa_dirs=None, tex_prefix='',
              outdir, tex_card, template_nif, box_dds, boxn_dds, glass_dds,
              esp_path, full_name, log=print, csub=None, bsub=None, share_box=None,
              card_sub=None, card_name='', tex_fix=None):
    import boxesp
    import nifpatch

    bsa_index = dict(BSA_CACHE['index'])
    if bsa_dirs:
        try:
            for k, v in bsa.build_index(bsa_dirs).items():
                bsa_index.setdefault(k, v)
            if bsa_index:
                log('BSA 索引：%d 个文件%s' % (
                    len(bsa_index), '（含缓存）' if BSA_CACHE['index'] else ''))
        except Exception:
            log('BSA 索引失败（忽略）：' + traceback.format_exc())

    entries = boxesp.describe(src_esp)
    ent = [e for e in entries if e['edid'] == style_edid][0]
    recs, tes4 = boxesp.scan_esp(src_esp)
    armo = [r for r in recs if r['sig'] == b'ARMO' and r['fid'] == ent['fid']][0]
    arma_fid = struct.unpack('<I', boxesp.sub_get(armo, b'MODL'))[0]
    arma = [r for r in recs if r['sig'] == b'ARMA' and r['fid'] == arma_fid][0]
    worn_rel = boxesp.sub_get(arma, b'MOD3').rstrip(b'\x00').decode('latin1')
    log('源发型: %s  (%s)' % (ent['full'], worn_rel))

    # --- 定位 ---
    if not moddir or not os.path.isdir(moddir):
        raise RuntimeError('先选择 MO2 mad 文件夹')
    worn_abs = find_in_mod(moddir, worn_rel)
    if not worn_abs:
        raise RuntimeError('该 mod 里找不到穿着 NIF：' + worn_rel)

    doc = nifpatch.load(worn_abs)
    tex = nifpatch.texset_paths(doc)
    xmls = nifpatch.xml_strings(doc)
    log('NIF 引用贴图 %d 个，XML %d 个' % (len(tex), len(xmls)))

    # --- 输出路径（先自定义命名）---
    csub = (csub or '').strip() or msub                    # 服装 Meshes 子目录（穿着 NIF / XML）
    msub = (msub or '').strip() or 'BoxWorld'              # 世界模型 Meshes 子目录（盒子 NIF）
    tsub = (tsub or '').strip() or 'BoxWorld\\hair'        # 服装 Textures 子目录（头发贴图）
    bsub = (bsub or '').strip() or tsub                    # 世界模型 Textures 子目录（盒子贴图）
    card_sub = (card_sub or '').strip() or 'BoxWorld\\hair\\Card'   # 卡片 dds 子目录
    cloth_root = os.path.join(outdir, 'Meshes', csub)
    meshes_root = os.path.join(outdir, 'Meshes', msub)
    tex_root = os.path.join(outdir, 'Textures', tsub)
    boxtex_root = os.path.join(outdir, 'Textures', bsub)
    cardtex_root = os.path.join(outdir, 'Textures', card_sub)
    nif_name = nif_name or os.path.basename(worn_rel)
    box_name = box_name or (style_edid + '_box.nif')
    xml_name = (xml_name or '').strip() or (os.path.basename(xmls[0]) if xmls else '')
    nif_out = os.path.join(cloth_root, nif_name)
    xml_out = os.path.join(cloth_root, xml_name) if xml_name else None
    box_out = os.path.join(meshes_root, box_name)

    # --- 第一遍：只解析来源，不写盘（缺东西就直接中止，不留半个 Meshes/Textures）---
    mapping = {}
    tex_fix = tex_fix or {}
    nif_key = os.path.basename(worn_rel).lower()
    missing = []
    plan = []            # [(kind, rel, src, base, raw_key)]
    seen_key = set()
    for t in tex:
        raw_b = t.rstrip('\x00').lower().encode('latin1')
        raw_key = (nif_key, t.rstrip('\x00').lower())
        if raw_key in seen_key:
            continue
        seen_key.add(raw_key)
        ct = clean_tex_path(t)
        base = ''
        if raw_key in tex_fix:
            val = tex_fix[raw_key] or ''
            if not val:
                plan.append(('clear', ct, '', '', raw_b))
                continue
            src = val
            if not os.path.exists(src):
                missing.append('%s（你指定的文件不存在：%s）' % (ct, src))
                continue
            base = (tex_prefix + os.path.basename(src)) if tex_prefix else os.path.basename(src)
            plan.append(('copy', ct, src, base, raw_b))
        else:
            src = find_in_mod(moddir, ct) if ct else ''
            if not src:
                bhit = bsa.find(bsa_index, ct) if (bsa_index and ct) else None
                if bhit:
                    plan.append(('bsa', ct, bhit, '', raw_b))
                    continue
                missing.append(ct or t)
                continue
            base = (tex_prefix + os.path.basename(src)) if tex_prefix else os.path.basename(src)
            plan.append(('copy', ct, src, base, raw_b))
    for _src, _nm in ((box_dds, 'box.dds'), (boxn_dds, 'box_n.dds'), (glass_dds, 'glass_n.dds')):
        if not _src or not os.path.exists(_src):
            missing.append('盒子贴图缺失：%s' % _src)
    if xmls and xml_name and not find_in_mod(moddir, xmls[0]):
        missing.append('XML 缺失：%s' % xmls[0])
    if tex_card and not os.path.exists(tex_card):
        missing.append('卡片 dds 缺失：%s' % tex_card)
    if missing:
        raise MissingTexture(
            '下面 %d 项没找到，先在素材表里右键「指定这张贴图用的 DDS 文件」或「清空」再生成：\n  %s'
            % (len(missing), '\n  '.join(missing[:8])))

    # --- 预检通过，这时才建目录 ---
    os.makedirs(cloth_root, exist_ok=True)
    os.makedirs(meshes_root, exist_ok=True)
    os.makedirs(tex_root, exist_ok=True)
    if bsub != tsub:
        os.makedirs(boxtex_root, exist_ok=True)
    os.makedirs(cardtex_root, exist_ok=True)

    # --- 第二遍：按计划复制 / 清空 / 跳过 ---
    for kind, ct, src, base, raw_b in plan:
        if kind == 'clear':
            mapping[raw_b] = ''
            log('贴图 %s -> 已按你的设置清空该槽（不复制）' % ct)
        elif kind == 'bsa':
            log('贴图在 BSA 中，保留原路径不复制：%s（%s）' % (ct, os.path.basename(src)))
        else:
            shutil.copy2(src, os.path.join(tex_root, base))
            mapping[raw_b] = 'textures\\%s\\%s' % (tsub, base)
            log('贴图 %s -> textures\\%s\\%s' % (ct, tsub, base))
    nifpatch.rewrite_texsets(doc, mapping)

    # --- XML 复制 + 改写 ---
    if xmls and xml_name:
        srcx = find_in_mod(moddir, xmls[0])
        if not srcx:
            raise RuntimeError('找不到 XML：' + xmls[0])
        shutil.copy2(srcx, xml_out)
        new_xml = 'meshes\\%s\\%s' % (csub, xml_name)
        nifpatch.rewrite_strings(doc, lambda k: k.lower().endswith(b'.xml'), new_xml)
        log('XML -> ' + new_xml)
    elif not xmls:
        log('该 NIF 没有 XML：跳过 XML 复制')
    nifpatch.save(doc, nif_out)
    log('穿着 NIF -> meshes\\%s\\%s' % (csub, nif_name))

    # --- 盒子 ---
    for _src, _nm in ((box_dds, 'box.dds'), (boxn_dds, 'box_n.dds'), (glass_dds, 'glass_n.dds')):
        shutil.copy2(_src, os.path.join(boxtex_root, _nm))

    exists = os.path.exists(esp_path) and os.path.getsize(esp_path) > 0
    old = None
    if exists:
        old, _ = boxesp.scan_esp(esp_path)

    # 追加模式：默认沿用本工具此前生成的盒子 NIF（同一套世界模型），只换卡片贴图
    shared = None
    want_share = SHARE_BOX_DEFAULT if share_box is None else bool(share_box)
    if want_share and old:
        pref = msub.lower() + '\\'
        for r in old:
            if r['sig'] == b'ARMO':
                m = boxesp.sub_get(r, b'MOD2')
                if not m:
                    continue
                cand = m.rstrip(b'\x00').decode('latin1')
                if cand.lower().startswith(pref):
                    shared = cand
                    break
    stem = os.path.splitext(nif_name)[0]
    cn = (card_name or '').strip() or (stem + '_Card')
    if not cn.lower().endswith('.dds'):
        cn += '.dds'
    card_name = cn
    card_dds_rel = '%s\\%s' % (card_sub, card_name)
    shutil.copy2(tex_card, os.path.join(cardtex_root, card_name))
    if not shared:
        sets = boxesp.nif_texsets(template_nif)
        idx = sorted(sets.keys())
        p = 'textures\\%s\\' % bsub
        boxesp.build_box(template_nif, box_out, {
            idx[0]: [p + 'box.dds', p + 'box_n.dds'] + [''] * 7,
            idx[1]: ['textures\\%s\\%s' % (card_sub, card_name), p + 'glass_n.dds', '', '',
                     'textures\\cubemaps\\shinyglass_e.dds'] + [''] * 4,
        })
        log('盒子 -> meshes\\%s\\%s' % (msub, box_name))
        wh = boxesp.dds_wh(tex_card)
        if wh and wh[1] and 1.85 <= wh[0] / float(wh[1]) <= 2.15:
            if boxesp.remap_card_uv(box_out):
                log('卡片 %d×%d（2:1）：盒子卡片平面 UV 已拉满 0..1，避免上下被裁' % wh)
    else:
        wh = boxesp.dds_wh(tex_card)
        log('世界模型复用已有盒子 -> meshes\\%s（卡片 %s，%s×%s）'
            % (shared, card_name, wh[0], wh[1]) if wh else '世界模型复用已有盒子 -> meshes\\%s' % shared)

    # --- ESP ---
    base_fid = 0x800
    edid = style_edid + '_BOX'
    if exists:
        for r in old:
            base_fid = max(base_fid, r['fid'])
        base_fid += 1
        edid = style_edid + '_BOX%d' % base_fid
    armo_fid, arma_fid = base_fid, base_fid + 1
    next_fid = base_fid + 2
    txst_bytes, txst_fid, txst_edid = [], None, None
    box_model = '%s\\%s' % (msub, box_name)
    if shared:
        txst_fid = next_fid
        next_fid += 1
        txst_edid = edid + '_TEX'
        txst_bytes.append(boxesp.make_txst(txst_edid, card_dds_rel,
                                           '%s\\glass_n.dds' % bsub,
                                           'cubemaps\\shinyglass_e.dds', txst_fid))
        box_model = shared
    a, b = boxesp.make_entry(armo, arma, edid, full_name or edid,
                             '%s\\%s' % (csub, nif_name), box_model,
                             arma_fid, armo_fid,
                             txst_fid=txst_fid)
    boxesp.write_esp(esp_path, [(a, b)], tes4, existing_records=old,
                     base_fid=base_fid, txsts=txst_bytes)
    log('ESP (%s): %s' % ('追加' if exists else '新建', esp_path))
    if txst_edid:
        log('替换纹理 %s -> %s（MO2S 绑定盒子形状 1）' % (txst_edid, card_dds_rel))
    return dict(esp=esp_path, nif=nif_out, box=(box_out if not shared else shared),
                xml=xml_out, texdir=tex_root, boxtexdir=boxtex_root,
                edid=edid, txst=txst_edid or '', shared=bool(shared),
                card=os.path.join(cardtex_root, card_name), card_rel=card_dds_rel,
                cardtexdir=cardtex_root)


