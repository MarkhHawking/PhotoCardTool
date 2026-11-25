import os, sys, numpy as np
sys.path.insert(0, r'D:\DSH_SKY_CTD')
import gndtool as G
import make_photos as M

MOD = r'D:\Modding\MO2\mods\Aerith Hair Final Fantasy'
NIF = os.path.join(MOD, 'CalienteTools', 'BodySlide', 'ShapeData', '[Cloud] Aerith Hair', '[Cloud] Aerith Hair.nif')

M.ROOT = MOD
shapes = G.source_shapes(NIF)
print('shapes', len(shapes))
keep = []
for name, pos, uvs, tris, tex in shapes:
    nm = name.decode('latin1') if isinstance(name, bytes) else str(name)
    p = np.asarray(pos, dtype=float)
    print('  ', nm, len(p), len(tris) // 3)
    if 'virtual' in nm.lower() or 'femalehead' in nm.lower():
        continue
    keep.append((nm, pos, uvs, tris, tex))
pos, uvs, tris, tex = [], [], [], []
seen = set()
for nm, p, u, t, tx in keep:
    sig = (len(p), tuple(round(c, 1) for c in p[0]), tuple(round(c, 1) for c in p[len(p) // 2]))
    if sig in seen:
        continue
    seen.add(sig)
    base = len(pos); pos.extend(p); uvs.extend(u); tris.extend([base + x for x in t])
    for q in tx:
        if q and q not in tex:
            tex.append(q)
print('merged', len(pos), len(tris) // 3, 'tex', [t.decode('latin1') if isinstance(t, bytes) else t for t in tex][:3])
M.TM = None
tt = M.load_tex(tex)
print('tex stats', tt.shape, tt[..., :3].mean(axis=(0, 1)), tt[..., 3].mean())
import render_blend as RB
img = RB.render_blend(pos, uvs, tris, M.load_tex(tex), size=2048)
os.makedirs(r'D:\DSH_SKY_CTD\work\out\aerith', exist_ok=True)
png = r'D:\DSH_SKY_CTD\work\out\aerith\aeroith_hair.png'
from PIL import Image
Image.fromarray(img, 'RGBA').save(png)
bg = np.array([46, 46, 46], np.float32)
al = img[..., 3:4].astype(np.float32) / 255.0
comp = (img[..., :3].astype(np.float32) * al + bg * (1 - al)).astype(np.uint8)
flat = np.dstack([comp, np.full(img.shape[:2], 255, np.uint8)])
dds = r'D:\DSH_SKY_CTD\work\out\aerith\photo.dds'
M.save_dds_dxt5(flat, dds)
print('wrote', png, os.path.getsize(png), dds, os.path.getsize(dds))
