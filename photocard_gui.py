# -*- coding: utf-8 -*-
"""PhotoCard Tool v24 —— 卡片生成 / 供图拼卡 / 盒子 + ESP

页签 1 卡片生成：NIF -> <名字>.dds(BC7) + _front/_side.png；预设(默认/细节/柔和) + 高级参数折叠。
页签 2 供图拼卡：全屏框选截图(自动方图)填正面/侧面 -> 实时预览整卡 ->
                 <名字>.dds(BC7，默认 1024×1024，可选 2048) + _front/_side.png。
页签 3 盒子 + ESP：选源 ESP/发型 -> 选 MO2 mod 定位 DDS/XML -> 自定义命名 -> 生成
                    （复制 NIF/DDS/XML 并改写内部路径，盒子 nif 与 ESP 一起产出）
"""
import os
import re
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk
try:
    import bsa
except Exception:
    bsa = None
from tkinter import font as tkfont

BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

MAT = os.path.join(APP_DIR, 'materials')
TEXCONV = os.path.join(MAT, 'Texconv.exe')
if not os.path.exists(TEXCONV):
    TEXCONV = os.path.join(BASE, 'Texconv.exe')
BASE_CARD = os.path.join(MAT, '02.png')
if not os.path.exists(BASE_CARD):
    BASE_CARD = os.path.join(BASE, '02.png')

CARD_RECT = (12, 238, 1012, 788)
BG = (46, 46, 46)
SIDE_YAW = 65.0

# 供图拼卡（页签②）：与卡片生成同一版式（02.png 木框 + 中间卡片区），默认 1024×1024
SQUARE_PX = 280
PREV1_PX = 560        # 卡片生成页的预览尺寸（原来 440）
PREV2_W, PREV2_H = 460, 460
G_SIZES = ('1024', '2048')

# 渲染预设：只改这些项，其余保持默认
PRESETS = {
    '默认': dict(amb=0.50, diff=0.55, rim=0.18, spec=0.24, specpow=24, alpha=1.8,
                 gamma=1.8, bright=1.0, contrast=1.0, depth=0, autobright=1),
    '细节': dict(amb=0.50, diff=0.55, rim=0.18, spec=0.35, specpow=32, alpha=1.4,
                 gamma=1.8, bright=1.0, contrast=1.0, depth=1, autobright=1),
    '柔和': dict(amb=0.50, diff=0.60, rim=0.18, spec=0.24, specpow=12, alpha=2.0,
                 gamma=1.8, bright=1.0, contrast=1.0, depth=0, autobright=1),
}



from pct.paths import (APP_DIR, BASE, BASE_CARD, BSA_CACHE, CACHE_DIR, MAT, SETTINGS_FILE,
                       TEXCONV, auto_find_game_data, auto_find_mods_root, bsa_cache_path,
                       load_bsa_cache, load_settings, save_bsa_cache, save_settings,
                       scan_bsa_tree)
from pct.imaging import (BG, CARD_RECT, build_card, compose_card, dds_size, panel, run_card,
                         square_crop, to_bc7)
from pct.scene import load_scene, render_view
from pct.mods import (scan_bodyslide, write_osp_shell, _index_cache, _meshes_subdir, clean_tex_path, find_in_mod, rel_to_root,
                      scan_assets, scan_mods)
from pct.ui import (FuzzyCombo, ToolTip, _fuzzy_match, _fuzzy_rank, log_trim)
from pct.pack import MissingTexture, make_pack
from pct.screenshots import _virtual_metrics, shoot_screen

