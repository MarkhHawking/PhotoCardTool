# -*- coding: utf-8 -*-
"""APP/BASE 路径、settings.json、自动搜索 MO2/游戏目录、BSA 索引缓存。"""
import json
import os
import re
import sys
import time

import bsa

BASE = getattr(sys, '_MEIPASS',
              os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, 'frozen', False) else
    os.path.join(BASE, 'photocard_gui.py')))
MAT = os.path.join(APP_DIR, 'materials')
TEXCONV = os.path.join(MAT, 'Texconv.exe')
if not os.path.exists(TEXCONV):
    TEXCONV = os.path.join(BASE, 'Texconv.exe')
BASE_CARD = os.path.join(MAT, '02.png')
if not os.path.exists(BASE_CARD):
    BASE_CARD = os.path.join(BASE, '02.png')

SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
CACHE_DIR = {'dir': ''}
BSA_CACHE = {'index': {}, 'stamp': ''}


def load_settings():
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def auto_find_mods_root():
    """找 MO2 的 mods 目录：常见位置 + ModOrganizer.ini 的 mod_directory。"""
    import glob
    cands = []
    for drv in ('C:', 'D:', 'E:', 'F:', 'G:'):
        cands += [drv + r'\Modding\MO2', drv + r'\MO2', drv + r'\Games\MO2',
                  drv + r'\Tools\MO2', drv + r'\MO2 Portable']
    for d in cands:
        exe = os.path.join(d, 'ModOrganizer.exe')
        if not os.path.exists(exe):
            continue
        ini = os.path.join(d, 'ModOrganizer.ini')
        if os.path.exists(ini):
            try:
                for line in open(ini, encoding='utf-8', errors='replace'):
                    k, _, v = line.partition('=')
                    if k.strip().lower() == 'mod_directory':
                        p = v.strip().strip('"')
                        if p and os.path.isdir(p):
                            return p
            except Exception:
                pass
        m = os.path.join(d, 'mods')
        if os.path.isdir(m):
            return m
    # 退一步：直接找盘符下的 mods 目录（有 meta.ini 的那种）
    for drv in ('C:', 'D:', 'E:', 'F:', 'G:'):
        for pat in (drv + r'\*\mods', drv + r'\*\*\mods'):
            for m in glob.glob(pat):
                try:
                    for n in os.listdir(m)[:5]:
                        if os.path.isdir(os.path.join(m, n)):
                            return m
                except OSError:
                    pass
    return ''


def auto_find_game_data():
    """找 Skyrim SE 的 Data：注册表 → Steam 库 → 常见路径。"""
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key in (r'SOFTWARE\WOW6432Node\Bethesda Softworks\Skyrim Special Edition',
                        r'SOFTWARE\Bethesda Softworks\Skyrim Special Edition'):
                try:
                    k = winreg.OpenKey(hive, key)
                    p, _ = winreg.QueryValueEx(k, 'Installed Path')
                    d = os.path.join(p, 'Data')
                    if os.path.isdir(d):
                        return d
                except OSError:
                    pass
    except Exception:
        pass
    libs = []
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam')
        steam, _ = winreg.QueryValueEx(k, 'SteamPath')
        libs.append(steam)
        vdf = os.path.join(steam, 'steamapps', 'libraryfolders.vdf')
        if os.path.exists(vdf):
            txt = open(vdf, encoding='utf-8', errors='replace').read()
            for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                libs.append(m.group(1).replace('\\\\', '\\'))
    except Exception:
        pass
    for drv in ('C:', 'D:', 'E:', 'F:', 'G:'):
        libs += [drv + r'\SteamLibrary', drv + r'\Steam', drv + r'\Program Files (x86)\Steam']
    for lib in libs:
        d = os.path.join(lib, 'steamapps', 'common', 'Skyrim Special Edition', 'Data')
        if os.path.isdir(d):
            return d
    return ''


def bsa_cache_path(cache_dir):
    return os.path.join(cache_dir or APP_DIR, 'bsa_index.json.gz')


def load_bsa_cache(cache_dir):
    p = bsa_cache_path(cache_dir)
    try:
        import gzip
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            d = json.load(f)
        files = d.get('files') or {}
        BSA_CACHE['index'] = {k.lower(): v for k, v in files.items()}
        BSA_CACHE['stamp'] = d.get('stamp', '')
        return len(BSA_CACHE['index'])
    except Exception:
        return 0


def save_bsa_cache(cache_dir, index, stamp=''):
    p = bsa_cache_path(cache_dir)
    try:
        import gzip
        os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
        with gzip.open(p, 'wt', encoding='utf-8') as f:
            json.dump({'stamp': stamp or time.strftime('%Y-%m-%d %H:%M:%S'),
                       'count': len(index), 'files': index}, f, ensure_ascii=False)
        return p
    except Exception:
        return ''


def scan_bsa_tree(dirs, log=print, stop=None):
    """扫描若干目录下的 BSA（含各 mod 子目录第一层），返回 {名字: bsa 路径}。"""
    idx = {}
    seen = set()
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        cand = [d] + [os.path.join(d, n) for n in sorted(os.listdir(d))
                      if os.path.isdir(os.path.join(d, n))]
        for dd in cand:
            if dd in seen:
                continue
            seen.add(dd)
            for p in bsa.bsa_in_dir(dd):
                if stop and stop():
                    return idx
                names = bsa.list_files(p)
                if names:
                    log('  %s：%d 个文件' % (os.path.relpath(p, d), len(names)))
                for n in names:
                    idx.setdefault(n, p)
    return idx


