"""
Quran Reels Generator - Backend Server
Generates short video clips (Reels) with Quran recitation, text overlay, and backgrounds.
"""

import os
import sys
import json
import uuid
import time
import shutil
import threading
import subprocess
import re
import glob
import webbrowser
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote

# Set stdout encoding for Arabic
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask, request, jsonify, send_from_directory, send_file, Response, copy_current_request_context
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__, static_folder='.')
CORS(app)

# ── Preserve Arabic characters in all JSON responses ──────────────────
app.json.ensure_ascii = False

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
BUNDLED_DIR = Path(getattr(sys, '_MEIPASS', BASE_DIR))

# When running as EXE, store data next to the EXE for user visibility
if hasattr(sys, '_MEIPASS') and sys.executable.lower().endswith('.exe'):
    DATA_DIR = Path(sys.executable).parent.resolve()
    FONTS_DIR = BUNDLED_DIR / 'fonts'
else:
    DATA_DIR = BASE_DIR
    FONTS_DIR = DATA_DIR / 'fonts'

AUDIO_DIR = DATA_DIR / 'audio'
VIDEO_DIR = DATA_DIR / 'video'
VISION_DIR = DATA_DIR / 'vision'
OUTPUTS_DIR = DATA_DIR / 'outputs'
# Note: FONTS_DIR is set above (from BASE_DIR or BUNDLED_DIR)
TOOLS_DIR = DATA_DIR / 'tools'
FFMPEG_DIR = TOOLS_DIR / 'ffmpeg'

