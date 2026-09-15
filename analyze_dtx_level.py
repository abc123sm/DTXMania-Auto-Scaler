import os
import re
import sys

DRUM_CHANNELS = ['11', '12', '13', '14', '15', '16', '17', '18', '19', '1A', '1B', '1C']
HAND_CHANNELS = ['11', '12', '14', '15', '16', '17', '18', '19', '1A']

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw = f.read(4)
        if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
            return 'utf-16'
        elif raw.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read()
        return 'utf-8-sig'
    except:
        return 'shift_jis'

def analyze_dtx(file_path):
    enc = detect_encoding(file_path)
    with open(file_path, 'r', encoding=enc, errors='ignore') as f:
        lines = f.readlines()
        
    dlevel = None
    title = ""
    for line in lines:
        if line.upper().startswith('#TITLE:'):
            title = line.split(':', 1)[1].strip()
        if line.upper().startswith('#DLEVEL:'):
            try:
                dlevel = float(line.split(':')[1].strip())
                if dlevel > 10:  # 有的版本 50 代表 5.0
                    dlevel = dlevel / 10.0
            except:
                pass
                
    if dlevel is None:
        return None
        
    pattern = re.compile(r'^#(\d{3})([0-9a-zA-Z]{2}):\s*([0-9a-zA-Z]+)')
    
    all_notes = []
    
    for line in lines:
        match = pattern.match(line)
        if match:
            bar_num = int(match.group(1))
            ch = match.group(2)
            seq = match.group(3)
            
            if ch in DRUM_CHANNELS and len(seq) % 2 == 0:
                objs = [seq[i:i+2] for i in range(0, len(seq), 2)]
                total_objs = len(objs)
                for obj_idx, obj in enumerate(objs):
                    if obj != '00':
                        abs_time = bar_num + obj_idx / total_objs
                        all_notes.append({'time': abs_time, 'ch': ch})
                        
    all_notes.sort(key=lambda x: x['time'])
    
    # Analyze
    if not all_notes:
        return None
        
    min_dist_hand = 999
    min_dist_bass = 999
    
    last_hand_time = -100
    last_bass_time = -100
    
    simul_hands = {}
    
    for note in all_notes:
        t = note['time']
        ch = note['ch']
        
        if ch in HAND_CHANNELS:
            if t - last_hand_time > 0.01:
                dist = t - last_hand_time
                if dist < min_dist_hand: min_dist_hand = dist
            last_hand_time = t
            
            # Count simul
            bucket = round(t, 2)
            simul_hands[bucket] = simul_hands.get(bucket, 0) + 1
            
        elif ch in ['13', '1B', '1C']:
            if t - last_bass_time > 0.01:
                dist = t - last_bass_time
                if dist < min_dist_bass: min_dist_bass = dist
            last_bass_time = t
            
    max_hand_simul = max(simul_hands.values()) if simul_hands else 0
    
    return {
        'title': title,
        'dlevel': dlevel,
        'min_dist_hand': min_dist_hand,
        'min_dist_bass': min_dist_bass,
        'max_hand_simul': max_hand_simul,
        'total_notes': len(all_notes),
        'file': os.path.basename(file_path)
    }

def scan_dir(dir_path):
    results = []
    for root, _, files in os.walk(dir_path):
        for f in files:
            if f.lower().endswith('.dtx'):
                res = analyze_dtx(os.path.join(root, f))
                if res:
                    results.append(res)
    return results

def main():
    base_dir = "c:/game/DTXManiaNX 1.4.0 Basic FSP/DTXFiles"
    
    maoke = scan_dir(os.path.join(base_dir, "Maoke Jackson"))
    approv = scan_dir(os.path.join(base_dir, "approvedtx"))
    
    # Target 1: BSC analysis
    bsc_maoke = [r for r in maoke if r['dlevel'] < 2.0]
    bsc_approv = [r for r in approv if r['dlevel'] < 3.5]
    
    print("--- BSC Level Analysis ---")
    print(f"Maoke Jackson (<2.0): {len(bsc_maoke)} tracks")
    for r in bsc_maoke[:5]:
        print(f"[{r['dlevel']}] {r['file']} - MinHand:{r['min_dist_hand']:.3f}, MinBass:{r['min_dist_bass']:.3f}, MaxSimul:{r['max_hand_simul']}")
        
    print(f"\napprovedtx (<3.5): {len(bsc_approv)} tracks")
    for r in bsc_approv[:5]:
        print(f"[{r['dlevel']}] {r['file']} - MinHand:{r['min_dist_hand']:.3f}, MinBass:{r['min_dist_bass']:.3f}, MaxSimul:{r['max_hand_simul']}")
        
    # Target 2: ADV analysis
    adv_maoke = [r for r in maoke if 2.5 <= r['dlevel'] <= 4.0]
    adv_approv = [r for r in approv if 3.5 <= r['dlevel'] <= 6.0]
    
    print("\n--- ADV Level Analysis ---")
    print(f"Maoke Jackson (2.5-4.0): {len(adv_maoke)} tracks")
    for r in adv_maoke[:5]:
        print(f"[{r['dlevel']}] {r['file']} - MinHand:{r['min_dist_hand']:.3f}, MinBass:{r['min_dist_bass']:.3f}, MaxSimul:{r['max_hand_simul']}")
        
    print(f"\napprovedtx (3.5-6.0): {len(adv_approv)} tracks")
    for r in adv_approv[:5]:
        print(f"[{r['dlevel']}] {r['file']} - MinHand:{r['min_dist_hand']:.3f}, MinBass:{r['min_dist_bass']:.3f}, MaxSimul:{r['max_hand_simul']}")

if __name__ == '__main__':
    main()
