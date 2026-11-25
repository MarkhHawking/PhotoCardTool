# -*- coding: utf-8 -*-
"""NIF 场景加载与正/侧视角渲染（依赖 photocard_core / render_blend）。"""
import os
import sys
import traceback

import numpy as np


import photocard_core as core
import render_blend as RB

# ==================== 卡片渲染 ====================
def _rot(P, deg_yaw, deg_pitch):
    import numpy as np
    th = np.deg2rad(deg_yaw)
    X = P[:, 0] * np.cos(th) - P[:, 1] * np.sin(th)
    Y = P[:, 0] * np.sin(th) + P[:, 1] * np.cos(th)
    Q = np.stack([X, Y, P[:, 2]], axis=1)
    if abs(deg_pitch) > 1e-6:
        ph = np.deg2rad(deg_pitch)
        Y2 = Q[:, 1] * np.cos(ph) - Q[:, 2] * np.sin(ph)
        Z2 = Q[:, 1] * np.sin(ph) + Q[:, 2] * np.cos(ph)
        Q = np.stack([Q[:, 0], Y2, Z2], axis=1)
    return Q


def load_scene(nif_path):
    import photocard_core as PC
    if not os.path.exists(nif_path):
        raise RuntimeError('NIF 不存在: ' + nif_path)
    pos, uvs, tris, tex = PC.load_geometry(nif_path)
    root = PC.find_root(nif_path)
    t = PC.load_texture(tex, root)
    if t is None:
        raise MissingTexture('找不到贴图：%s' % ', '.join([x for x in tex if x] or ['<nif 未引用贴图>']))
    return dict(pos=pos, uvs=uvs, tris=tris, tex=t, root=root, texpaths=[x for x in tex if x])


def render_view(scene, size, yaw, pitch, prm=None):
    import numpy as np
    import render_blend as RB
    P = np.array(scene['pos'], float)
    P[:, 1] *= -1.0
    return RB.render_blend(_rot(P, yaw, pitch), scene['uvs'], scene['tris'], scene['tex'], size=size, prm=prm)