for d in [AUDIO_DIR, VIDEO_DIR, VISION_DIR, OUTPUTS_DIR, FONTS_DIR, TOOLS_DIR, FFMPEG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Ensure bundled fonts exist in BASE_DIR (copy from _MEIPASS if needed)
if BUNDLED_DIR != BASE_DIR:
    bundled_fonts = BUNDLED_DIR / 'fonts'
    if bundled_fonts.exists():
        for f in bundled_fonts.iterdir():
            dest = FONTS_DIR / f.name
            if not dest.exists():
                try:
                    import shutil
                    shutil.copy2(str(f), str(dest))
                except Exception:
                    pass
    # Copy UI.html if needed
    bundled_ui = BUNDLED_DIR / 'UI.html'
    if bundled_ui.exists():
        dest_ui = BASE_DIR / 'UI.html'
        if not dest_ui.exists():
            try:
                import shutil
                shutil.copy2(str(bundled_ui), str(dest_ui))
            except Exception:
                pass
    # Copy sw.js and manifest.json
    for fn in ['sw.js', 'manifest.json']:
        bf = BUNDLED_DIR / fn
        if bf.exists():
            df = BASE_DIR / fn
            if not df.exists():
                try:
                    import shutil
                    shutil.copy2(str(bf), str(df))
                except Exception:
                    pass

# ── FFmpeg path ────────────────────────────────────────────────────────
FFMPEG_EXE = shutil.which('ffmpeg')
if not FFMPEG_EXE:
    # Check local ffmpeg
    local_ffmpeg = FFMPEG_DIR / 'ffmpeg.exe'
    if local_ffmpeg.exists():
        FFMPEG_EXE = str(local_ffmpeg)

# ── In-memory job store ────────────────────────────────────────────────
jobs = {}

# ── Cached data files ──────────────────────────────────────────────────
RECITERS_CACHE_FILE = BASE_DIR / 'reciters_cache.json'
SURAH_CACHE_FILE = BASE_DIR / 'surah_cache.json'


def fetch_reciters():
    """Fetch all available reciters from everyayah.com."""
    if RECITERS_CACHE_FILE.exists():
        try:
            with open(str(RECITERS_CACHE_FILE), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    try:
        data = fetch_json('https://everyayah.com/data/recitations.js', timeout=15)
        reciters = []
        seen = {}
        for k, v in data.items():
            if k.isdigit() and isinstance(v, dict):
                name = v.get('name', '').strip()
                subfolder = v.get('subfolder', '').strip()
                bitrate = v.get('bitrate', '64kbps')
                if name and subfolder:
                    if name in seen:
                        existing = seen[name]
                        existing_bit = int(existing.get('bitrate', '0').replace('kbps', ''))
                        new_bit = int(bitrate.replace('kbps', ''))
                        if new_bit > existing_bit:
                            seen[name]['bitrate'] = bitrate
                            seen[name]['subfolder'] = subfolder
                    else:
                        rec = {'id': k, 'name': name, 'subfolder': subfolder, 'bitrate': bitrate}
                        reciters.append(rec)
                        seen[name] = rec
        if reciters:
            try:
                with open(str(RECITERS_CACHE_FILE), 'w', encoding='utf-8') as f:
                    json.dump(reciters, f, ensure_ascii=False)
            except Exception:
                pass
            return reciters
    except Exception as e:
        print(f'fetch_reciters error: {e}')

    # Fallback
    return [
        {"id": "1", "name": "Abdul Basit Murattal", "subfolder": "Abdul_Basit_Murattal_64kbps", "bitrate": "64kbps"},
        {"id": "7", "name": "Abdurrahmaan As-Sudais", "subfolder": "Abdurrahmaan_As-Sudais_64kbps", "bitrate": "64kbps"},
        {"id": "14", "name": "Alafasy", "subfolder": "Alafasy_64kbps", "bitrate": "64kbps"},
        {"id": "19", "name": "Husary", "subfolder": "Husary_64kbps", "bitrate": "64kbps"},
        {"id": "23", "name": "Hudhaify", "subfolder": "Hudhaify_64kbps", "bitrate": "64kbps"},
        {"id": "28", "name": "Maher Al Muaiqly", "subfolder": "Maher_AlMuaiqly_64kbps", "bitrate": "64kbps"},
        {"id": "31", "name": "Menshawi", "subfolder": "Menshawi_64kbps", "bitrate": "64kbps"},
        {"id": "33", "name": "Muhammad Jibreel", "subfolder": "Muhammad_Jibreel_64kbps", "bitrate": "64kbps"},
    ]

# ── Helpers ────────────────────────────────────────────────────────────

def fetch_json(url, timeout=15):
    """Fetch JSON from URL."""
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get_available_fonts():
    """Return list of font files in fonts directory."""
    fonts = []
    for f in sorted(FONTS_DIR.glob('*.ttf')) + sorted(FONTS_DIR.glob('*.otf')):
        fonts.append({
            'filename': f.name,
            'name': f.stem,
            'path': str(f)
        })
    # Also check bundled fonts (PyInstaller)
    if BUNDLED_DIR != BASE_DIR:
        bundled_fonts = BUNDLED_DIR / 'fonts'
        if bundled_fonts.exists():
            for f in sorted(bundled_fonts.glob('*.ttf')) + sorted(bundled_fonts.glob('*.otf')):
                if not any(x['filename'] == f.name for x in fonts):
                    fonts.append({
                        'filename': f.name,
                        'name': f.stem,
                        'path': str(f)
                    })
    return fonts


def get_backgrounds():
    """Return list of background files (images + videos)."""
    items = []
    for ext in ('*.mp4', '*.webm', '*.jpg', '*.jpeg', '*.png', '*.gif'):
        for f in sorted(VIDEO_DIR.glob(ext)):
            items.append(f.name)
    return items


def get_outputs():
    """Return list of generated video files with sizes."""
    files = []
    for f in sorted(OUTPUTS_DIR.glob('*.mp4'), key=os.path.getmtime, reverse=True):
        size_mb = round(os.path.getsize(f) / (1024 * 1024), 2)
        files.append({
            'filename': f.name,
            'size_mb': size_mb,
            'path': str(f)
        })
    return files


def download_audio(reciter_subfolder, surah_num, ayah_num, dest_path):
    """Download ayah audio from everyayah.com."""
    url = f"https://everyayah.com/data/{reciter_subfolder}/{surah_num:03d}{ayah_num:03d}.mp3"
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) < 1000:
                return False
            with open(dest_path, 'wb') as f:
                f.write(data)
            return True
    except Exception:
        return False


def get_ayah_text(surah_num, ayah_num):
    """Get Arabic text of an ayah from alquran.cloud (Uthmani script with full diacritics)."""
    try:
        data = fetch_json(f"http://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}/quran-uthmani")
        if data.get('code') == 200 and data.get('data'):
            text = data['data'].get('text', '')
            return text.lstrip('\ufeff')  # strip BOM
        data = fetch_json(f"http://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}")
        if data.get('code') == 200 and data.get('data'):
            text = data['data'].get('text', '')
            return text.lstrip('\ufeff')
    except Exception:
        pass
    return ''


def get_ayah_translation(surah_num, ayah_num, edition):
    """Get translation text of an ayah."""
    if not edition:
        return ''
    try:
        data = fetch_json(f"http://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}/{edition}")
        if data.get('code') == 200 and data.get('data'):
            return data['data'].get('text', '')
    except Exception:
        pass
    return ''


# ── NudeNet moderation ──────────────────────────────────────────────────

HAS_NUDENET = False
_nude_detector = None

def _init_nudenet():
    global HAS_NUDENET, _nude_detector
    if _nude_detector is not None:
        return True
    try:
        from nudenet import NudeDetector
        _nude_detector = NudeDetector()
        HAS_NUDENET = True
        return True
    except Exception:
        return False

try:
    from nudenet import NudeDetector
    HAS_NUDENET = True
    _nude_detector = None
except ImportError:
    pass

BLOCKED_LABELS = {
    "FEMALE_GENITALIA_COVERED", "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED", "FEMALE_BREAST_COVERED",
    "BUTTOCKS_EXPOSED", "BUTTOCKS_COVERED",
    "ANUS_EXPOSED", "ANUS_COVERED",
}

def moderate_image(image_path):
    global _nude_detector
    if not _init_nudenet():
        return True, "Moderation unavailable"
    try:
        detections = _nude_detector.detect(image_path)
        for det in detections:
            label = det.get("class", "")
            score = det.get("score", 0)
            if label in BLOCKED_LABELS and score > 0.4:
                return False, f"Blocked: {label}"
        return True, "OK"
    except Exception as e:
        return False, f"Error: {e}"

def moderate_video(video_path):
    if not _init_nudenet():
        return True, "Moderation unavailable"
    try:
        import tempfile
        tmp = tempfile.mkdtemp()
        pat = os.path.join(tmp, "f_%04d.png")
        cmd = [FFMPEG_EXE, "-y", "-i", video_path, "-vf", "fps=1/2", "-frames:v", "5", pat]
        subprocess.run(cmd, capture_output=True, timeout=60)
        frames = sorted([f for f in os.listdir(tmp) if f.endswith('.png')])
        ok = True
        msg = "OK"
        for fname in frames:
            fpath = os.path.join(tmp, fname)
            ok, msg = moderate_image(fpath)
            os.remove(fpath)
            if not ok:
                break
        shutil.rmtree(tmp, ignore_errors=True)
        return ok, msg
    except Exception as e:
        return False, f"Error: {e}"


# ── Arabic text rendering ──────────────────────────────────────────────

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_ARABIC_RESHAPER = True
    # Test it immediately
    try:
        _test = arabic_reshaper.reshape('بسم')
        _test2 = get_display(_test)
        print(f'  Arabic Reshaper: ✅ (test: {_test2[:3]}...)')
    except Exception as e:
        HAS_ARABIC_RESHAPER = False
        print(f'  Arabic Reshaper: ❌ test failed: {e}')
except ImportError:
    HAS_ARABIC_RESHAPER = False
    print('  Arabic Reshaper: ❌ not installed')

try:
    import freetype
    import uharfbuzz as hb
    import numpy as np
    HAS_HARFBUZZ = True
except ImportError:
    HAS_HARFBUZZ = False

_HB_MARK_GAP = 5
_hb_ft_cache = {}

def _get_hb_ft(font_path, font_size):
    key = (font_path, font_size)
    if key not in _hb_ft_cache:
        blob = hb.Blob.from_file_path(font_path)
        face = hb.Face(blob)
        font_hb = hb.Font(face)
        font_hb.scale = (font_size * 64, font_size * 64)
        ft = freetype.Face(font_path)
        ft.set_char_size(font_size * 64)
        _hb_ft_cache[key] = (font_hb, ft)
    return _hb_ft_cache[key]


def render_arabic_text_hb(text, font_path, font_size):
    """Render Arabic text with full tashkeel using HarfBuzz + FreeType.
    Returns (PIL 'L' mode Image, width, height) or (None,0,0)."""
    if not HAS_HARFBUZZ or not text:
        return None, 0, 0

    font_hb, ft = _get_hb_ft(font_path, font_size)

    buf = hb.Buffer()
    buf.add_str(text)
    buf.direction = 'rtl'
    buf.script = 'arab'
    buf.language = 'ar'
    hb.shape(font_hb, buf)

    glyphs = []
    x_cursor = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gid = info.codepoint
        ft.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bmp = ft.glyph.bitmap
        bw, bh = bmp.width, bmp.rows
        bl, bt = ft.glyph.bitmap_left, ft.glyph.bitmap_top
        buf_bytes = bytes(bmp.buffer) if bw > 0 and bh > 0 else None
        is_mark = pos.x_advance == 0

        glyphs.append({
            'gid': gid, 'cluster': info.cluster, 'is_mark': is_mark,
            'x_cursor': x_cursor, 'x_offset': pos.x_offset / 64,
            'x_advance': pos.x_advance / 64,
            'bmp_left': bl, 'bmp_top': bt, 'bmp_w': bw, 'bmp_h': bh,
            'buf_bytes': buf_bytes, 'y_abs': None,
        })
        x_cursor += pos.x_advance / 64

    # Group by cluster and position marks relative to base
    clusters = {}
    for i, g in enumerate(glyphs):
        cid = g['cluster']
        if cid not in clusters:
            clusters[cid] = {'base': None, 'marks': []}
        if g['is_mark']:
            clusters[cid]['marks'].append(i)
        elif g['x_advance'] > 0 and clusters[cid]['base'] is None:
            clusters[cid]['base'] = i

    shadda_gid = ft.get_char_index(0x0651) if hasattr(ft, 'get_char_index') else -1

    for cdata in clusters.values():
        base_idx = cdata['base']
        mark_indices = cdata['marks']
        if base_idx is not None and mark_indices:
            base_g = glyphs[base_idx]
            base_y_top = -base_g['bmp_top']
            base_y_bottom = -base_g['bmp_top'] + base_g['bmp_h']
            above = [mi for mi in mark_indices if glyphs[mi]['bmp_top'] >= 0]
            below = [mi for mi in mark_indices if glyphs[mi]['bmp_top'] < 0]
            above.sort(key=lambda mi: 0 if glyphs[mi]['gid'] == shadda_gid else 1)
            cur_top = base_y_top
            for mi in above:
                mg = glyphs[mi]
                mg['y_abs'] = cur_top - _HB_MARK_GAP - mg['bmp_h']
                cur_top = mg['y_abs']
            cur_bot = base_y_bottom
            for mi in below:
                mg = glyphs[mi]
                mg['y_abs'] = cur_bot + _HB_MARK_GAP
                cur_bot = mg['y_abs'] + mg['bmp_h']

    for g in glyphs:
        if g['y_abs'] is None:
            g['y_abs'] = -g['bmp_top']

    data = []
    for g in glyphs:
        x_abs = g['x_cursor'] + g['x_offset'] + g['bmp_left']
        data.append((x_abs, g['y_abs'], g['bmp_w'], g['bmp_h'], g['buf_bytes']))

    valid = [d for d in data if d[4] is not None]
    if not valid:
        return None, 0, 0

    x_min = min(d[0] for d in valid)
    y_min = min(d[1] for d in valid)
    x_max = max(d[0] + d[2] for d in valid)
    y_max = max(d[1] + d[3] for d in valid)

    tw = int(x_max - x_min) + 2
    th = int(y_max - y_min) + 2

    target = np.zeros((th, tw), dtype=np.uint16)
    for x_abs, y_abs, bw, bh, buf_bytes in data:
        if buf_bytes is None:
            continue
        glyph_arr = np.frombuffer(buf_bytes, dtype=np.uint8).reshape((bh, bw))
        tx = int(x_abs - x_min)
        ty = int(y_abs - y_min)
        sx0, sy0 = max(0, -tx), max(0, -ty)
        sx1, sy1 = min(bw, tw - tx), min(bh, th - ty)
        if sx0 >= sx1 or sy0 >= sy1:
            continue
        dx0, dy0 = tx + sx0, ty + sy0
        dx1, dy1 = tx + sx1, ty + sy1
        target[dy0:dy1, dx0:dx1] = np.minimum(
            target[dy0:dy1, dx0:dx1] + glyph_arr[sy0:sy1, sx0:sx1], 255
        )

    text_alpha = Image.frombytes('L', (tw, th), target.astype(np.uint8).tobytes())
    return text_alpha, tw, th


def wrap_text_hb(text, font_path, font_size, max_width):
    """Wrap Arabic text for HarfBuzz rendering."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = current + " " + word if current else word
        _, tw, _ = render_arabic_text_hb(test, font_path, font_size)
        if tw <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def normalize_diacritics(text):
    """
    Normalize Arabic diacritics order: ensure shadda (U+0651) comes BEFORE the vowel mark.
    Some sources may output shadda after the vowel, which causes rendering issues.
    This reorders combining marks to the standard order:
    Base + Shadda + Vowel (Fatha/Kasra/Damma) + Other marks
    """
    if not text:
        return text
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        result.append(ch)
        i += 1
        # Collect all combining marks after this base character
        marks = []
        while i < len(text) and (
            0x064B <= ord(text[i]) <= 0x065F or
            0x0670 == ord(text[i]) or
            0x0610 <= ord(text[i]) <= 0x061A or
            0x06D6 <= ord(text[i]) <= 0x06ED
        ):
            marks.append(text[i])
            i += 1
        if marks:
            # Sort marks: shadda (0651) first, then vowels, then other marks
            def mark_sort_key(m):
                cp = ord(m)
                # Shadda = 0
                if cp == 0x0651:
                    return 0
                # Fatha (064E), Kasra (0650), Damma (064F) = 1
                if cp in (0x064E, 0x0650, 0x064F):
                    return 1
                # Tanween marks (064B, 064C, 064D) = 2
                if cp in (0x064B, 0x064C, 0x064D):
                    return 2
                # Sukun (0652) = 3
                if cp == 0x0652:
                    return 3
                # Extended marks (0653-065F, 0670) = 4
                if 0x0653 <= cp <= 0x065F or cp == 0x0670:
                    return 4
                # The rest (0610-061A, 06D6-06ED) = 5
                return 5
            marks.sort(key=mark_sort_key)
            result.extend(marks)
    return ''.join(result)


def reshape_arabic(text):
    """Reshape Arabic text for proper letter connections, preserving tashkeel."""
    if not text:
        return text
    text = text.lstrip('\ufeff')
    text = normalize_diacritics(text)
    if HAS_ARABIC_RESHAPER:
        try:
            from arabic_reshaper import ArabicReshaper
            _reshaper = ArabicReshaper(configuration={'delete_harakat': False})
            reshaped = _reshaper.reshape(text)
            return get_display(reshaped)
        except Exception as e:
            print(f'reshape_arabic error: {e}')
    return text


def render_ft_text(text, font_path, font_size):
    """Render Arabic text with proper tashkeel using FreeType glyph positioning.
    Returns (PIL 'L' Image, width, height) or (None,0,0) if FreeType unavailable."""
    if not HAS_FREETYPE or not text:
        return None, 0, 0

    ft = freetype.Face(font_path)
    ft.set_char_size(font_size * 64)

    glyphs = []
    x_cursor = 0
    for ch in text:
        cp = ord(ch)
        gid = ft.get_char_index(cp)
        if gid == 0:
            x_cursor += font_size * 0.3  # space for missing glyph
            continue
        ft.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        bmp = ft.glyph.bitmap
        is_mark = 0x064B <= cp <= 0x065F or cp == 0x0670 or 0x0610 <= cp <= 0x061A or 0x06D6 <= cp <= 0x06ED

        glyphs.append({
            'cp': cp, 'gid': gid, 'is_mark': is_mark,
            'x_advance': ft.glyph.advance.x / 64.0,
            'bmp_left': ft.glyph.bitmap_left, 'bmp_top': ft.glyph.bitmap_top,
            'bmp_w': bmp.width, 'bmp_h': bmp.rows,
            'buf': bytes(bmp.buffer) if bmp.width > 0 and bmp.rows > 0 else None,
        })
        x_cursor += ft.glyph.advance.x / 64.0

    # Group into clusters: base char + following marks
    clusters = []
    current = None
    for g in glyphs:
        if not g['is_mark']:
            if current:
                clusters.append(current)
            current = {'base': g, 'marks': []}
        elif current:
            current['marks'].append(g)
    if current:
        clusters.append(current)

    # Position marks relative to base char in each cluster
    for cl in clusters:
        base = cl['base']
        marks = cl['marks']
        if marks:
            base_top = -base['bmp_top']
            base_bottom = -base['bmp_top'] + base['bmp_h']
            # Sort marks: shadda first, then vowels, then others
            def mark_order(m):
                cp = m['cp']
                if cp == 0x0651: return 0
                if cp in (0x064E, 0x0650, 0x064F, 0x064B, 0x064C, 0x064D): return 1
                return 2
            marks.sort(key=mark_order)
            # Stack above marks and below marks
            above = [m for m in marks if m['bmp_top'] > 0 or m['cp'] not in (0x0650, 0x064D)]
            below = [m for m in marks if m not in above]
            cur_y_top = base_top
            for m in above:
                m['y_abs'] = cur_y_top - 3 - m['bmp_h']
                cur_y_top = m['y_abs']
            cur_y_bottom = base_bottom
            for m in below:
                m['y_abs'] = cur_y_bottom + 3
                cur_y_bottom = m['y_abs'] + m['bmp_h']
        base['y_abs'] = -base['bmp_top']

    # Build positioned glyph list
    pos_glyphs = []
    x_pos = 0
    for cl in clusters:
        base = cl['base']
        base['x_abs'] = x_pos + base['bmp_left']
        pos_glyphs.append(base)
        for m in cl['marks']:
            m['x_abs'] = x_pos + m['bmp_left']
            pos_glyphs.append(m)
        x_pos += base['x_advance']

    valid = [g for g in pos_glyphs if g['buf']]
    if not valid:
        return None, 0, 0

    x_min = min(g['x_abs'] for g in valid)
    y_min = min(g['y_abs'] for g in valid)
    x_max = max(g['x_abs'] + g['bmp_w'] for g in valid)
    y_max = max(g['y_abs'] + g['bmp_h'] for g in valid)

    tw = int(x_max - x_min) + 2
    th = int(y_max - y_min) + 2

    target = [0] * (tw * th)
    for g in pos_glyphs:
        if not g['buf']:
            continue
        arr = list(g['buf'])
        gw, gh = g['bmp_w'], g['bmp_h']
        tx = int(g['x_abs'] - x_min)
        ty = int(g['y_abs'] - y_min)
        for row in range(gh):
            for col in range(gw):
                sx, sy = tx + col, ty + row
                if 0 <= sx < tw and 0 <= sy < th:
                    alpha = arr[row * gw + col]
                    idx = sy * tw + sx
                    if alpha:
                        target[idx] = min(target[idx] + alpha, 255)

    from PIL import Image
    img = Image.frombytes('L', (tw, th), bytes(target))
    return img, tw, th


def wrap_text_ft(text, font_path, font_size, max_width):
    """Wrap text for FreeType rendering by measuring widths."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        _, tw, _ = render_ft_text(test, font_path, font_size)
        if tw <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def get_available_font_path():
    """Get a good Arabic font path."""
    fonts = get_available_fonts()
    # Prefer specific fonts
    preferred = ['Amiri-Regular.ttf', 'NotoNaskhArabic-Regular.ttf',
                 'Al Mushaf Quran.ttf', 'Al Majeed Quranic Font_shiped.ttf']
    for p in preferred:
        fp = FONTS_DIR / p
        if fp.exists():
            return str(fp)
    if fonts:
        return fonts[0]['path']
    return None


def wrap_text(text, font, max_width, draw):
    """
    Wrap text to fit within max_width, preserving Arabic diacritics.
    Diacritics (combining marks) are kept attached to their base character.
    """
    lines = []
    # Group: base_char + any combining diacritical marks
    # Arabic combining marks (diacritics) ranges:
    #   Fathatan..Sukun:   \u064B-\u0652
    #   Maddah..Madd:      \u0653-\u065F
    #   Superscript Alef:  \u0670
    #   Honorifics:        \u0610-\u061A
    #   Extended:          \u06D6-\u06ED
    pattern = re.compile(
        r'.[\u064B-\u065F\u0670\u0610-\u061A\u06D6-\u06ED]*',
        re.UNICODE
    )
    units = pattern.findall(text)
    if not units:
        units = list(text)
    current_line = ''
    for unit in units:
        test_line = current_line + unit
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = unit
    if current_line:
        lines.append(current_line)
    return lines


def create_text_overlay(ayah_text, translation_text, font_path, text_color,
                        translation_color, bg_color, font_size=None, trans_font_size=None,
                        width=1080, height=1920, surah_name=None, ayah_num=None):
    """Create text overlay image using Pillow (fast, reliable, never hangs)."""
    if not font_path or not os.path.exists(font_path):
        font_path = get_available_font_path()

    if font_size is None:
        text_len = len(ayah_text)
        if text_len > 150: font_size = 56
        elif text_len > 100: font_size = 64
        elif text_len > 60: font_size = 76
        else: font_size = 92

    if trans_font_size is None:
        trans_font_size = max(28, int(font_size * 0.45))

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Parse colors
    try:
        tc = tuple(int(text_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        tc = (255, 255, 255)
    try:
        trc = tuple(int(translation_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        trc = (240, 214, 138)

    # Load fonts (with fail-safe)
    quran_font = ImageFont.load_default()
    trans_font = ImageFont.load_default()
    try:
        if font_path and os.path.exists(font_path):
            quran_font = ImageFont.truetype(font_path, font_size)
    except Exception:
        pass
    try:
        if font_path and os.path.exists(font_path):
            trans_font = ImageFont.truetype(font_path, trans_font_size)
    except Exception:
        pass

    margin_x = 60
    max_text_width = width - 2 * margin_x

    # ── HarfBuzz path for proper tashkeel (fallback: FreeType, then Pillow) ──
    text = ayah_text.lstrip('\ufeff')

    use_hb = HAS_HARFBUZZ and font_path and os.path.exists(font_path)

    if use_hb:
        # HarfBuzz handles everything: shaping, bidi, and tashkeel positioning
        # Use ORIGINAL text (not reshaped by arabic_reshaper/bidi)
        ayah_lines = wrap_text_hb(text, font_path, font_size, max_text_width)
        # Measure base height for line spacing
        try:
            ft = freetype.Face(font_path)
            ft.set_char_size(font_size * 64)
            ft.load_glyph(ft.get_char_index(0x0627), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            base_h = abs(ft.glyph.bitmap_top) + ft.glyph.bitmap.rows
        except Exception:
            base_h = font_size
        line_height = int(base_h * 2.5)

        # Translation via Pillow
        trans_lines = []
        trans_line_height = 0
        if translation_text:
            try:
                trans_font = ImageFont.truetype(font_path, trans_font_size) if font_path and os.path.exists(font_path) else ImageFont.load_default()
            except Exception:
                trans_font = ImageFont.load_default()
            simple_trans = translation_text.lstrip('\ufeff')
            reshaped_trans = reshape_arabic(simple_trans)
            trans_lines = wrap_text(reshaped_trans, trans_font, max_text_width, draw)
            try:
                bbox_t = trans_font.getbbox('آ')
                trans_line_height = int((bbox_t[3] - bbox_t[1]) * 2.0)
            except Exception:
                trans_line_height = int(trans_font_size * 2.0)

        gap_between = 80
        total_h = len(ayah_lines) * line_height
        total_h += gap_between if trans_lines else 0
        total_h += len(trans_lines) * trans_line_height
        start_y = (height - total_h) // 2

        for i, line in enumerate(ayah_lines):
            text_alpha, tw, th = render_arabic_text_hb(line, font_path, font_size)
            if text_alpha is None:
                continue
            x_pos = (width - tw) // 2
            y_pos = start_y + i * line_height
            shadow = Image.new('RGBA', (tw, th), (0, 0, 0, 200))
            shadow.putalpha(text_alpha)
            img.paste(shadow, (x_pos + 2, y_pos + 2), shadow)
            color_layer = Image.new('RGBA', (tw, th), tc + (255,))
            color_layer.putalpha(text_alpha)
            img.paste(color_layer, (x_pos, y_pos), color_layer)

        if trans_lines:
            trans_start_y = start_y + len(ayah_lines) * line_height + gap_between
            for j, line in enumerate(trans_lines):
                bbox = draw.textbbox((0, 0), line, font=trans_font)
                t_w = bbox[2] - bbox[0]
                tx = (width - t_w) // 2
                ty = trans_start_y + j * trans_line_height
                draw.text((tx+1, ty+1), line, font=trans_font, fill=(0, 0, 0, 100))
                draw.text((tx, ty), line, font=trans_font, fill=trc + (255,))

    elif HAS_FREETYPE:
        # FreeType fallback (manual mark positioning)
        ayah_lines = wrap_text_ft(reshaped, font_path, font_size, max_text_width)
        try:
            ft = freetype.Face(font_path)
            ft.set_char_size(font_size * 64)
            ft.load_glyph(ft.get_char_index(0x0627), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            base_h = abs(ft.glyph.bitmap_top) + ft.glyph.bitmap.rows
        except Exception:
            base_h = font_size
        line_height = int(base_h * 2.5)

        trans_lines = []
        trans_line_height = 0
        if translation_text:
            try:
                trans_font = ImageFont.truetype(font_path, trans_font_size) if font_path and os.path.exists(font_path) else ImageFont.load_default()
            except Exception:
                trans_font = ImageFont.load_default()
            simple_trans = translation_text.lstrip('\ufeff')
            reshaped_trans = reshape_arabic(simple_trans)
            trans_lines = wrap_text(reshaped_trans, trans_font, max_text_width, draw)
            try:
                bbox_t = trans_font.getbbox('آ')
                trans_line_height = int((bbox_t[3] - bbox_t[1]) * 2.0)
            except Exception:
                trans_line_height = int(trans_font_size * 2.0)

        gap_between = 80
        total_h = len(ayah_lines) * line_height
        total_h += gap_between if trans_lines else 0
        total_h += len(trans_lines) * trans_line_height
        start_y = (height - total_h) // 2

        for i, line in enumerate(ayah_lines):
            text_alpha, tw, th = render_ft_text(line, font_path, font_size)
            if text_alpha is None:
                continue
            x_pos = (width - tw) // 2
            y_pos = start_y + i * line_height
            shadow = Image.new('RGBA', (tw, th), (0, 0, 0, 200))
            shadow.putalpha(text_alpha)
            img.paste(shadow, (x_pos + 2, y_pos + 2), shadow)
            color_layer = Image.new('RGBA', (tw, th), tc + (255,))
            color_layer.putalpha(text_alpha)
            img.paste(color_layer, (x_pos, y_pos), color_layer)

        if trans_lines:
            trans_start_y = start_y + len(ayah_lines) * line_height + gap_between
            for j, line in enumerate(trans_lines):
                bbox = draw.textbbox((0, 0), line, font=trans_font)
                t_w = bbox[2] - bbox[0]
                tx = (width - t_w) // 2
                ty = trans_start_y + j * trans_line_height
                draw.text((tx+1, ty+1), line, font=trans_font, fill=(0, 0, 0, 100))
                draw.text((tx, ty), line, font=trans_font, fill=trc + (255,))

    else:
        # Plain Pillow fallback
        ayah_lines = wrap_text(reshaped, quran_font, max_text_width, draw)
        try:
            bbox = quran_font.getbbox('آ')
            base_h = bbox[3] - bbox[1]
        except Exception:
            base_h = font_size
        line_height = int(base_h * 2.8)

        trans_lines = []
        trans_line_height = 0
        if translation_text:
            simple_trans = translation_text.lstrip('\ufeff')
            reshaped_trans = reshape_arabic(simple_trans)
            trans_lines = wrap_text(reshaped_trans, trans_font, max_text_width, draw)
            try:
                bbox_t = trans_font.getbbox('آ')
                trans_line_height = int((bbox_t[3] - bbox_t[1]) * 2.2)
            except Exception:
                trans_line_height = int(trans_font_size * 2.2)

        gap_between = 80
        total_h = len(ayah_lines) * line_height
        total_h += gap_between if trans_lines else 0
        total_h += len(trans_lines) * trans_line_height
        start_y = (height - total_h) // 2

        y = start_y
        for line in ayah_lines:
            bbox = draw.textbbox((0, 0), line, font=quran_font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            draw.text((x+2, y+2), line, font=quran_font, fill=(0, 0, 0, 200))
            draw.text((x, y), line, font=quran_font, fill=tc + (255,))
            y += line_height

        if trans_lines:
            y += gap_between
            for line in trans_lines:
                bbox = draw.textbbox((0, 0), line, font=trans_font)
                line_w = bbox[2] - bbox[0]
                x = (width - line_w) // 2
                draw.text((x+1, y+1), line, font=trans_font, fill=(0, 0, 0, 100))
                draw.text((x, y), line, font=trans_font, fill=trc + (255,))
                y += trans_line_height

    # Watermark
    try:
        wm_font = ImageFont.truetype(font_path, 22) if font_path and os.path.exists(font_path) else ImageFont.load_default()
    except Exception:
        wm_font = ImageFont.load_default()
    wm_text = 'تلاوة القرآن الكريم'
    wm_bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    wm_w = wm_bbox[2] - wm_bbox[0]
    wm_x = (width - wm_w) // 2
    draw.text((wm_x, height - 70), wm_text, font=wm_font, fill=(180, 180, 180, 180))

    return img


# ── Video Generation ───────────────────────────────────────────────────

def generate_video_job(job_id, params):
    """Background worker that generates the video."""
    try:
        # DEBUG: write immediately to verify thread starts
        try:
            desktop = Path(os.environ.get('USERPROFILE', '')) / 'Desktop'
            with open(str(desktop / 'quran_debug.txt'), 'a', encoding='utf-8') as _df:
                _df.write(f'[{time.strftime("%H:%M:%S")}] generate_video_job STARTED job_id={job_id}\n')
        except Exception:
            pass

        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['progress'] = 5
        jobs[job_id]['message'] = 'جاري بدء التوليد...'

        reciter_subfolder = params['reciter_subfolder']
        surah_num = params['surah_num']
        ayah_from = params['ayah_from']
        ayah_to = params['ayah_to']
        translation_edition = params.get('translation_edition')
        quran_font = params.get('quran_font')
        text_color = params.get('text_color', '#ffffff')
        translation_color = params.get('translation_color', '#f0d68a')
        bg_color = params.get('bg_color', '#0a0f1a')
        background_file = params.get('background_file')
        surah_name = params.get('surah_name', '')

        # Determine font path (fall back if none selected)
        font_path = None
        if quran_font:
            fp = FONTS_DIR / quran_font
            if fp.exists():
                font_path = str(fp)
        if not font_path:
            font_path = get_available_font_path()

        # Collect ayah data
        ayah_data = []
        total = ayah_to - ayah_from + 1

        _update_job(job_id, 2, 'جاري تحميل بيانات الآيات...')

        for i, ayah_num in enumerate(range(ayah_from, ayah_to + 1)):
            pct_base = 5 + int(25 * (i / total))
            _update_job(job_id, pct_base, f'({i+1}/{total}) جاري تحميل نص الآية {ayah_num}...')

            text = get_ayah_text(surah_num, ayah_num)
            if not text:
                text = f'آية {ayah_num}'

            translation = ''
            if translation_edition:
                _update_job(job_id, pct_base + 2, f'({i+1}/{total}) جاري تحميل ترجمة الآية {ayah_num}...')
                translation = get_ayah_translation(surah_num, ayah_num, translation_edition)

            audio_path = AUDIO_DIR / f'ayah_{surah_num}_{ayah_num}.mp3'
            if not audio_path.exists():
                _update_job(job_id, pct_base + 5, f'({i+1}/{total}) جاري تحميل صوت الآية {ayah_num}...')
                download_audio(reciter_subfolder, surah_num, ayah_num, audio_path)

            ayah_data.append({
                'num': ayah_num,
                'text': text,
                'translation': translation,
                'audio': str(audio_path) if audio_path.exists() else None
            })

        job_dir = VISION_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        _update_job(job_id, 35, 'جاري إنشاء صور النص...')

        overlay_files = []
        for idx, ayah in enumerate(ayah_data):
            pct = 35 + int(25 * ((idx + 1) / len(ayah_data)))
            _update_job(job_id, pct, f'({idx+1}/{len(ayah_data)}) جاري إنشاء صورة الآية {ayah["num"]}...')

            try:
                _log_debug(job_id, f'START overlay ayah {ayah["num"]} font={font_path}')
                img = create_text_overlay(
                    ayah_text=ayah['text'],
                    translation_text=ayah['translation'],
                    font_path=font_path,
                    text_color=text_color,
                    translation_color=translation_color,
                    bg_color=bg_color,
                    surah_name=surah_name,
                    ayah_num=ayah['num']
                )
                _log_debug(job_id, f'OVERLAY DONE ayah {ayah["num"]}')
                overlay_path = job_dir / f'overlay_{idx+1}.png'
                img.save(str(overlay_path), 'PNG')
                _log_debug(job_id, f'SAVED overlay ayah {ayah["num"]}')
                overlay_files.append(str(overlay_path))
            except Exception as e:
                _log_debug(job_id, f'ERROR overlay ayah {ayah["num"]}: {e}')
                _update_job(job_id, 0, f'خطأ في إنشاء الصورة: {str(e)}', error=True)
                return

        if not FFMPEG_EXE:
            _update_job(job_id, 0, 'FFmpeg غير موجود. يرجى تثبيت FFmpeg', error=True)
            return

        _update_job(job_id, 62, 'جاري تجهيز مقاطع الفيديو...')

        output_filename = f'quran_{surah_num}_{ayah_from}_{ayah_to}_{job_id[:8]}.mp4'
        output_path = OUTPUTS_DIR / output_filename

        success = render_video(
            overlay_files=overlay_files,
            background_file=background_file,
            bg_color=bg_color,
            output_path=str(output_path),
            job_id=job_id,
            ayah_data=ayah_data
        )

        if success:
            _update_job(job_id, 100, '✅ تم إنشاء الفيديو بنجاح!', completed=True)
        else:
            _update_job(job_id, 0, '❌ فشل إنشاء الفيديو', error=True)

        # Cleanup temp overlay files after a delay
        def cleanup():
            time.sleep(30)
            try:
                shutil.rmtree(str(job_dir), ignore_errors=True)
            except Exception:
                pass

        threading.Thread(target=cleanup, daemon=True).start()

    except Exception as e:
        _update_job(job_id, 0, f'❌ خطأ: {str(e)}', error=True)


def _update_job(job_id, progress, message, error=False, completed=False):
    """Update job progress."""
    if job_id in jobs:
        jobs[job_id]['progress'] = progress
        jobs[job_id]['message'] = message
        if error:
            jobs[job_id]['status'] = 'error'
        elif completed:
            jobs[job_id]['status'] = 'completed'

def _log_debug(job_id, msg):
    """Write debug log to Desktop."""
    try:
        desktop = Path(os.environ.get('USERPROFILE', '')) / 'Desktop'
        with open(str(desktop / 'quran_debug.txt'), 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%H:%M:%S")} [{job_id}] {msg}\n')
    except Exception:
        pass


def get_video_duration(video_path):
    """Get duration of video file using ffmpeg."""
    cmd = [FFMPEG_EXE, '-i', video_path, '-f', 'null', '-']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # Parse duration from stderr
        match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0


def get_audio_duration(audio_path):
    """Get duration of audio file using ffmpeg."""
    cmd = [FFMPEG_EXE, '-i', audio_path, '-f', 'null', '-']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0


def render_video(overlay_files, background_file, bg_color,
                 output_path, job_id, ayah_data):
    """Render final video by creating individual clips per ayah for perfect sync."""
    if not overlay_files or len(overlay_files) != len(ayah_data):
        return False

    try:
        job_dir = VISION_DIR / job_id
        clip_files = []
        total_clips = len(overlay_files)

        for idx, (ov_path, ayah) in enumerate(zip(overlay_files, ayah_data)):
            ayah_num = ayah.get('num', idx + 1)
            ayah_audio = ayah.get('audio')

            # Progress: 65% → 90%
            pct = 65 + int(25 * (idx / total_clips))
            _update_job(job_id, pct, f'({idx+1}/{total_clips}) جاري تجهيز مقطع الآية {ayah_num}...')

            ayah_duration = get_audio_duration(ayah_audio) if ayah_audio and os.path.exists(ayah_audio) else 5
            ayah_duration += 0.5  # small padding

            _update_job(job_id, pct, f'({idx+1}/{total_clips}) جاري معالجة فيديو الآية {ayah_num} بصوت {ayah_duration:.1f} ثانية...')

            clip_path = str(job_dir / f'clip_{idx}.mp4')

            bg_path = None
            if background_file and (VIDEO_DIR / background_file).exists():
                bg_path = str(VIDEO_DIR / background_file)
                bg_lower = background_file.lower()
                is_video_bg = bg_lower.endswith(('.mp4', '.webm'))
            else:
                bg_path = None
                is_video_bg = False

            # Build FFmpeg command for this single clip
            cmd = [FFMPEG_EXE, '-y']

            if bg_path and is_video_bg:
                # Video background (looped)
                cmd.extend(['-stream_loop', '-1', '-i', bg_path])
                # Overlay image
                cmd.extend(['-loop', '1', '-i', ov_path, '-t', str(ayah_duration)])
                # Ayah audio
                if ayah_audio and os.path.exists(ayah_audio):
                    cmd.extend(['-i', ayah_audio])
                # Filter
                cmd.extend([
                    '-filter_complex',
                    '[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[bg];'
                    f'[bg][1:v]overlay=(W-w)/2:(H-h)/2:format=auto[vout]',
                    '-map', '[vout]'
                ])
                if ayah_audio and os.path.exists(ayah_audio):
                    cmd.extend(['-map', '2:a', '-shortest'])
                else:
                    cmd.extend(['-t', str(ayah_duration)])

            elif bg_path:
                # Image background
                cmd.extend(['-loop', '1', '-i', bg_path, '-t', str(ayah_duration)])
                cmd.extend(['-loop', '1', '-i', ov_path, '-t', str(ayah_duration)])
                if ayah_audio and os.path.exists(ayah_audio):
                    cmd.extend(['-i', ayah_audio])
                cmd.extend([
                    '-filter_complex',
                    '[0:v]scale=1080:1920,setsar=1[bg];'
                    '[bg][1:v]overlay=(W-w)/2:(H-h)/2:format=auto[vout]',
                    '-map', '[vout]'
                ])
                if ayah_audio and os.path.exists(ayah_audio):
                    cmd.extend(['-map', '2:a', '-shortest'])
                else:
                    cmd.extend(['-t', str(ayah_duration)])

            else:
                # Solid color background
                try:
                    bg_rgb = bg_color.lstrip('#')
                    bg_rgb = f"0x{bg_rgb[0:2]}{bg_rgb[2:4]}{bg_rgb[4:6]}"
                except Exception:
                    bg_rgb = "0x0A0F1A"
                cmd.extend([
                    '-f', 'lavfi', '-i',
                    f'color=c={bg_rgb}:s=1080x1920:d={ayah_duration}:r=30,format=yuv420p'
                ])
                cmd.extend(['-loop', '1', '-i', ov_path, '-t', str(ayah_duration)])
                if ayah_audio and os.path.exists(ayah_audio):
                    cmd.extend(['-i', ayah_audio])
                cmd.extend([
                    '-filter_complex',
                    '[0:v]setpts=PTS-STARTPTS[bg];'
                    '[bg][1:v]overlay=(W-w)/2:(H-h)/2:format=auto[vout]',
                    '-map', '[vout]'
                ])
                if ayah_audio and os.path.exists(ayah_audio):
                    cmd.extend(['-map', '2:a', '-shortest'])
                else:
                    cmd.extend(['-t', str(ayah_duration)])

            # Common codec settings
            cmd.extend([
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-crf', '23', '-pix_fmt', 'yuv420p',
                '-r', '30',
                '-c:a', 'aac', '-b:a', '128k',
                clip_path
            ])

            _update_job(job_id, pct, f'({idx+1}/{total_clips}) جاري تشغيل FFmpeg لمقطع الآية {ayah_num}...')

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"[clip {idx}] FFmpeg error: {result.stderr[:500]}")
                return False

            if os.path.exists(clip_path) and os.path.getsize(clip_path) > 5000:
                clip_files.append(clip_path)
            else:
                print(f"[clip {idx}] Failed to create clip")
                return False

        # Concat all clips
        if len(clip_files) == 0:
            return False

        _update_job(job_id, 92, f'جاري دمج {len(clip_files)} مقطع في فيديو نهائي...')
        concat_file = job_dir / 'final_concat.txt'
        with open(str(concat_file), 'w', encoding='utf-8') as f:
            for cf in clip_files:
                f.write(f"file '{cf}'\n")

        concat_cmd = [
            FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0',
            '-i', str(concat_file),
            '-c:v', 'libx264', '-preset', 'ultrafast',
            '-crf', '23', '-pix_fmt', 'yuv420p',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            output_path
        ]
        result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"[concat] FFmpeg error: {result.stderr[:500]}")
            # Try re-encoding
            concat_cmd2 = [
                FFMPEG_EXE, '-y', '-f', 'concat', '-safe', '0',
                '-i', str(concat_file),
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-crf', '23', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                output_path
            ]
            result = subprocess.run(concat_cmd2, capture_output=True, text=True, timeout=600)

        _update_job(job_id, 96, 'جاري إنهاء الفيديو...')
        success = os.path.exists(output_path) and os.path.getsize(output_path) > 10000

        # Cleanup clips
        for cf in clip_files:
            try: os.remove(cf)
            except: pass
        try: os.remove(str(concat_file))
        except: pass

        return success

    except Exception as e:
        print(f"Render error: {e}")
        return False


# ── API Routes ─────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the main UI."""
    return send_from_directory(str(BASE_DIR), 'UI.html')


@app.route('/api/tools-check')
def api_tools_check():
    """Check availability of tools."""
    ffmpeg_ok = FFMPEG_EXE is not None
    pillow_ok = True

    bg_videos = len([f for f in VIDEO_DIR.glob('*.mp4')]) + \
                len([f for f in VIDEO_DIR.glob('*.webm')])

    return jsonify({
        'ffmpeg': ffmpeg_ok,
        'pillow': pillow_ok,
        'background_videos': bg_videos,
        'moderation_enabled': HAS_NUDENET,
        'arabic_reshaper': HAS_ARABIC_RESHAPER,
        'font': get_available_font_path() is not None,
        'fonts_dir': str(FONTS_DIR),
        'fonts_dir_exists': FONTS_DIR.exists(),
        'fonts_count': len(list(FONTS_DIR.glob('*.ttf'))),
        'meipass': str(getattr(sys, '_MEIPASS', 'none')),
        'has_meipass': hasattr(sys, '_MEIPASS'),
        'exe_path': str(sys.executable),
        'base_dir': str(BASE_DIR),
        'data_dir': str(DATA_DIR),
        'bundled_dir': str(BUNDLED_DIR)
    })


@app.route('/api/reciters')
def api_reciters():
    """Return list of reciters."""
    reciters = fetch_reciters()
    return jsonify(reciters)


@app.route('/api/surahs')
def api_surahs():
    """Return list of surahs from cache or fetch."""
    if SURAH_CACHE_FILE.exists():
        try:
            with open(str(SURAH_CACHE_FILE), 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception:
            pass

    try:
        data = fetch_json('http://api.alquran.cloud/v1/surah')
        if data.get('code') == 200 and data.get('data'):
            surahs = []
            for s in data['data']:
                surahs.append({
                    'number': s['number'],
                    'name': s['name'],
                    'englishName': s['englishName'],
                    'numberOfAyahs': s['numberOfAyahs']
                })
            return jsonify(surahs)
    except Exception:
        pass

    return jsonify([])


@app.route('/api/translations')
def api_translations():
    """Return available translation editions, grouped by language, English first."""
    LANG_NAMES = {
        'en': 'English', 'fr': 'Français', 'de': 'Deutsch', 'es': 'Español',
        'it': 'Italiano', 'pt': 'Português', 'nl': 'Nederlands', 'ru': 'Русский',
        'tr': 'Türkçe', 'fa': 'فارسی', 'ur': 'اردو', 'hi': 'हिन्दी',
        'bn': 'বাংলা', 'id': 'Bahasa Indonesia', 'ms': 'Bahasa Melayu',
        'so': 'Soomaali', 'sw': 'Kiswahili', 'th': 'ไทย', 'ja': '日本語',
        'zh': '中文', 'ku': 'Kurdî', 'az': 'Azərbaycanca', 'sq': 'Shqip',
        'bs': 'Bosanski', 'ro': 'Română', 'bg': 'Български', 'sr': 'Српски',
        'sv': 'Svenska', 'ta': 'தமிழ்', 'ml': 'മലയാളം', 'ko': '한국어',
        'uz': 'Oʻzbekcha', 'kk': 'Қазақша', 'ckb': 'کوردی',
    }
    try:
        data = fetch_json('http://api.alquran.cloud/v1/edition?type=translation&format=text')
        if data.get('code') == 200 and data.get('data'):
            editions = []
            for e in data['data']:
                lang = e.get('language', '')
                editions.append({
                    'identifier': e['identifier'],
                    'englishName': e.get('englishName', e.get('name', '')),
                    'languageName': LANG_NAMES.get(lang, lang.upper()),
                    'language': lang
                })
            editions.sort(key=lambda x: (
                0 if x['language'] == 'en' else 1,
                x['languageName'],
                x['englishName']
            ))
            return jsonify(editions)
    except Exception:
        pass
    return jsonify([])


@app.route('/api/fonts')
def api_fonts():
    """Return available fonts."""
    fonts = get_available_fonts()
    return jsonify(fonts)


@app.route('/api/backgrounds')
def api_backgrounds():
    """Return list of background files."""
    bgs = get_backgrounds()
    return jsonify(bgs)


@app.route('/api/background-thumb/<path:filename>')
def api_background_thumb(filename):
    """Return thumbnail for a background file."""
    filepath = VIDEO_DIR / filename
    if not filepath.exists():
        return '', 404

    ext = filename.lower()
    if ext.endswith(('.mp4', '.webm')):
        # Generate thumbnail from video
        thumb_path = VISION_DIR / f'thumb_{filename}.jpg'
        if not thumb_path.exists():
            cmd = [FFMPEG_EXE, '-y', '-i', str(filepath), '-vframes', '1',
                   '-vf', 'scale=240:426', str(thumb_path)]
            try:
                subprocess.run(cmd, capture_output=True, timeout=30)
            except Exception:
                pass

        if thumb_path.exists():
            return send_file(str(thumb_path), mimetype='image/jpeg')
        return '', 404
    else:
        # Send image directly
        return send_file(str(filepath))


@app.route('/api/outputs')
def api_outputs():
    """Return list of generated videos."""
    files = get_outputs()
    return jsonify(files)


@app.route('/api/download/<path:filename>')
def api_download(filename):
    """Download a generated video."""
    filepath = OUTPUTS_DIR / filename
    if not filepath.exists():
        return jsonify({'error': 'الملف غير موجود'}), 404
    return send_file(str(filepath), as_attachment=True,
                     download_name=filename,
                     mimetype='video/mp4')


@app.route('/api/delete/<path:filename>', methods=['DELETE'])
def api_delete(filename):
    """Delete a generated video."""
    filepath = OUTPUTS_DIR / filename
    if filepath.exists():
        try:
            os.remove(str(filepath))
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'الملف غير موجود'}), 404


@app.route('/api/generate', methods=['POST'])
def api_generate():
    """Start video generation job."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'بيانات غير صالحة'}), 400

    required = ['reciter_id', 'reciter_subfolder', 'surah_num', 'ayah_from', 'ayah_to']
    for r in required:
        if r not in data:
            return jsonify({'error': f'الحقل {r} مطلوب'}), 400

    job_id = str(uuid.uuid4())[:8]

    job = {
        'id': job_id,
        'status': 'queued',
        'progress': 0,
        'message': 'في قائمة الانتظار...',
        'params': data,
        'created_at': time.time()
    }

    jobs[job_id] = job

    # Start generation in background (with Flask request context)
    @copy_current_request_context
    def _run_generation():
        generate_video_job(job_id, data)

    thread = threading.Thread(target=_run_generation, daemon=True)
    thread.start()

    return jsonify({'job_id': job_id, 'status': 'queued'})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    """Get job status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'status': 'error', 'message': 'المهمة غير موجودة'})
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message']
    })


@app.route('/api/upload-background', methods=['POST'])
def api_upload_background():
    """Upload a background file."""
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم رفع ملف'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'اسم الملف فارغ'}), 400

    # Check file extension
    allowed = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({'error': 'نوع الملف غير مدعوم. المدعوم: JPG, PNG, MP4'}), 400

    # Check file size (max 100MB)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 100 * 1024 * 1024:
        return jsonify({'error': 'الملف كبير جداً. الحد الأقصى 100 ميجابايت'}), 400

    # Save file
    filename = file.filename
    filepath = VIDEO_DIR / filename
    # Avoid overwriting
    counter = 1
    while filepath.exists():
        name, ext = os.path.splitext(filename)
        filename = f'{name}_{counter}{ext}'
        filepath = VIDEO_DIR / filename
        counter += 1

    file.save(str(filepath))

    # ── Content moderation ──
    is_image = ext in {'.jpg', '.jpeg', '.png', '.gif'}
    is_video = ext in {'.mp4', '.webm'}
    if HAS_NUDENET:
        try:
            if is_image:
                ok, msg = moderate_image(str(filepath))
            elif is_video:
                ok, msg = moderate_video(str(filepath))
            else:
                ok, msg = True, "OK"
            if not ok:
                os.remove(str(filepath))
                return jsonify({'error': f'⚠️ هذا المحتوى غير مناسب: {msg}'}), 403
        except Exception as e:
            print(f"Moderation error: {e}")

    return jsonify({'success': True, 'filename': filename})


@app.route('/api/backgrounds/<path:filename>', methods=['DELETE'])
def api_delete_background(filename):
    """Delete a background file."""
    filepath = VIDEO_DIR / filename
    if not filepath.exists():
        return jsonify({'error': 'الملف غير موجود'}), 404

    try:
        os.remove(str(filepath))
        # Also remove thumbnail
        thumb = VISION_DIR / f'thumb_{filename}.jpg'
        if thumb.exists():
            os.remove(str(thumb))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Serve static files ─────────────────────────────────────────────────

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files."""
    full_path = BASE_DIR / path
    if full_path.exists() and full_path.is_file():
        return send_from_directory(str(BASE_DIR), path)
    return '', 404


# ── Main ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    try:
        print('=' * 50)
        print('  Quran Reels Generator')
        print('  http://localhost:5001')
        print('=' * 50)
        print(f'  FFmpeg: {"✅" if FFMPEG_EXE else "❌"}')
        print(f'  Pillow: ✅')
        print(f'  Arabic Reshaper: {"✅" if HAS_ARABIC_RESHAPER else "❌"}')
        print(f'  NudeNet: {"✅" if HAS_NUDENET else "❌"}')
        print(f'  Outputs: {OUTPUTS_DIR}')
        print(f'  Fonts: {FONTS_DIR}')
        print(f'  Backgrounds: {VIDEO_DIR}')
        print('=' * 50)
        print('  Opening browser...')
        print('  Press Ctrl+C to stop')
        print('=' * 50)

        # Auto-open browser after a short delay
        def _open_browser():
            try:
                import time
                time.sleep(1.5)
                webbrowser.open('http://localhost:5001')
            except Exception:
                pass

        threading.Thread(target=_open_browser, daemon=True).start()

        app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

    except Exception as e:
        print(f'\n❌ خطأ: {e}')
        print('اضغط Enter للخروج...')
        try:
            input()
        except:
            pass