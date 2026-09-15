import os
import re

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw = f.read(4)
        if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'): return 'utf-16'
        elif raw.startswith(b'\xef\xbb\xbf'): return 'utf-8-sig'
    return 'shift_jis'

def get_channel_stats(file_path):
    enc = detect_encoding(file_path)
    try:
        with open(file_path, 'r', encoding=enc, errors='ignore') as f:
            lines = f.readlines()
    except:
        return None

    pattern = re.compile(r'^#(\d{3})([0-9a-zA-Z]{2}):\s*([0-9a-zA-Z]+)')
    notes = {'1B': [], '1C': [], '13': []}
    dlevel = 'unknown'

    for line in lines:
        if line.upper().startswith('#DLEVEL:'):
            dlevel = line.split(':')[1].strip()
        match = pattern.match(line)
        if match:
            bar = int(match.group(1))
            ch = match.group(2)
            seq = match.group(3)
            if ch in ['13', '1B', '1C'] and len(seq) % 2 == 0:
                objs = [seq[i:i+2] for i in range(0, len(seq), 2)]
                total = len(objs)
                for i, o in enumerate(objs):
                    if o != '00':
                        notes[ch].append(bar + i / total)

    stats = {}
    for ch, n_list in notes.items():
        n_list.sort()
        count = len(n_list)
        min_dist = 999
        if count > 1:
            for i in range(1, count):
                dist = n_list[i] - n_list[i-1]
                if dist > 0.01 and dist < min_dist:
                    min_dist = dist
        stats[ch] = {'count': count, 'min_dist': min_dist if count > 1 else 'N/A'}

    print(f'File: {os.path.basename(file_path)} (Level: {dlevel})')
    print(f"  Bass (13): {stats['13']['count']} notes, min_dist = {stats['13']['min_dist']}")
    print(f"  Left (1B): {stats['1B']['count']} notes, min_dist = {stats['1B']['min_dist']}")
    print(f"  HiHat(1C): {stats['1C']['count']} notes, min_dist = {stats['1C']['min_dist']}")

dir_path = 'c:/game/DTXManiaNX 1.4.0 Basic FSP/DTXFiles/approvedtx/Zattou Bokura no Machi'
for f in os.listdir(dir_path):
    if f.lower().endswith('.dtx'):
        get_channel_stats(os.path.join(dir_path, f))