def main_gui():
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from PIL import Image, ImageTk

    root = tk.Tk()
    root.title('PhotoCard Tool · 卡片 / 盒子世界模型')
    _sw = root.winfo_screenwidth()
    _sh = root.winfo_screenheight()
    _w = min(1140, max(960, _sw - 80))
    _h = min(1060, max(700, _sh - 40))
    root.geometry('%dx%d+%d+%d' % (_w, _h, max(0, (_sw - _w) // 2), 0))
    root.minsize(960, 800)
    try:
        root.tk.call('tk', 'scaling', 1.15)
    except Exception:
        pass


    # ==== 设置（mods 根目录 / 游戏根目录 / 缓存目录）====
    _settings = load_settings()
    cache_dir = tk.StringVar(value=_settings.get('cache_dir') or APP_DIR)

    def open_settings():
        win = tk.Toplevel(root)
        win.title('设置')
        win.transient(root)
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill='both', expand=True)
        mv = tk.StringVar(value=mods_root.get())
        gv = tk.StringVar(value=game_data.get())
        cv_ = tk.StringVar(value=cache_dir.get())

        def row(r, label, var, auto_fn, auto_label):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky='w', pady=4)
            ttk.Entry(frame, textvariable=var, width=72).grid(row=r, column=1, sticky='we', padx=6)
            ttk.Button(frame, text='浏览…',
                       command=lambda: browse(var, kind='dir')).grid(row=r, column=2)
            def _auto():
                p = auto_fn()
                if p:
                    var.set(p)
                    log2_to('自动搜索：%s -> %s' % (auto_label, p))
                else:
                    log2_to('自动搜索：没找到 %s' % auto_label)
            ttk.Button(frame, text='自动搜索', command=_auto).grid(row=r, column=3, padx=(6, 0))

        row(0, 'MO2 mods 根目录：', mv, auto_find_mods_root, 'mods 根目录')
        row(1, '游戏 Data 目录：', gv, auto_find_game_data, '游戏 Data')
        row(2, '缓存目录：', cv_, lambda: APP_DIR, '软件目录')
        ttk.Label(frame, text='缓存里放：BSA 索引、卡片预览的临时 png。默认就在软件所在目录。',
                  foreground='#666').grid(row=3, column=1, columnspan=3, sticky='w', pady=(6, 0))

        no_pop = tk.IntVar(value=1 if _settings.get('setup_done') else 1)
        ttk.Checkbutton(frame, text='保存后不再自动弹出（下次启动不弹这个窗口）',
                        variable=no_pop).grid(row=4, column=0, columnspan=4, sticky='w', pady=(6, 0))

        def do_save():
            mods_root.set(mv.get().strip())
            game_data.set(gv.get().strip())
            cache_dir.set(cv_.get().strip() or APP_DIR)
            CACHE_DIR['dir'] = cache_dir.get()
            save_settings({'mods_root': mods_root.get(), 'game_data': game_data.get(),
                           'cache_dir': cache_dir.get(),
                           'setup_done': 1 if no_pop.get() else 0})
            _settings.update(load_settings())
            log2_to('设置已保存到 %s' % SETTINGS_FILE)
            win.destroy()

        btns = ttk.Frame(frame)
        btns.grid(row=5, column=0, columnspan=4, pady=(10, 0), sticky='e')
        ttk.Button(btns, text='保存', command=do_save).pack(side='right')
        ttk.Button(btns, text='取消', command=win.destroy).pack(side='right', padx=(0, 6))
        win.grab_set()

    def scan_bsa_all():
        dirs = [mods_root.get().strip(), game_data.get().strip()]
        log2_to('开始扫描 BSA（mods 根目录 + 游戏 Data）…')
        def work():
            t0 = time.time()
            idx = scan_bsa_tree(dirs, log=log2_to)
            p = save_bsa_cache(cache_dir.get(), idx)
            BSA_CACHE['index'] = idx
            BSA_CACHE['stamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
            log2_to('BSA 扫描完成：%d 个文件名，用时 %.1f 秒%s' % (
                len(idx), time.time() - t0, ('，缓存 -> ' + p) if p else ''))
        threading.Thread(target=work, daemon=True).start()

    def open_cache():
        d = cache_dir.get() or APP_DIR
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as e:
            log2_to('打开缓存目录失败：%s' % e)

    def clear_bsa_cache():
        p = bsa_cache_path(cache_dir.get())
        try:
            if os.path.exists(p):
                os.remove(p)
            BSA_CACHE['index'] = {}
            bsa.clear_cache()
            log2_to('已清空 BSA 缓存')
        except Exception as e:
            log2_to('清空缓存失败：%s' % e)

    if not _settings.get('setup_done'):
        root.after(400, open_settings)

    menubar = tk.Menu(root, tearoff=0)
    m_set = tk.Menu(menubar, tearoff=0)
    m_set.add_command(label='路径设置…', command=open_settings)
    m_set.add_separator()
    m_set.add_command(label='自动搜索 mods 根目录',
                      command=lambda: log2_to('mods 根目录 -> %s' % (auto_find_mods_root() or '没找到')))
    m_set.add_command(label='自动搜索游戏根目录',
                      command=lambda: log2_to('游戏 Data -> %s' % (auto_find_game_data() or '没找到')))
    m_set.add_separator()
    m_set.add_command(label='扫描 BSA（mods + 游戏）', command=scan_bsa_all)
    m_set.add_command(label='打开缓存目录', command=open_cache)
    m_set.add_command(label='清空 BSA 缓存', command=clear_bsa_cache)
    menubar.add_cascade(label='设置', menu=m_set)
    root.config(menu=menubar)

    bar = ttk.Frame(root)
    bar.pack(fill='x', padx=10, pady=(10, 0))
    body = ttk.Frame(root)
    body.pack(fill='both', expand=True)
    def _scroll_page():
        """带竖向滚动的页：小屏 / 高 DPI 缩放下内容不会被切掉。"""
        host = ttk.Frame(body)
        cv = tk.Canvas(host, highlightthickness=0, bd=0, bg=root.cget('bg'))
        vs = ttk.Scrollbar(host, orient='vertical', command=cv.yview)
        cv.configure(yscrollcommand=vs.set)
        vs.pack(side='right', fill='y')
        cv.pack(side='left', fill='both', expand=True)
        inner = ttk.Frame(cv, padding=12)
        win = cv.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))

        def _selfscroll(w):
            """光标所在的控件（或祖先）自己会滚：日志、表格、列表框。"""
            try:
                while w is not None:
                    if w.winfo_class() in ('Text', 'Treeview', 'Listbox'):
                        return True
                    w = getattr(w, 'master', None)
            except Exception:
                pass
            return False

        def _wheel(e):
            try:
                under = root.winfo_containing(root.winfo_pointerx(), root.winfo_pointery())
            except Exception:
                under = None
            if _selfscroll(under):
                return None      # 让日志/表格自己滚，整页不动
            cv.yview_scroll(int(-1 * (e.delta / 120)), 'units')
            return 'break'

        def _fit(_e=None):
            """内容比窗口矮时铺满（多出来的高度给带 weight 的行）；比窗口高时可滚。"""
            try:
                if not cv.winfo_ismapped():
                    return
                w, h = cv.winfo_width(), cv.winfo_height()
                if w <= 2 or h <= 2:
                    return
                need = inner.winfo_reqheight()
                cv.itemconfigure(win, width=w, height=max(need, h))
            except tk.TclError:
                pass

        inner.bind('<Configure>', lambda e: (inner.after_idle(_fit),
                                             cv.configure(scrollregion=cv.bbox('all'))), add='+')
        cv.bind('<Configure>', lambda e: _fit(), add='+')
        host.bind('<Map>', lambda e: cv.after_idle(_fit), add='+')
        cv.bind('<Enter>', lambda e: cv.bind_all('<MouseWheel>', _wheel))
        cv.bind('<Leave>', lambda e: cv.unbind_all('<MouseWheel>'))
        return host, inner

    t1_host, t1 = _scroll_page()      # 页签① 卡片生成（小屏可滚，生成按钮能点到）
    t2s_host, t2s = _scroll_page()        # 页签② 供图拼卡
    t2_host, t2 = _scroll_page()          # 页签③ 盒子 + ESP（沿用旧变量名）

    def show_page(page):
        for w in (t1_host, t2s_host, t2_host):
            w.pack_forget()
        page.pack(fill='both', expand=True)

    _st = ttk.Style(root)
    _st.configure('Err.TEntry', fieldbackground='#ffd2d2')
    _st.configure('Err.TCombobox', fieldbackground='#ffd2d2')
    _st.configure('Warn.TEntry', fieldbackground='#ffe9b8')
    _st.configure('Warn.TCombobox', fieldbackground='#ffe9b8')

    ttk.Button(bar, text='① 卡片生成', command=lambda: show_page(t1_host)).pack(side='left')
    ttk.Button(bar, text='② 供图拼卡', command=lambda: show_page(t2s_host)).pack(side='left', padx=(6, 0))
    ttk.Button(bar, text='③ 盒子 + ESP', command=lambda: show_page(t2_host)).pack(side='left', padx=(6, 0))
    show_page(t1_host)

    # ---------------- tab 1 ----------------
    nif_var = tk.StringVar()
    out_var = tk.StringVar()
    name_var = tk.StringVar()
    size_var = tk.StringVar(value='1024')
    follow_var = tk.BooleanVar(value=True)
    yaw_f = tk.DoubleVar(value=0)
    pitch_f = tk.DoubleVar(value=0)
    yaw_s = tk.DoubleVar(value=65)
    pitch_s = tk.DoubleVar(value=0)
    fill_var = tk.DoubleVar(value=92)
    hs_var = tk.DoubleVar(value=100)
    rpv = dict(amb=tk.DoubleVar(value=0.50), diff=tk.DoubleVar(value=0.55),
               rim=tk.DoubleVar(value=0.18), spec=tk.DoubleVar(value=0.24),
               specpow=tk.DoubleVar(value=24), alpha=tk.DoubleVar(value=1.8),
               gamma=tk.DoubleVar(value=1.8), bright=tk.DoubleVar(value=1.0),
               contrast=tk.DoubleVar(value=1.0))
    depth_var = tk.IntVar(value=0)
    autob_var = tk.IntVar(value=1)      # 按贴图平均亮度自适应（压掉“发白”）

    def rp_dict():
        out = {k: float(v.get()) for k, v in rpv.items()}
        out['depth'] = int(depth_var.get())
        out['autobright'] = int(autob_var.get())
        return out

    class Num(ttk.Frame):
        def __init__(self, parent, label, var, lo, hi, fmt='%.0f', on_change=None, length=130):
            super().__init__(parent)
            self.var, self.fmt, self.cb = var, fmt, on_change
            ttk.Label(self, text=label).pack(side='left')
            self.e = ttk.Entry(self, width=6)
            self.e.pack(side='left', padx=(3, 3))
            self.s = ttk.Scale(self, from_=lo, to=hi, variable=var, length=length,
                               command=lambda v: self._changed())
            self.s.pack(side='left')
            self.e.bind('<Return>', self._commit)
            self.e.bind('<FocusOut>', self._commit)
            var.trace_add('write', lambda *a: self._sync())
            self._sync()

        def _sync(self):
            try:
                self.e.delete(0, 'end')
                self.e.insert(0, self.fmt % float(self.var.get()))
            except Exception:
                pass

        def _commit(self, *_):
            try:
                self.var.set(float(self.e.get()))
            except Exception:
                self._sync()
            self._changed()

        def _changed(self):
            self._sync()
            if self.cb:
                self.cb()

    def defaults_from(nif):
        stem = re.sub(r'[\\/:*?"<>|]', '_', os.path.splitext(os.path.basename(nif))[0])
        return os.path.dirname(nif), stem

    preview_lbl = ttk.Label(t1, text='（选 NIF 后这里显示双视角实时预览）', anchor='center')
    preview_lbl.configure(width=PREV1_PX)
    prev_state = dict(scene=None, nif=None, job=None, img=None, seq=0, busy=False)

    def _preview_worker(seq):
        try:
            sc = prev_state['scene']
            if not sc or seq != prev_state['seq']:
                return
            f = panel(render_view(sc, 900, float(yaw_f.get()), float(pitch_f.get()), rp_dict()))
            if seq != prev_state['seq']:
                return
            sd = panel(render_view(sc, 900, float(yaw_s.get()), float(pitch_s.get()), rp_dict()))
            if seq != prev_state['seq']:
                return
            card = compose_card(f, sd, PREV1_PX, float(fill_var.get()), float(hs_var.get()))
            prev_state['img'] = ImageTk.PhotoImage(card)
            d = prev_state.get('desc') or {}
            txt = ('预览完成 %s · %s · 正面 %.0f°/%.0f°  侧面 %.0f°/%.0f° · 占比 %.0f%% 横向 %.0f%% · '
                   '发丝 %.2f 伽马 %.2f 深度%s · 预设 %s'
                   % (time.strftime('%H:%M:%S'), d.get('nif', ''),
                      d.get('yaw_f', 0), d.get('pitch_f', 0), d.get('yaw_s', 0), d.get('pitch_s', 0),
                      d.get('fill', 0), d.get('hs', 0), d.get('alpha', 0), d.get('gamma', 0),
                      '开' if d.get('depth') else '关', d.get('preset', '')))
            root.after(0, lambda: preview_lbl.configure(image=prev_state['img'], text=''))
            root.after(0, lambda: (log_to(log1, txt), log_trim(log1)))
        except Exception as e:
            import traceback as _tb
            msg = '%s: %s' % (type(e).__name__, e)
            root.after(0, lambda: preview_lbl.configure(image='', text='预览失败 → ' + msg))
            try:
                open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'preview_error.log'), 'a', encoding='utf-8').write(_tb.format_exc() + '\n')
            except Exception:
                pass

    def draw_preview():
        if not prev_state['scene']:
            return
        prev_state['seq'] += 1
        prev_state['desc'] = dict(
            nif=os.path.basename(prev_state.get('nif') or nif_var.get() or ''),
            yaw_f=float(yaw_f.get()), pitch_f=float(pitch_f.get()),
            yaw_s=float(yaw_s.get()), pitch_s=float(pitch_s.get()),
            fill=float(fill_var.get()), hs=float(hs_var.get()),
            preset=cur_preset[0], alpha=float(rpv['alpha'].get()),
            gamma=float(rpv['gamma'].get()), depth=int(depth_var.get()))
        threading.Thread(target=_preview_worker, args=(prev_state['seq'],), daemon=True).start()

    def schedule_preview():
        if prev_state['job']:
            try:
                root.after_cancel(prev_state['job'])
            except Exception:
                pass
        prev_state['job'] = root.after(320, draw_preview)

    def load_for_preview(path):
        try:
            prev_state['scene'] = load_scene(path)
            schedule_preview()
        except Exception as e:
            prev_state['scene'] = None
            preview_lbl.configure(image='', text=str(e))

    def pick_nif():
        p = filedialog.askopenfilename(title='选择 NIF', filetypes=[('NIF', '*.nif'), ('所有文件', '*.*')])
        if not p:
            return
        nif_var.set(p)
        if follow_var.get():
            o, n = defaults_from(p)
            out_var.set(o)
            name_var.set(n)
        load_for_preview(p)

    def pick_out():
        p = filedialog.askdirectory(title='选择输出文件夹')
        if p:
            out_var.set(p)

    steps = ttk.Label(t1, text='操作顺序：① 选 NIF → ② 确认输出目录/名字 → ③ 选预设或展开高级参数微调（预览实时更新）→ ④ 生成卡片',
                      foreground='#555')
    steps.grid(row=0, column=0, columnspan=5, sticky='w', pady=(0, 6))

    r = 1
    ttk.Label(t1, text='NIF 文件：').grid(row=r, column=0, sticky='w')
    nif_entry = ttk.Entry(t1, textvariable=nif_var, width=86)
    nif_entry.grid(row=r, column=1, columnspan=3, sticky='we')
    nif_entry.bind('<Return>', lambda e: (follow_var.get() and (out_var.set(defaults_from(nif_var.get())[0]), name_var.set(defaults_from(nif_var.get())[1])), load_for_preview(nif_var.get())))
    nif_entry.bind('<FocusOut>', lambda e: load_for_preview(nif_var.get()))
    ttk.Button(t1, text='浏览…', command=pick_nif).grid(row=r, column=4, padx=(6, 0))
    r += 1
    ttk.Label(t1, text='输出文件夹：').grid(row=r, column=0, sticky='w')
    ttk.Entry(t1, textvariable=out_var, width=86).grid(row=r, column=1, columnspan=3, sticky='we')
    ttk.Button(t1, text='浏览…', command=pick_out).grid(row=r, column=4, padx=(6, 0))
    r += 1
    ttk.Checkbutton(t1, text='输出路径跟随输入文件（取消=锁定）', variable=follow_var).grid(
        row=r, column=0, columnspan=3, sticky='w')
    r += 1

    f2 = ttk.Frame(t1)
    f2.grid(row=r, column=0, columnspan=5, sticky='we', pady=(6, 3))
    ttk.Label(f2, text='输出名:').pack(side='left')
    ttk.Entry(f2, textvariable=name_var, width=22).pack(side='left', padx=(4, 12))
    ttk.Label(f2, text='尺寸:').pack(side='left')
    ttk.Combobox(f2, textvariable=size_var, values=['1024', '2048'], width=7, state='readonly').pack(side='left', padx=(4, 12))
    Num(f2, '画面占比%', fill_var, 55, 100, on_change=schedule_preview).pack(side='left', padx=(0, 8))
    Num(f2, '横向%', hs_var, 80, 145, on_change=schedule_preview).pack(side='left')
    r += 1

    f3 = ttk.Frame(t1)
    f3.grid(row=r, column=0, columnspan=5, sticky='we', pady=(0, 3))
    ttk.Label(f3, text='正面：').pack(side='left')
    Num(f3, '旋转°', yaw_f, -180, 180, on_change=schedule_preview).pack(side='left', padx=(0, 8))
    Num(f3, '俯仰°', pitch_f, -40, 40, on_change=schedule_preview).pack(side='left', padx=(0, 16))
    ttk.Label(f3, text='侧面：').pack(side='left')
    Num(f3, '旋转°', yaw_s, -180, 180, on_change=schedule_preview).pack(side='left', padx=(0, 8))
    Num(f3, '俯仰°', pitch_s, -40, 40, on_change=schedule_preview).pack(side='left')
    r += 1

    cur_preset = ['默认']

    def set_preset(name):
        cur_preset[0] = name
        preset_lbl.configure(text='当前：' + name)

    def apply_preset(name):
        for k, v in PRESETS[name].items():
            if k == 'depth':
                depth_var.set(int(v))
            elif k == 'autobright':
                autob_var.set(int(v))
            else:
                rpv[k].set(float(v))
        set_preset(name)
        schedule_preview()

    def adv_changed():
        set_preset('自定义')
        schedule_preview()

    def toggle_adv():
        if adv_btn.cget('text').endswith('▸'):
            adv.grid()
            adv_btn.configure(text='高级参数▾')
        else:
            adv.grid_remove()
            adv_btn.configure(text='高级参数▸')

    f4 = ttk.Frame(t1)
    f4.grid(row=r, column=0, columnspan=5, sticky='we', pady=(2, 0))
    ttk.Label(f4, text='预设:').pack(side='left')
    for nm in ('默认', '细节', '柔和'):
        ttk.Button(f4, text=nm, width=6, command=lambda n=nm: apply_preset(n)).pack(side='left', padx=(4, 0))
    preset_lbl = ttk.Label(f4, text='当前：默认', foreground='#1a6fb5')
    preset_lbl.pack(side='left', padx=(10, 14))
    adv_btn = ttk.Button(f4, text='高级参数▸', width=12, command=lambda: toggle_adv())
    adv_btn.pack(side='left')
    ttk.Label(f4, text='（渲染参数都在里面）', foreground='#888').pack(side='left', padx=(8, 0))
    r += 1

    adv = ttk.Frame(t1)
    adv.grid(row=r, column=0, columnspan=5, sticky='we', pady=(4, 0))
    adv.grid_remove()

    f4b = ttk.Frame(adv)
    f4b.pack(fill='x', pady=(0, 2))
    Num(f4b, '环境光', rpv['amb'], 0, 1.2, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f4b, '漫反射', rpv['diff'], 0, 1.2, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f4b, '边缘光', rpv['rim'], 0, 1.0, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f4b, '高光', rpv['spec'], 0, 1.5, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f4b, '高光锐度', rpv['specpow'], 2, 128, on_change=adv_changed, length=70, fmt='%.0f').pack(side='left')

    f5 = ttk.Frame(adv)
    f5.pack(fill='x')
    Num(f5, '发丝厚度', rpv['alpha'], 0.2, 4.0, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f5, '亮度', rpv['bright'], 0.4, 2.0, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f5, '对比度', rpv['contrast'], 0.4, 2.0, on_change=adv_changed, length=70, fmt='%.2f').pack(side='left', padx=(0, 6))
    Num(f5, '伽马', rpv['gamma'], 0.6, 3.0, on_change=adv_changed, length=70,
        fmt='%.2f').pack(side='left', padx=(0, 10))
    ttk.Checkbutton(f5, text='深度遮挡', variable=depth_var, command=adv_changed).pack(side='left')
    ttk.Checkbutton(f5, text='亮度自适应', variable=autob_var, command=adv_changed).pack(side='left', padx=(8, 0))
    r += 1

    preview_lbl.grid(row=r, column=0, columnspan=5, pady=(2, 6))
    r += 1
    log1_wrap = ttk.Frame(t1)
    log1 = tk.Text(log1_wrap, height=8, wrap='word')
    log1_vs = ttk.Scrollbar(log1_wrap, orient='vertical', command=log1.yview)
    log1.configure(yscrollcommand=log1_vs.set)
    log1.pack(side='left', fill='both', expand=True)
    log1_vs.pack(side='right', fill='y')
    log1_wrap.grid(row=r, column=0, columnspan=5, sticky='we', pady=(2, 4))
    r += 1
    btn_gen = ttk.Button(t1, text='④ 生成卡片')
    btn_gen.grid(row=r, column=0, columnspan=5, sticky='we')
    for c in range(4):
        t1.columnconfigure(c, weight=1)

    def log_to(w, msg):
        w.insert('end', msg + '\n')
        w.see('end')
        root.update_idletasks()

    def job1():
        p = nif_var.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showerror('缺少输入', '请选择存在的 .nif 文件')
            return
        o = out_var.get().strip()
        if not o:
            o, n = defaults_from(p)
            out_var.set(o)
            if not name_var.get():
                name_var.set(n)
        n = name_var.get().strip() or defaults_from(p)[1]
        btn_gen.configure(state='disabled')
        log1.delete('1.0', 'end')

        def work():
            try:
                log_to(log1, '输入: ' + p)
                png, dds = run_card(p, o, int(size_var.get()), n, lambda m: log_to(log1, m),
                                    float(fill_var.get()), float(hs_var.get()),
                                    float(yaw_f.get()), float(pitch_f.get()),
                                    float(yaw_s.get()), float(pitch_s.get()), rp_dict())
                log_to(log1, '完成: ' + dds)
                root.after(0, lambda: messagebox.showinfo('完成', dds))
            except MissingTexture as e:
                root.after(0, lambda: messagebox.showwarning('缺少贴图', str(e)))
            except Exception as e:
                log_to(log1, traceback.format_exc())
                root.after(0, lambda: messagebox.showerror('失败', str(e)))
            finally:
                root.after(0, lambda: btn_gen.configure(state='normal'))

        threading.Thread(target=work, daemon=True).start()

    btn_gen.configure(command=job1)

    # ---------------- tab 2 供图拼卡（页签②） ----------------
    g_state = {'front': dict(img=None, lbl=None, thumb=None),
               'side': dict(img=None, lbl=None, thumb=None)}
    g_out = tk.StringVar(value=APP_DIR)
    g_name = tk.StringVar()
    g_size = tk.StringVar(value='1024')

    ttk.Label(t2s, foreground='#555',
              text='操作顺序：① 正面点「截图」拖框（自动正方形）或「选图…」 → ② 侧面同理 → ③ 确认输出名/文件夹 → ④ 生成').grid(
        row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))

    left = ttk.Frame(t2s)
    left.grid(row=1, column=0, sticky='nw')
    right = ttk.Frame(t2s)
    right.grid(row=1, column=1, sticky='nsew', padx=(16, 0))
    t2s.columnconfigure(1, weight=1)
    t2s.rowconfigure(1, weight=1)

    for title, key in (('① 正面（front）', 'front'), ('② 侧面（side）', 'side')):
        box = ttk.LabelFrame(left, text=title, padding=8)
        box.pack(fill='x', pady=(0, 10))
        holder = tk.Frame(box, width=SQUARE_PX, height=SQUARE_PX, bg='#2e2e2e')
        holder.pack(side='left')
        holder.pack_propagate(False)
        lbl = tk.Label(holder, text='点「截图」\n框选方图\n或「选图…」', bg='#2e2e2e', fg='#9a9a9a',
                       font=('Microsoft YaHei', 10), justify='center')
        lbl.pack(fill='both', expand=True)
        g_state[key]['lbl'] = lbl
        btns = ttk.Frame(box)
        btns.pack(side='left', fill='y', padx=(10, 0))
        ttk.Button(btns, text='截图', command=lambda k=key: g_shoot(k)).pack(fill='x', pady=(0, 6))
        ttk.Button(btns, text='选图…', command=lambda k=key: g_pick(k)).pack(fill='x', pady=(0, 6))
        ttk.Button(btns, text='清空', command=lambda k=key: g_clear(k)).pack(fill='x')

    ttk.Label(right, text='整卡预览（02.png 木框 + 左正面 / 右侧面，与「卡片生成」同一版式）').pack(anchor='w')
    prev_holder = tk.Frame(right, bg='#2e2e2e', height=PREV2_H)
    prev_holder.pack(fill='both', expand=True, pady=(4, 10))
    prev_cv = tk.Canvas(prev_holder, bg='#2e2e2e', highlightthickness=0)
    prev_cv.pack(fill='both', expand=True)
    g_prev = dict(img=None, pi=None, job=None)

    def _draw_prev():
        w, h = prev_cv.winfo_width(), prev_cv.winfo_height()
        if w < 30 or h < 30:
            return
        prev_cv.delete('all')
        if g_prev['img'] is None:
            prev_cv.create_text(w // 2, h // 2, fill='#9a9a9a', font=('Microsoft YaHei', 10),
                                text='（填好正面 / 侧面后，这里实时预览整卡）')
            return
        im = g_prev['img'].copy()
        im.thumbnail((max(40, w - 10), max(40, h - 10)), Image.LANCZOS)
        g_prev['pi'] = ImageTk.PhotoImage(im)
        prev_cv.create_image(w // 2, h // 2, image=g_prev['pi'])

    def _prev_resized(_e=None):
        if g_prev['job']:
            try:
                prev_cv.after_cancel(g_prev['job'])
            except Exception:
                pass
        g_prev['job'] = prev_cv.after(120, _draw_prev)

    prev_cv.bind('<Configure>', _prev_resized)

    grow = ttk.Frame(right)
    grow.pack(fill='x', pady=(0, 4))
    ttk.Label(grow, text='输出文件夹：').pack(side='left')
    ttk.Entry(grow, textvariable=g_out, width=54).pack(side='left', padx=(4, 6))
    ttk.Button(grow, text='浏览…', command=lambda: browse(g_out, kind='dir', title='选择输出文件夹')).pack(side='left')

    grow2 = ttk.Frame(right)
    grow2.pack(fill='x', pady=(0, 6))
    ttk.Label(grow2, text='输出名：').pack(side='left')
    ttk.Entry(grow2, textvariable=g_name, width=22).pack(side='left', padx=(4, 12))
    ttk.Label(grow2, text='尺寸：').pack(side='left')
    ttk.Combobox(grow2, textvariable=g_size, values=G_SIZES, width=6,
                 state='readonly').pack(side='left', padx=(4, 12))
    ttk.Label(grow2, text='<名字>.dds (BC7) + <名字>_front.png + <名字>_side.png',
              foreground='#777').pack(side='left')

    log3_wrap = ttk.Frame(right)
    log3 = tk.Text(log3_wrap, height=8, wrap='word')
    log3_vs = ttk.Scrollbar(log3_wrap, orient='vertical', command=log3.yview)
    log3.configure(yscrollcommand=log3_vs.set)
    log3.pack(side='left', fill='both', expand=True)
    log3_vs.pack(side='right', fill='y')
    log3_wrap.pack(fill='x', pady=(0, 6))
    btn_g2 = ttk.Button(right, text='④ 生成卡片（与「卡片生成」同一版式）')
    btn_g2.pack(fill='x')

    def log3_to(msg):
        log3.insert('end', msg + '\n')
        log3.see('end')
        root.update_idletasks()

    def g_refresh():
        for key in ('front', 'side'):
            d = g_state[key]
            im = d['img']
            if im is None:
                d['thumb'] = None
                d['lbl'].configure(image='', text='点「截图」\n框选方图\n或「选图…」')
            else:
                th = im.copy()
                th.thumbnail((SQUARE_PX - 4, SQUARE_PX - 4), Image.LANCZOS)
                d['thumb'] = ImageTk.PhotoImage(th)
                d['lbl'].configure(image=d['thumb'], text='')
        if g_state['front']['img'] is None and g_state['side']['img'] is None:
            g_prev['img'] = None
            _draw_prev()
            return
        bk = Image.new('RGB', (10, 10), BG)
        # 存一张高分辨率缓存，显示时按画布大小缩放（放大窗口也不会糊）
        g_prev['img'] = compose_card(g_state['front']['img'] or bk,
                                     g_state['side']['img'] or bk, 900)
        _draw_prev()

    def g_set(key, im):
        if im is not None:
            if max(im.size) > 1600:
                r = 1600.0 / max(im.size)
                im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
            im = square_crop(im, 1024)
        g_state[key]['img'] = im
        g_refresh()
        if im is not None:
            log3_to('%s：%d×%d' % ('正面' if key == 'front' else '侧面', im.width, im.height))

    def g_shoot(key):
        try:
            shoot_screen(root, lambda im, k=key: g_set(k, im))
        except Exception:
            log3_to(traceback.format_exc())
            messagebox.showerror('截图失败', '无法截图，可以改用「选图…」')

    def g_pick(key):
        p = filedialog.askopenfilename(
            title='选择%s图' % ('正面' if key == 'front' else '侧面'),
            filetypes=[('图片', '*.png *.jpg *.jpeg *.bmp *.tif *.tiff'), ('所有文件', '*.*')])
        if not p:
            return
        try:
            g_set(key, Image.open(p).convert('RGB'))
        except Exception as e:
            messagebox.showerror('读取失败', str(e))

    def g_clear(key):
        g_state[key]['img'] = None
        g_refresh()

    def g_job():
        if g_state['front']['img'] is None or g_state['side']['img'] is None:
            messagebox.showwarning('缺少画面', '正面和侧面都要有画面：点「截图」框选，或「选图…」')
            return
        name = g_name.get().strip()
        if not name:
            messagebox.showerror('缺少输出名', '请填写输出名（会生成 <名字>.dds / _front.png / _side.png）')
            return
        out = g_out.get().strip() or APP_DIR
        btn_g2.configure(state='disabled')
        log3.delete('1.0', 'end')

        def work():
            try:
                size = int(g_size.get() or 1024)
                png, dds = build_card(g_state['front']['img'], g_state['side']['img'],
                                      size, out, name)
                wh = dds_size(dds)
                root.after(0, lambda: log3_to('PNG -> %s  (%d×%d)' % (png, size, size)))
                root.after(0, lambda: log3_to('DDS -> %s  (%s)'
                                              % (dds, ('%d×%d' % wh) if wh else '尺寸未知')))
                root.after(0, lambda: carddds.set(dds))
                root.after(0, lambda: messagebox.showinfo('完成', dds))
            except Exception as e:
                msg = str(e)
                root.after(0, lambda: log3_to(traceback.format_exc()))
                root.after(0, lambda: messagebox.showerror('失败', msg))
            finally:
                root.after(0, lambda: btn_g2.configure(state='normal'))

        threading.Thread(target=work, daemon=True).start()

    btn_g2.configure(command=g_job)
    g_refresh()
    root.after(400, _draw_prev)

    # ---------------- tab 3 盒子 + ESP（页签③） ----------------
    src_esp = tk.StringVar()
    mods_root = tk.StringVar(value=_settings.get('mods_root') or r'D:\Modding\MO2\mods')
    mod_name = tk.StringVar()
    _gd_default = _settings.get('game_data') or r'D:\SteamLibrary\steamapps\common\Skyrim Special Edition\Data'
    if not os.path.isdir(_gd_default):
        _gd_default = ''
    game_data = tk.StringVar(value=_gd_default)
    style_var = tk.StringVar()
    edid_var = tk.StringVar()
    full_var = tk.StringVar()
    csub = tk.StringVar(value='')                  # 服装 Meshes 子目录，选发型后自动 <ESP名>\Hair\<NIF名>
    msub = tk.StringVar(value='BoxWorld\\hair')    # 世界模型 Meshes 子目录（盒子 NIF）
    tsub = tk.StringVar(value='BoxWorld\\hair')    # 服装 Textures 子目录（头发贴图）
    bsub = tk.StringVar(value='BoxWorld\\hair')    # 世界模型 Textures 子目录（盒子/卡片贴图）
    tex_prefix = tk.StringVar(value='new_')                 # 复制头发贴图时加的前缀
    card_sub = tk.StringVar(value='BoxWorld\\hair\\Card')    # 卡片 dds 子目录
    card_name_v = tk.StringVar(value='')                    # 卡片 dds 名（留空 = <穿着NIF名>_Card）
    nif_name_var = tk.StringVar()
    xml_name_var = tk.StringVar(value='physics.xml')
    box_name_var = tk.StringVar()
    out2 = tk.StringVar(value=APP_DIR)
    esp_name = tk.StringVar(value='Hair_BoxWorld')   # ESP 文件名（不含 .esp）
    esp_hint = tk.StringVar(value='')
    card_hint = tk.StringVar(value='')
    tpl_var = tk.StringVar(value='materials\\1_go.nif')   # 相对软件目录
    boxdds = tk.StringVar(value='materials\\box.dds')
    boxn = tk.StringVar(value='materials\\box_n.dds')
    glass = tk.StringVar(value='materials\\glass_n.dds')
    carddds = tk.StringVar()
    styles = []
    asset_rows = []
    mod_names = []

    ttk.Label(t2, text='操作顺序：① 选源 ESP → ② 选发型（下拉可打字模糊搜索）→ ③ 选 mod（选完 ESP 会自动切到它所在的 mod 并定位 DDS/XML）'
                       ' → ④ 自定义命名 → ⑤ 生成', foreground='#555').grid(
        row=0, column=0, columnspan=4, sticky='w', pady=(0, 8))

    r = 1

    def browse(var, kind='file', types=None, title='选择'):
        p = (filedialog.askdirectory(title=title) if kind == 'dir'
             else filedialog.askopenfilename(title=title, filetypes=types or [('所有文件', '*.*')]))
        if p:
            var.set(p)
        return p

    def _abs(p):
        """模板/贴图那行按“相对软件目录”解析；填绝对路径也认。"""
        p = (p or '').strip()
        if not p:
            return ''
        return p if os.path.isabs(p) else os.path.join(APP_DIR, p)

    bsa_hint = [False]

    def bsa_remind():
        """还没扫过 BSA 时提醒一次（选 ESP / 选发型 都会走到这里）。"""
        if BSA_CACHE['index'] or bsa_hint[0]:
            return
        bsa_hint[0] = True
        log2_to('提示：还没执行过 BSA 扫描。点菜单「设置 → 扫描 BSA（mods + 游戏）」，'
                '之后才能真正判断“贴图是否在 BSA 里”。')
        try:
            messagebox.showinfo('建议先扫描 BSA',
                                '素材表里标「缺失」的贴图，有一部分其实在 BSA 里。\n\n'
                                '先点菜单：设置 → 扫描 BSA（mods + 游戏）\n'
                                '扫完之后再看素材表，误报会少很多。')
        except Exception:
            pass

    def refresh_styles():
        nonlocal styles
        p = src_esp.get().strip()
        if not p or not os.path.exists(p):
            return
        import boxesp
        try:
            styles = boxesp.describe(p)
        except Exception as e:
            log2_to('读取 ESP 失败：%s' % e)
            return
        vals = ['%s — %s' % (s['edid'], s['full']) for s in styles]
        cb.refresh_values(filt='')
        cb['values'] = vals
        if vals:
            cur = style_var.get()
            if cur not in vals:          # 保留用户已选的发型，只有失效时才回落到第一个
                style_var.set(vals[0])
            log2_to('源 ESP 里找到 %d 个发型记录' % len(vals))
        bsa_remind()             # 没扫过 BSA 就提醒一次（选完 ESP 就会走到这里）
        sync_mod_from_esp()      # ① 源 ESP 所在文件夹 → mod 列表
        on_style()               # ② 穿着 NIF / 盒子 NIF 跟源发型同名 + 服装子目录

    def sync_mod_from_esp():
        """把 mod 列表切到源 ESP 所在的那个 mod 文件夹（在 mods 根目录下找一个存在的层）。"""
        p = src_esp.get().strip()
        if not p:
            return
        d = os.path.dirname(os.path.abspath(p))
        rootd = os.path.abspath(mods_root.get().strip() or '')
        name = ''
        if rootd and os.path.isdir(rootd):
            try:
                rel = os.path.relpath(d, rootd)
            except ValueError:
                rel = '..'
            if rel and not rel.startswith('..'):
                name = rel.split(os.sep)[0]
        if not name:
            name = os.path.basename(d)
        if name:
            if name not in mod_names:
                mod_names.append(name)
                modcb.refresh_values(filt='')
            if mod_name.get().strip() != name:
                mod_name.set(name)
                log2_to('mod 列表已切到源 ESP 所在 mod：%s' % name)

    def pick_src_esp():
        if browse(src_esp, types=[('ESP/ESM', '*.esp *.esm'), ('所有文件', '*.*')], title='选择源 ESP'):
            refresh_styles()

    _boldfont = tkfont.nametofont('TkDefaultFont').copy()
    _boldfont.configure(weight='bold')

    def _sec(title):
        nonlocal r
        ttk.Separator(t2, orient='horizontal').grid(row=r, column=0, columnspan=4, sticky='we', pady=(8, 3))
        r += 1
        ttk.Label(t2, text=title, font=_boldfont).grid(row=r, column=0, columnspan=4, sticky='w', pady=(0, 3))
        r += 1

    _sec('① 源 ESP / ② 源发型')
    src_row = ttk.Frame(t2)
    src_row.grid(row=r, column=0, columnspan=4, sticky='we')
    ttk.Label(src_row, text='源 ESP：').pack(side='left')
    C_OK, C_FOLLOW, C_CHANGE, C_REQ = '#ffffff', '#e3ecfa', '#fdeccd', '#fadada'
    RING = {'ok': '#cfcfcf', 'follow': '#9dbcf0', 'change': '#e8b56a', 'req': '#e08a8a'}
    BG_STATE = {'ok': C_OK, 'follow': C_FOLLOW, 'change': C_CHANGE, 'req': C_REQ}
    rings = {}

    def _ent(master, var, width, **kw):
        return tk.Entry(master, textvariable=var, width=width, relief='solid', bd=1,
                        highlightthickness=0, bg=C_OK, **kw)

    def set_state(w, st='ok'):
        try:
            if isinstance(w, tk.Entry):
                w.configure(bg=BG_STATE[st])
            else:
                r = rings.get(w)
                if r is not None:
                    r.configure(highlightbackground=RING[st])
        except tk.TclError:
            pass

    src_entry = _ent(src_row, src_esp, 58)
    ttk.Button(src_row, text='浏览…', command=pick_src_esp).pack(side='right')
    src_entry.pack(side='left', fill='x', expand=True, padx=(4, 6))
    src_entry.bind('<Return>', lambda e: refresh_styles())
    src_entry.bind('<KP_Enter>', lambda e: refresh_styles())
    src_entry.bind('<FocusOut>', lambda e: refresh_styles())
    r += 1
    style_row = ttk.Frame(t2)
    style_row.grid(row=r, column=0, columnspan=4, sticky='we')
    ttk.Label(style_row, text='② 源发型：').pack(side='left')

    def _style_vals():
        return ['%s — %s' % (x['edid'], x['full']) for x in styles]
    cb_ring = tk.Frame(style_row, highlightthickness=2, highlightbackground=RING['ok'], bd=0)
    cb_ring.pack(side='left', fill='x', expand=True, padx=(4, 0))
    cb = FuzzyCombo(cb_ring, values_getter=_style_vals, on_pick=lambda: on_style(),
                    textvariable=style_var, width=70)
    cb.pack(fill='x', expand=True)
    rings[cb] = cb_ring
    r += 1
    edid_row = ttk.Frame(t2)
    edid_row.grid(row=r, column=0, columnspan=4, sticky='we')
    ttk.Label(edid_row, text='新 EDID：').pack(side='left')
    edid_entry = _ent(edid_row, edid_var, 26)
    edid_entry.pack(side='left', padx=(4, 14))
    ttk.Label(edid_row, text='显示名：').pack(side='left')
    full_entry = _ent(edid_row, full_var, 34)
    full_entry.pack(side='left', fill='x', expand=True, padx=(4, 0))
    r += 1

    _sec('③ mod 与素材定位（贴图路径写错也能改）')
    mod_row = ttk.Frame(t2)
    mod_row.grid(row=r, column=0, columnspan=4, sticky='we', pady=(2, 2))
    ttk.Label(mod_row, text='mod 列表：').pack(side='left')

    def refresh_mods(quiet=False):
        nonlocal mod_names
        d = mods_root.get().strip()
        try:
            mod_names = scan_mods(d) if d else []
        except Exception as e:
            log2_to('扫描 mods 失败：%s' % e)
            mod_names = []
        modcb.refresh_values(filt='')
        if not quiet:
            log2_to('mod 列表：%d 个（%s）' % (len(mod_names), d))

    mod_ring = tk.Frame(mod_row, highlightthickness=2, highlightbackground=RING['ok'], bd=0)
    mod_ring.pack(side='left', padx=(4, 6))
    modcb = FuzzyCombo(mod_ring, values_getter=lambda: mod_names, textvariable=mod_name, width=42)
    modcb.pack(fill='x', expand=True)
    rings[modcb] = mod_ring
    ttk.Button(mod_row, text='扫描 mods', command=lambda: refresh_mods()).pack(side='left')
    ttk.Button(mod_row, text='定位素材', command=lambda: locate()).pack(side='left', padx=(6, 0))
    ttk.Button(mod_row, text='生成 BodySlide 工程…', command=lambda: make_bs_shell()).pack(side='left', padx=(6, 0))
    ttk.Button(mod_row, text='打开 BodySlide', command=lambda: open_bodyslide()).pack(side='left', padx=(6, 0))
    ttk.Button(mod_row, text='打开 Outfit Studio',
               command=lambda: open_bodyslide('os')).pack(side='left', padx=(6, 0))
    r += 1
    ttk.Label(t2, text='（mods 根目录 / 游戏 Data 在「设置 → 路径设置…」里改）',
              foreground='#777').grid(row=r, column=0, columnspan=4, sticky='w')
    r += 1

    tex_fix = {}        # {(nif 文件名小写, 原始贴图串小写): 修正后的相对路径 或 '' = 不使用}
    row_meta = {}       # iid -> 该行的原始信息，供右键修改/撤销

    tree = ttk.Treeview(t2, columns=('kind', 'rel', 'src'), show='headings', height=9)
    for c, tx, w in (('kind', '类型', 80), ('rel', 'NIF 内引用', 330), ('src', '在 mod 中找到', 470)):
        tree.heading(c, text=tx)
        tree.column(c, width=w, anchor='w')
    tree.grid(row=r, column=0, columnspan=3, sticky='nsew')
    t2.rowconfigure(r, weight=3)
    tree_vs = ttk.Scrollbar(t2, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=tree_vs.set)
    tree_vs.grid(row=r, column=3, sticky='ns')
    tree_rows = {}

    def _open_row(mode='file'):
        sel = tree.selection()
        if not sel:
            return
        p = tree_rows.get(sel[0]) or ''
        if not p or not os.path.exists(p):
            log2_to('这一行没有可打开的文件')
            return
        try:
            if p.lower().endswith(('.osp', '.xml')):
                subprocess.Popen(['explorer', '/select,', os.path.abspath(p)])
                return
            if mode == 'folder' and not os.path.isdir(p):
                subprocess.Popen(['explorer', '/select,', os.path.abspath(p)])
            else:
                os.startfile(os.path.dirname(p) if mode == 'folder' else p)
        except Exception as e:
            log2_to('打开失败：%s' % e)

    tree_menu = tk.Menu(root, tearoff=0)
    tree_menu.add_command(label='打开文件', command=lambda: _open_row('file'))
    tree_menu.add_command(label='打开所在文件夹', command=lambda: _open_row('folder'))
    tree_menu.add_separator()
    tree_menu.add_command(label='指定这张贴图用的 DDS 文件…', command=lambda: _edit_row())
    tree_menu.add_command(label='不使用这张贴图（清空该槽）', command=lambda: _drop_row())
    tree_menu.add_command(label='撤销这一行的修改', command=lambda: _undo_row())

    def _sel_meta():
        sel = tree.selection()
        return row_meta.get(sel[0]) if sel else None

    def _edit_row():
        m = _sel_meta()
        if not m:
            return
        if not m.get('key'):
            log2_to('只有「贴图」行可以指定文件（穿着 NIF / XML 用下面的命名框改）')
            return
        cur = m['psrc'] or ''
        f = filedialog.askopenfilename(
            title='这一行在 NIF 里写的是：%s —— 选一个 DDS 给它用' % (m['raw'] or '').replace('\n', '\\n'),
            initialdir=os.path.dirname(cur) if cur and os.path.exists(cur) else APP_DIR,
            filetypes=[('DDS 贴图', '*.dds'), ('所有文件', '*.*')], parent=root)
        if not f:
            return
        tex_fix[m['key']] = f
        log2_to('已指定文件：%s -> %s' % (clean_tex_path(m['raw']), f))
        locate(quiet=True)

    def _drop_row():
        m = _sel_meta()
        if not m or not m.get('key'):
            log2_to('只有「贴图」行可以移除')
            return
        tex_fix[m['key']] = ''
        log2_to('已移除：%s（生成时不复制这张贴图）' % clean_tex_path(m['raw']))
        locate(quiet=True)

    def _undo_row():
        m = _sel_meta()
        if not m or not m.get('key'):
            return
        if tex_fix.pop(m['key'], None) is None:
            log2_to('这一行没有手动修改过')
            return
        log2_to('已撤销修改：%s' % clean_tex_path(m['raw']))
        locate(quiet=True)

    def _tree_menu(e):
        iid = tree.identify_row(e.y)
        if iid:
            tree.selection_set(iid)
            tree_menu.tk_popup(e.x_root, e.y_root)

    tree.bind('<Double-1>', lambda e: _open_row('file'))
    tree.bind('<Button-3>', _tree_menu)
    tree.tag_configure('fixed', foreground='#0a62c0')
    tree.tag_configure('drop', foreground='#8a8a8a')
    r += 1
    ttk.Label(t2, text='（双击=打开文件；右键=指定这张贴图用的 DDS / 清空这一行 / 撤销；'
                       '缺失的贴图必须先「指定文件」或「清空」才能生成）',
              foreground='#777').grid(row=r, column=0, columnspan=4, sticky='w')
    r += 1

    _sec('④ 命名（左右两组都能自己改名）')
    # ---- 命名（左：服装/头发   右：世界模型/盒子）----
    nf = ttk.Frame(t2)
    nf.grid(row=r, column=0, columnspan=4, sticky='we', pady=(2, 2))
    bL = ttk.LabelFrame(nf, text=' 服装（头发） ')
    bL.pack(side='left', fill='x', expand=True, padx=(0, 8))
    bR = ttk.LabelFrame(nf, text=' 世界模型（盒子） ')
    bR.pack(side='left', fill='x', expand=True)
    for _b in (bL, bR):
        _b.columnconfigure(1, weight=1)

    def _lab(parent, txt, row):
        ttk.Label(parent, text=txt).grid(row=row, column=0, sticky='e', padx=(4, 4), pady=2)

    def _entg(parent, var, w, row):
        e = _ent(parent, var, w)
        e.grid(row=row, column=1, sticky='we', padx=(0, 8), pady=2)
        return e

    _lab(bL, 'Meshes 子目录', 0)
    csub_entry = _entg(bL, csub, 26, 0)
    _lab(bL, 'Textures 子目录', 1)
    tsub_entry = _entg(bL, tsub, 26, 1)
    _lab(bL, '穿着 NIF', 2)
    nifname_entry = _entg(bL, nif_name_var, 26, 2)
    _lab(bL, 'XML 名', 3)
    xmlname_entry = _entg(bL, xml_name_var, 26, 3)

    _lab(bR, 'Meshes 子目录', 0)
    msub_entry = _entg(bR, msub, 26, 0)
    _lab(bR, 'Textures 子目录', 1)
    bsub_entry = _entg(bR, bsub, 26, 1)
    _lab(bR, '盒子 NIF 名', 2)
    boxname_entry = _entg(bR, box_name_var, 26, 2)
    _lab(bR, '卡片子目录', 3)
    cardsub_entry = _entg(bR, card_sub, 26, 3)
    r += 1

    nf3 = ttk.Frame(t2)
    nf3.grid(row=r, column=0, columnspan=4, sticky='we', pady=(0, 4))
    ttk.Label(nf3, text='贴图前缀:').pack(side='left')
    prefix_entry = _ent(nf3, tex_prefix, 10)
    prefix_entry.pack(side='left', padx=(3, 12))
    ttk.Label(nf3, text='卡片名称:').pack(side='left')
    cardname_entry = _ent(nf3, card_name_v, 22)
    cardname_entry.pack(side='left', padx=(3, 6))
    ttk.Label(nf3, text='（留空 = <穿着NIF名>_Card.dds）', foreground='#777').pack(side='left')
    r += 1

    _sec('⑤ 输出与生成')
    ttk.Label(t2, text='输出文件夹：').grid(row=r, column=0, sticky='w')
    out2_entry = _ent(t2, out2, 78)
    out2_entry.grid(row=r, column=1, columnspan=2, sticky='we')
    ttk.Button(t2, text='浏览…', command=lambda: browse(out2, kind='dir')).grid(row=r, column=3, padx=(6, 0))
    r += 1
    ttk.Label(t2, text='ESP 文件名：').grid(row=r, column=0, sticky='w')
    esp_row = ttk.Frame(t2)
    esp_row.grid(row=r, column=1, columnspan=2, sticky='we')
    esp_entry = _ent(esp_row, esp_name, 30)
    esp_entry.pack(side='left')
    ttk.Label(esp_row, text='.esp').pack(side='left', padx=(2, 10))
    ttk.Button(esp_row, text='选已有 ESP…', command=lambda: pick_esp_file()).pack(side='left')
    r += 1
    esp_hint_lbl = ttk.Label(t2, textvariable=esp_hint, foreground='#777')
    esp_hint_lbl.grid(row=r, column=1, columnspan=3, sticky='w')
    r += 1
    ttk.Label(t2, text='（新 ARMO/ARMA 写进这个 esp：不存在就新建；已存在就追加，EDID 自动改成 <新EDID>_BOX<n>，'
                       '并沿用它已经建好的世界模型（只新增替换纹理 TXST））', foreground='#777').grid(
        row=r, column=1, columnspan=3, sticky='w')
    r += 1

    mat = ttk.Frame(t2)
    mat.grid(row=r, column=0, columnspan=4, sticky='we', pady=(4, 2))
    ttk.Label(mat, text='模板/贴图(相对软件目录):').pack(side='left')
    for lab, var in (('模板', tpl_var), ('box', boxdds), ('box_n', boxn), ('glass_n', glass)):
        ttk.Label(mat, text=lab + ':').pack(side='left')
        ttk.Entry(mat, textvariable=var, width=18).pack(side='left', padx=(2, 6))
    r += 1

    cardrow = ttk.Frame(t2)
    cardrow.grid(row=r, column=0, columnspan=4, sticky='we', pady=(0, 4))
    ttk.Label(cardrow, text='卡片:').pack(side='left')
    card_entry = _ent(cardrow, carddds, 62)
    card_entry.pack(side='left', padx=(3, 6))
    card_name_auto = [True]      # True = 用户没手改过，卡片名跟着穿着 NIF 自动变

    def card_default():
        st = os.path.splitext((nif_name_var.get() or '').strip())[0]
        return (st + '_Card') if st else ''

    def sync_card_name(*_a):
        if card_name_auto[0] or not (card_name_v.get() or '').strip():
            d = card_default()
            if d:
                card_name_v.set(d)
                card_name_auto[0] = True

    def card_name_typed(_e=None):
        # 手动清空 -> 回到自动模式；手填 -> 就不再被发型覆盖
        card_name_auto[0] = not (card_name_v.get() or '').strip()

    cardname_entry.bind('<KeyRelease>', card_name_typed, add='+')

    def pick_card():
        dd = browse(carddds, types=[('DDS 贴图', '*.dds'), ('所有文件', '*.*')], title='选择卡片 dds')
        if carddds.get().strip():
            sync_card_name()

    def preview_card():
        p = (carddds.get() or '').strip()
        if not p or not os.path.exists(p):
            messagebox.showwarning('提示', '先选一张卡片 dds 再预览')
            return
        try:
            os.startfile(p)                      # 直接用系统默认程序打开（和素材表双击一致）
            log2_to('预览卡片：' + p)
        except Exception as e:
            messagebox.showerror('预览失败', str(e))

    ttk.Button(cardrow, text='浏览…', command=lambda: pick_card()).pack(side='left')
    ttk.Button(cardrow, text='预览', command=lambda: preview_card()).pack(side='left', padx=(4, 0))
    nif_name_var.trace_add('write', sync_card_name)
    sync_card_name()
    ttk.Label(cardrow, textvariable=card_hint, foreground='#777').pack(side='left', padx=(8, 0))
    r += 1

    ToolTip(esp_entry, '生成/追加的 ESP 文件名，默认 Hair_BoxWorld。\n'
                       '下面那行实时显示完整路径，并区分「新建」与「已存在：追加」。')
    ToolTip(csub_entry, '服装（头发）Meshes 子目录，穿着 NIF 与 XML 放这里。\n'
                        '默认 <ESP名>\\Hair\\<发型名>，可随意改。')
    ToolTip(msub_entry, '世界模型（盒子）Meshes 子目录，盒子的 NIF 放这里。默认 BoxWorld\\hair。')
    ToolTip(tsub_entry, '服装（头发）Textures 子目录，复制过来的头发贴图放这里。')
    ToolTip(bsub_entry, '世界模型 Textures 子目录，木箱/玻璃法线等贴图放这里。')
    ToolTip(prefix_entry, '复制头发贴图时加在文件名前的字符串（默认 new_）。\n'
                          '防止和 mod 里已有同名贴图互相覆盖，也方便区分是哪套卡片。')
    ToolTip(cardsub_entry, '卡片 dds 单独放这个子目录，默认 BoxWorld\\hair\\Card。\n'
                           '和世界模型的其它贴图分开，找起来更清楚。')
    ToolTip(cardname_entry, '输出的卡片文件名（不含 .dds 也行）。\n'
                            '留空 = 用自己的穿着 NIF 名 + _Card，例如 flower_Card.dds。')
    ToolTip(card_entry, '卡片 dds 本体：页签①/②生成后会自动填到这里，也可以自己选一张现成的。')
    ToolTip(nifname_entry, '穿着 NIF 的文件名；换源发型时会自动跟着变。')

    log2_wrap = ttk.Frame(t2)
    log2_wrap.grid(row=r, column=0, columnspan=4, sticky='nsew', pady=(4, 4))
    t2.rowconfigure(r, weight=2)
    log2 = tk.Text(log2_wrap, height=7, wrap='word')
    log2_vs = ttk.Scrollbar(log2_wrap, orient='vertical', command=log2.yview)
    log2.configure(yscrollcommand=log2_vs.set)
    log2.pack(side='left', fill='both', expand=True)
    log2_vs.pack(side='right', fill='y')
    r += 1
    def clean_out():
        out = (out2.get() or '').strip()
        if not out or not os.path.isdir(out):
            messagebox.showwarning('提示', '输出文件夹不存在：\n%s' % out)
            return
        drive, _ = os.path.splitdrive(os.path.abspath(out))
        if os.path.abspath(out).rstrip('\\').lower() == (drive + '\\').lower():
            messagebox.showerror('拒绝', '输出文件夹是盘符根目录，不能在这里删。')
            return
        tgt = [os.path.join(out, 'Meshes'), os.path.join(out, 'Textures')]
        exist = [p for p in tgt if os.path.isdir(p)]
        if not exist:
            messagebox.showinfo('提示', '输出文件夹下没有 Meshes / Textures：\n%s' % out)
            return
        cnt, size = 0, 0
        for p in exist:
            for dp, _dn, fn in os.walk(p):
                for f in fn:
                    cnt += 1
                    try:
                        size += os.path.getsize(os.path.join(dp, f))
                    except OSError:
                        pass
        if not messagebox.askyesno('确认删除', (
                '将删除以下文件夹（不可恢复）：\n\n%s\n\n共 %d 个文件，%.1f MB。\n\n确定继续吗？'
                % ('\n'.join(exist), cnt, size / 1048576.0)), icon='warning'):
            return
        errs = []
        for p in exist:
            try:
                shutil.rmtree(p)
            except Exception as e:
                errs.append('%s: %s' % (p, e))
        if errs:
            messagebox.showerror('删除失败', '\n'.join(errs))
        log2_to('已删除：%s（%d 个文件，%.1f MB）' % ('；'.join(exist), cnt, size / 1048576.0))
        if not errs:
            messagebox.showinfo('完成', '已删除 %d 个文件（%.1f MB）。' % (cnt, size / 1048576.0))

    clean_row = ttk.Frame(t2)
    clean_row.grid(row=r, column=0, columnspan=4, sticky='we', pady=(0, 4))
    ttk.Button(clean_row, text='清空输出文件夹下的 Meshes / Textures…',
               command=lambda: clean_out()).pack(side='left')
    ttk.Label(clean_row, text='（先弹确认框，列出要删的文件夹和文件数；只在当前「输出文件夹」下删）',
              foreground='#777').pack(side='left', padx=(8, 0))
    r += 1

    leg = ttk.Frame(t2)
    leg.grid(row=r, column=0, columnspan=4, sticky='we', pady=(6, 2))
    ttk.Label(leg, text='图例：').pack(side='left')
    for _txt, _col in (('正常', C_OK), ('随发型更新', C_FOLLOW), ('要改 / 将追加', C_CHANGE), ('必填', C_REQ)):
        tk.Label(leg, text='    ', bg=_col, relief='solid', bd=1).pack(side='left', padx=(6, 3))
        ttk.Label(leg, text=_txt).pack(side='left')
    ttk.Label(leg, text='（框底色 = 状态）', foreground='#777').pack(side='left', padx=(10, 0))
    r += 1

    btn_box = ttk.Button(t2, text='生成（复制 NIF / DDS / XML + 盒子 + ESP）')
    btn_box.grid(row=r, column=0, columnspan=4, sticky='we')
    r += 1
    job_hint = tk.Label(t2, text='', fg='#c00000', anchor='w', justify='left')
    job_hint.grid(row=r, column=0, columnspan=4, sticky='we')
    t2.columnconfigure(1, weight=1)

    def log2_to(msg):
        log2.insert('end', msg + '\n')
        log2.see('end')
        root.update_idletasks()

    def selected_style():
        s = style_var.get()
        for x in styles:
            if s.startswith(x['edid'] + ' — '):
                return x
        return None

    def on_style(*_):
        s = selected_style()
        if not s:
            return
        before = {'csub': csub.get(), 'tsub': tsub.get(), 'nif': nif_name_var.get(),
                  'box': box_name_var.get(), 'card': card_name_v.get()}
        edid_var.set(s['edid'])
        full_var.set(s['full'])
        base = os.path.basename((s['mod3'] or s['mod4']).replace('/', '\\')) or (s['edid'] + '.nif')
        nif_name_var.set(base)                                   # 穿着 NIF 跟源发型文件同名
        box_name_var.set(os.path.splitext(base)[0] + '_box.nif') # 盒子 NIF 也跟着同名
        esp_stem = os.path.splitext(os.path.basename(src_esp.get().strip()))[0] or 'Hair'
        stem = os.path.splitext(base)[0]
        # 服装素材默认按「ESP 名 \ Hair \ 发型名」分类：一套发型一个文件夹，越加越多也不打架
        csub.set('%s\\Hair\\%s' % (esp_stem, stem))            # 服装 Meshes 子目录
        tsub.set(csub.get())                                     # 服装 Textures 与 Meshes 同构
        # 3) 把「因为换发型而跟着变」的框标出来，并说明原因
        followed = []
        for key, w, var, label in (('csub', csub_entry, csub, '服装 Meshes'),
                                   ('tsub', tsub_entry, tsub, '服装 Textures'),
                                   ('nif', nifname_entry, nif_name_var, '穿着 NIF'),
                                   ('box', boxname_entry, box_name_var, '盒子 NIF 名'),
                                   ('card', cardname_entry, card_name_v, '卡片名称')):
            cur = (var.get() or '')
            if cur != (before[key] or ''):
                followed.append(label)
                set_state(w, 'follow')
        if followed:
            for w in (edid_entry, full_entry):
                set_state(w, 'change')
            job_hint.configure(fg='#1f6fb2', text=(
                '源发型已切换：%s 跟着更新了；新 EDID / 显示名 也要按新发型改（淡橙框）。'
                % '、'.join(followed)))
        _upd_esp_hint()                     # 换发型后再校验一次 ESP 文件名
        if mod_name.get().strip():
            locate(quiet=True)                                   # 自动定位素材

    cb.bind('<<ComboboxSelected>>', lambda e: on_style())

    def locate(quiet=False):
        nonlocal asset_rows
        try:
            _index_cache.pop(mod_name.get().strip(), None)
        except Exception:
            pass
        for it in tree.get_children():
            tree.delete(it)
        tree_rows.clear()
        row_meta.clear()
        asset_rows = []
        s = selected_style()
        if not s:
            if not quiet:
                messagebox.showwarning('提示', '先选源发型')
            return
        mod = mod_name.get().strip()
        if not mod:
            if not quiet:
                messagebox.showwarning('提示', '先选 mod')
            return
        moddir = os.path.join(mods_root.get(), mod)
        bsa_idx = dict(BSA_CACHE['index'])
        bsa_dirs_use = [moddir]
        gd = (game_data.get() or '').strip()
        if gd:
            bsa_dirs_use.append(gd)
        try:
            for k, v in bsa.build_index(bsa_dirs_use).items():
                bsa_idx.setdefault(k, v)
            if bsa_idx:
                log2_to('BSA 索引：%d 个文件（含游戏 Data%s）' % (
                    len(bsa_idx), ' 与缓存' if BSA_CACHE['index'] else ''))
        except Exception:
            log2_to(traceback.format_exc())
        try:
            import nifpatch
            worn = s['mod3'].replace('/', '\\') or s['mod4'].replace('/', '\\')
            wa = find_in_mod(moddir, worn)
            if not wa:
                if not quiet:
                    messagebox.showerror('找不到', 'mod 里没有该 NIF：' + worn)
                else:
                    log2_to('定位失败：mod 里没有该 NIF：' + worn)
                return
            doc = nifpatch.load(wa)
            tex = nifpatch.texset_paths(doc)
            xmls = nifpatch.xml_strings(doc)
            fixed_note = []
            nif_key = os.path.basename(worn).lower()
            seen_tex = set()
            rows = []
            for t in tex:
                raw_lower = t.rstrip('\x00').lower()
                if raw_lower in seen_tex:
                    continue
                seen_tex.add(raw_lower)
                key = (nif_key, raw_lower)
                psrc = ''
                if key in tex_fix:
                    val = tex_fix[key] or ''
                    if not val:
                        mark, eff, found = '贴图 ⊘', '（不使用，生成时清空该槽）', ''
                    else:
                        psrc = val
                        mark = '贴图 ✎'
                        eff = rel_to_root(val, [moddir, mods_root.get()])
                        found = val if os.path.exists(val) else ''
                else:
                    eff = clean_tex_path(t)
                    mark = '贴图'
                    found = find_in_mod(moddir, eff) if eff else ''
                    if eff != t:
                        fixed_note.append('%s -> %s' % (t.replace('\n', '\\n'), eff))
                disp = found or ''
                bsa_hit = ''
                if not disp and eff and bsa_idx:
                    bsa_hit = bsa.find(bsa_idx, eff) or ''
                    if bsa_hit:
                        mark = '贴图 BSA'
                        disp = '在 %s 中（保留原路径，不复制）' % os.path.basename(bsa_hit)
                rows.append((mark, eff, found, key, t, eff, psrc, disp, bsa_hit))
            allrows = [('穿着 NIF', worn, wa, None, None, worn, '', wa, '')] + \
                [('XML', x, find_in_mod(moddir, x), None, None, x, '', find_in_mod(moddir, x), '')
                 for x in xmls] + rows
            try:
                for _p, _k in scan_bodyslide(moddir, os.path.basename(worn)):
                    _rel = os.path.relpath(_p, moddir)
                    allrows.append(('BS 工程', _rel, _p, None, None, _rel, '', _p, ''))
            except Exception:
                log2_to(traceback.format_exc())
            for kind, rel, found, key, raw, eff, psrc, disp, bsa_hit in allrows:
                asset_rows.append(dict(kind=kind, rel=rel, src=found or bsa_hit))
                iid = tree.insert('', 'end', values=(kind, rel, disp or ('—' if not rel else '✗ 缺失')))
                tree_rows[iid] = found or ''
                row_meta[iid] = dict(kind=kind, key=key, raw=raw, eff=eff, psrc=psrc,
                                     bsa=bsa_hit)
            if fixed_note:
                log2_to('贴图路径含换行/控制字符，已修正：' + '；'.join(fixed_note))
            if tex_fix:
                log2_to('已应用 %d 处手动修正的贴图路径（右键可改/撤销）' % len(tex_fix))
            if xmls:
                nm = os.path.basename(xmls[0])
                if nm != (xml_name_var.get() or ''):
                    xml_name_var.set(nm)
                    set_state(xmlname_entry, 'follow')
            else:
                if (xml_name_var.get() or ''):
                    xml_name_var.set('')
                set_state(xmlname_entry, 'change')
                log2_to('该 NIF 没有 XML：XML 名已清空，生成时不复制 XML')
            n_miss = sum(1 for a in asset_rows if not a['src'])
            n_bsa = sum(1 for m in row_meta.values() if m.get('bsa'))
            log2_to('定位完成：%d 项，缺失 %d 项%s' % (
                len(asset_rows), n_miss, ('，在 BSA 中 %d 项' % n_bsa) if n_bsa else ''))
        except Exception as e:
            log2_to(traceback.format_exc())
            if not quiet:
                messagebox.showerror('失败', str(e))

    def make_bs_shell():
        """为当前发型生成一个 BodySlide 起步工程（.osp 骨架，滑块数据仍需 OS 生成）。"""
        s = selected_style()
        if not s:
            messagebox.showwarning('提示', '先选源发型')
            return
        rel = (s.get('mod3') or s.get('mod4') or '').replace('/', '\\')
        nif = os.path.basename(rel)
        if not nif:
            messagebox.showwarning('提示', '这个发型没有模型路径')
            return
        stem = os.path.splitext(nif)[0]
        name = (full_var.get().strip() or stem) + ' BodySlide'
        out = out2.get().strip() or APP_DIR
        try:
            p = write_osp_shell(out, name, nif)
        except Exception as e:
            messagebox.showerror('失败', str(e))
            return
        log2_to('已生成 BodySlide 起步工程：%s' % p)
        log2_to('接着在 BodySlide / Outfit Studio 里打开它，用 Conform All 刷滑块后保存 —— 滑块形变数据只能这样生成')
        try:
            subprocess.Popen(['explorer', '/select,', os.path.abspath(p)])
        except Exception:
            pass

    def _tool_exe(which='bs'):
        from pct.mods import find_bodyslide, find_outfitstudio
        root = mods_root.get().strip()
        return (find_bodyslide(root) if which == 'bs' else find_outfitstudio(root))

    def open_bodyslide(which='bs'):
        """调用 mods 里的 BodySlide / Outfit Studio（GUI，用来 Batch Build / Conform）。"""
        exe = _tool_exe(which)
        label = 'BodySlide' if which == 'bs' else 'Outfit Studio'
        if not exe:
            messagebox.showwarning(
                '没找到 ' + label,
                '在「MO2 mods 根目录」下没找到 %s 的可执行文件。\n'
                '请确认已安装 BodySlide and Outfit Studio，并在'
                '「设置 → 路径设置…」里把 mods 根目录指对。' % label)
            return
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
        except Exception as e:
            messagebox.showerror('启动失败', str(e))
            return
        log2_to('已启动 %s：%s' % (label, exe))
        log2_to('在 %s 里选中左侧的 outfit，按「Batch Build」即可生成 NIF'
                '（滑块形变由它计算）。' % label)

    def esp_path_now():
        n = (esp_name.get().strip() or 'Hair_BoxWorld')
        if not n.lower().endswith('.esp'):
            n += '.esp'
        return os.path.join(out2.get().strip() or APP_DIR, n)

    def _upd_esp_hint(*_a):
        p = esp_path_now()
        ex = os.path.exists(p)
        esp_hint.set('→ %s  %s' % (p, '（已存在同名 ESP：将追加）' if ex else '（新建）'))
        try:
            esp_hint_lbl.configure(foreground=('#b36b00' if ex else '#0a7d28'))
            esp_entry.configure(bg=(C_CHANGE if ex else C_OK))
        except tk.TclError:
            pass

    esp_name.trace_add('write', _upd_esp_hint)
    out2.trace_add('write', _upd_esp_hint)
    _upd_esp_hint()

    def pick_esp_file():
        p = filedialog.askopenfilename(title='选择要追加的 ESP', filetypes=[('ESP', '*.esp')])
        if not p:
            return
        out2.set(os.path.dirname(p))
        esp_name.set(os.path.splitext(os.path.basename(p))[0])

    FIELDS = (('src', src_entry), ('style', cb), ('mod', modcb),
              ('out', out2_entry), ('esp', esp_entry), ('card', card_entry))
    COLORED = (csub_entry, tsub_entry, nifname_entry, boxname_entry, cardname_entry,
               xmlname_entry, edid_entry, full_entry)

    for _k, _w in FIELDS:
        _w.bind('<KeyRelease>', lambda e, w=_w: set_state(w, 'ok'), add='+')
        _w.bind('<<ComboboxSelected>>', lambda e, w=_w: set_state(w, 'ok'), add='+')

    badges = {}

    def badge(w, text, bg, fg):
        """在控件右侧叠一个小色块 —— ttk 在 Windows 主题下不吃 fieldbackground，只能这么标。"""
        lb = badges.get(w)
        if lb is None or not lb.winfo_exists():
            lb = tk.Label(w.master, text=text, bg=bg, fg=fg, bd=0, padx=4,
                          font=('Microsoft YaHei UI', 8))
            lb.place(in_=w, relx=1.0, rely=0.5, anchor='e', x=-2)
            badges[w] = lb
        else:
            lb.configure(text=text, bg=bg, fg=fg)
        lb.lift()

    def unbadge(*ws):
        for w in ws:
            lb = badges.pop(w, None)
            if lb is not None and lb.winfo_exists():
                lb.destroy()

    for _w in COLORED:
        _w.bind('<KeyRelease>', lambda e, w=_w: set_state(w, 'ok'), add='+')

    def reset_marks():
        for _k, w in FIELDS:
            set_state(w, 'ok')
        for w in COLORED:
            set_state(w, 'ok')
        job_hint.configure(text='', fg='#c00000')
        card_hint.set('（绝对路径；用页签①/②生成时会自动填这里，也可以自己选现成的 dds）')

    def mark(keys, msg):
        for k, w in FIELDS:
            if k in keys:
                set_state(w, 'req')
        job_hint.configure(text=msg)

    def job2():
        reset_marks()
        miss, labels = [], []
        if not (src_esp.get().strip() and os.path.exists(src_esp.get().strip())):
            miss.append('src'); labels.append('源 ESP')
        if not selected_style():
            miss.append('style'); labels.append('源发型')
        mod = mod_name.get().strip()
        if not mod or not os.path.isdir(os.path.join(mods_root.get(), mod)):
            miss.append('mod'); labels.append('mod 列表')
        if not out2.get().strip():
            miss.append('out'); labels.append('输出文件夹')
        if not esp_name.get().strip():
            miss.append('esp'); labels.append('ESP 文件名')
        card = carddds.get().strip()
        if not card or not os.path.exists(_abs(card)):
            miss.append('card'); labels.append('卡片 dds')
        if miss:
            mark(set(miss), '还差：' + '、'.join(labels) + '（红底格子就是没填/填错的）')
            log2_to('缺少必填项：' + '、'.join(labels))
            return
        s_ = selected_style()
        esp = esp_path_now()
        btn_box.configure(state='disabled')
        log2.delete('1.0', 'end')
        log2_to('ESP: ' + esp)
        if os.path.exists(esp):
            log2_to('该 ESP 已存在 -> 追加；世界模型沿用里面已建好的盒子 NIF，只新增替换纹理（TXST）')

        def work():
            try:
                res = make_pack(src_esp=src_esp.get(), style_edid=s_['edid'],
                                moddir=os.path.join(mods_root.get(), mod),
                                nif_name=nif_name_var.get().strip(), box_name=box_name_var.get().strip(),
                                xml_name=xml_name_var.get().strip(), msub=msub.get().strip(),
                                csub=csub.get().strip(), tex_prefix=tex_prefix.get().strip(),
                                card_sub=card_sub.get().strip(), card_name=card_name_v.get().strip(),
                                tsub=tsub.get().strip(), bsub=bsub.get().strip(), outdir=out2.get().strip(),
                                tex_card=_abs(card), template_nif=_abs(tpl_var.get()),
                                box_dds=_abs(boxdds.get()), boxn_dds=_abs(boxn.get()),
                                glass_dds=_abs(glass.get()),
                                esp_path=esp, full_name=full_var.get(), log=log2_to,
                                tex_fix=dict(tex_fix),
                                bsa_dirs=[os.path.join(mods_root.get(), mod),
                                          (game_data.get() or '').strip()])
                root.after(0, lambda: after_ok(res))
            except (MissingTexture, RuntimeError) as e:
                log2_to('错误: ' + str(e))
                root.after(0, lambda: messagebox.showwarning('缺少素材', str(e)))
            except Exception as e:
                log2_to(traceback.format_exc())
                root.after(0, lambda: messagebox.showerror('失败', str(e)))
            finally:
                root.after(0, lambda: btn_box.configure(state='normal'))

        threading.Thread(target=work, daemon=True).start()

    def after_ok(res):
        # 3) 生成完就清空卡片路径并高亮提示
        carddds.set('')
        card_name_v.set('')
        card_name_auto[0] = True
        set_state(card_entry, 'change')
        card_hint.set('已生成 -> 请换一张卡片 dds 再点生成（同一套头发记得改下面的 EDID）')
        # 4) 下一次必须改的东西用橙色块标出来
        for w in (edid_entry, full_entry):
            set_state(w, 'change')
        job_hint.configure(fg='#a05a00', text=(
            '已生成 %s。下一套请改：新 EDID / 显示名（橙底），并选新的卡片 dds；'
            '世界模型%s' % (os.path.basename(res.get('esp', '')),
                            ('复用 ' + res.get('box', '')) if res.get('shared')
                            else ('新建 ' + os.path.basename(res.get('box') or '')))))
        messagebox.showinfo('完成', '%s\n\n%s' % (
            res.get('esp', ''),
            ('世界模型：复用已有盒子 + 替换纹理 %s' % res.get('txst')) if res.get('shared')
            else '世界模型：新建盒子'))

    btn_box.configure(command=job2)
    refresh_assets = lambda: locate(quiet=True)
    root.after(400, lambda: refresh_mods(quiet=True))

    CACHE_DIR['dir'] = cache_dir.get() or APP_DIR
    try:
        _n = load_bsa_cache(CACHE_DIR['dir'])
    except Exception:
        _n = 0
    root.mainloop()


def main_cli():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--out', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--size', type=int, default=1024)
    ap.add_argument('--fill', type=float, default=92.0)
    ap.add_argument('--hscale', type=float, default=100.0)
    ap.add_argument('--yaw', type=float, default=0.0)
    ap.add_argument('--pitch', type=float, default=0.0)
    ap.add_argument('--yaw2', type=float, default=65.0)
    ap.add_argument('--pitch2', type=float, default=0.0)
    for k, dv in (('amb', 0.5), ('diff', 0.55), ('rim', 0.18), ('spec', 0.24),
                  ('specpow', 24.0), ('alpha', 1.8), ('gamma', 1.8),
                  ('bright', 1.0), ('contrast', 1.0)):
        ap.add_argument('--' + k, type=float, default=dv)
    ap.add_argument('--depth', type=int, default=0)
    ap.add_argument('--autobright', type=int, default=1, help='1=按贴图平均亮度自适应（默认），0=关闭')
    a = ap.parse_args()
    out = a.out or os.path.dirname(os.path.abspath(a.input))
    name = a.name or re.sub(r'[\\/:*?"<>|]', '_', os.path.splitext(os.path.basename(a.input))[0])
    prm = dict(amb=a.amb, diff=a.diff, rim=a.rim, spec=a.spec, specpow=a.specpow,
               alpha=a.alpha, gamma=a.gamma, bright=a.bright, contrast=a.contrast,
               depth=a.depth, autobright=a.autobright)
    png, dds = run_card(a.input, out, a.size, name, print, a.fill, a.hscale,
                        a.yaw, a.pitch, a.yaw2, a.pitch2, prm)
    print('OK', dds)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main_cli()
    else:
        main_gui()
