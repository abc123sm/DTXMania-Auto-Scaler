import os
import sys
import re

# 优先级: 数值越小优先级越高。在面临同拍和同小节削减时，优先保留高优先级乐器。
# 主镲 > 军鼓 > 踩镲 > 副镲 > 嗵鼓 > 其他
PRIORITY = {
    '16': 1, '1A': 2, '12': 3, '11': 4, '18': 4,
    '14': 5, '15': 6, '17': 7, 
    '13': -1, '1B': 0, '1C': 0, # 底鼓最高级，同拍优先剔除左脚
    'DEFAULT': 9
}

# 5段难度配置字典
DIFFICULTIES = {
    'bsc': {
        'suffix': '_aimode_bsc.dtx',
        'diff_ratio': 0.4,
        'rules': {
            '13': 1.0,
            '1B': 99.0, # 完全剔除左脚
            '1C': 99.0,
            'DEFAULT': 0.25
        },
        'max_hand_simul': 1,
        'max_hands_ch': 1,
        'max_foots_per_bar': 1
    },
    'adv': {
        'suffix': '_aimode_adv.dtx',
        'diff_ratio': 0.7,
        'rules': {
            '13': 0.25,
            '1B': 1.0, # 允许4拍一次左脚
            '1C': 1.0,
            'DEFAULT': 0.125
        },
        'max_hand_simul': 2,
        'max_hands_ch': 2,
        'max_foots_per_bar': 2
    },
    'ext': {
        'suffix': '_aimode_ext.dtx',
        'diff_ratio': 0.85,
        'rules': {
            '13': 0.125,
            '1B': 0.25,
            '1C': 0.25,
            'DEFAULT': 0.125
        },
        'max_hand_simul': 99,
        'max_hands_ch': 3,
        'max_foots_per_bar': 99
    },
    'mstr': {
        'suffix': '_aimode_mstr.dtx',
        'diff_ratio': 0.95,
        'rules': {
            '16': 0.04,
            '1A': 0.04,
            '1B': 0.07,
            '1C': 0.07,
            'DEFAULT': 0.07
        },
        'max_hand_simul': 99,
        'max_hands_ch': 5,
        'max_foots_per_bar': 99
    }
}

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
        pass
    return 'shift_jis'

def get_dtx_title(lines):
    for line in lines:
        if line.upper().startswith('#TITLE:'):
            return line.split(':', 1)[1].strip()
    return "Unknown Title"

def process_single_dtx(file_path):
    enc = detect_encoding(file_path)
    read_enc = enc
    if read_enc == 'utf-16':
        pass

    with open(file_path, 'r', encoding=read_enc) as f:
        lines = f.readlines()
        
    original_title = get_dtx_title(lines)
    pattern = re.compile(r'^#(\d{3})([0-9a-zA-Z]{2}):\s*([0-9a-zA-Z]+)')
    
    generated_files = {}
    import copy

    for diff_key, diff_cfg_orig in DIFFICULTIES.items():
        diff_cfg = copy.deepcopy(diff_cfg_orig)
        
        all_notes = []
        parsed_lines = [] 
        
        for line_idx, line in enumerate(lines):
            match = pattern.match(line)
            if match:
                bar_str = match.group(1)
                ch = match.group(2)
                seq = match.group(3)
                
                if ch in DRUM_CHANNELS and len(seq) % 2 == 0:
                    bar_num = int(bar_str)
                    objs = [seq[i:i+2] for i in range(0, len(seq), 2)]
                    total_objs = len(objs)
                    parsed_lines.append({'is_drum': True, 'objs': objs, 'ch': ch, 'prefix': line.split(':')[0]})
                    
                    for obj_idx, obj in enumerate(objs):
                        if obj != '00':
                            abs_time = bar_num + obj_idx / total_objs
                            priority = PRIORITY.get(ch, PRIORITY['DEFAULT'])
                            all_notes.append({
                                'line_idx': line_idx,
                                'obj_idx': obj_idx,
                                'abs_time': abs_time,
                                'bar_num': bar_num,
                                'ch': ch,
                                'obj': obj,
                                'priority': priority,
                                'keep': False
                            })
                else:
                    parsed_lines.append({'is_drum': False, 'raw': line})
            else:
                parsed_lines.append({'is_drum': False, 'raw': line})

        # 第1.5阶段：单小节内种类限制 (仅手部限制种类)
        max_hands_ch = diff_cfg.get('max_hands_ch', 99)
        bar_notes = {}
        for note in all_notes:
            b = note['bar_num']
            if b not in bar_notes:
                bar_notes[b] = []
            if note['ch'] in HAND_CHANNELS:
                bar_notes[b].append(note)
            else:
                note['keep_bar'] = True # 脚部等特殊通道放行，在第二阶段处理数量
                
        for b, notes in bar_notes.items():
            channels_in_bar = set([n['ch'] for n in notes])
            if len(channels_in_bar) > max_hands_ch:
                ch_priority = {ch: PRIORITY.get(ch, PRIORITY['DEFAULT']) for ch in channels_in_bar}
                sorted_channels = sorted(list(channels_in_bar), key=lambda x: ch_priority[x])
                kept_channels = set(sorted_channels[:max_hands_ch])
                
                for n in notes:
                    if n['ch'] not in kept_channels:
                        n['keep_bar'] = False
                    else:
                        n['keep_bar'] = True
            else:
                for n in notes:
                    n['keep_bar'] = True

        # 第二阶段：智能精算过滤 (时间间距与同拍数量)
        all_notes.sort(key=lambda x: (x['abs_time'], x['priority']))
        
        last_note_time = {ch: -100.0 for ch in DRUM_CHANNELS}
        last_original_time = {ch: -100.0 for ch in DRUM_CHANNELS} # 新增：记录原始间距
        current_run_length = {ch: 0 for ch in DRUM_CHANNELS} # 新增：同轨连击数
        
        current_time_window = -100.0
        current_hand_count = 0
        current_foot_window = -100.0
        max_hand_simul = diff_cfg['max_hand_simul']
        
        current_bar_num = -1
        current_bar_foot_count = 0
        
        for note in all_notes:
            abs_time = note['abs_time']
            ch = note['ch']
            bar_num = note['bar_num']
            
            if bar_num != current_bar_num:
                current_bar_num = bar_num
                current_bar_foot_count = 0
            
            # Fatigue Control: 监测原曲同轨连击状态
            orig_dist = abs_time - last_original_time[ch]
            if orig_dist <= 0.13: # 8分或更密
                current_run_length[ch] += 1
            else:
                current_run_length[ch] = 1 # 连击断开
            last_original_time[ch] = abs_time
            
            if not note.get('keep_bar', True):
                note['keep'] = False
                continue
                
            min_dist = diff_cfg['rules'].get(ch, diff_cfg['rules']['DEFAULT'])
            
            # 触发疲劳惩罚：ADV 难度下，如果同一鼓面上连续 8 分音符超过 24 下（3个小节），强行降频为 4 分音符间距
            if diff_key == 'adv' and ch in HAND_CHANNELS and current_run_length[ch] > 24:
                min_dist = max(min_dist, 0.25)
            
            if (abs_time - last_note_time[ch]) < min_dist - 0.001:
                note['keep'] = False
                continue
                
            if ch in HAND_CHANNELS:
                if abs_time - current_time_window < 0.01:
                    if current_hand_count < max_hand_simul:
                        note['keep'] = True
                        current_hand_count += 1
                        last_note_time[ch] = abs_time
                    else:
                        note['keep'] = False
                else:
                    note['keep'] = True
                    current_time_window = abs_time
                    current_hand_count = 1
                    last_note_time[ch] = abs_time
            elif ch in ['13', '1B', '1C']:
                max_foots = diff_cfg.get('max_foots_per_bar', 99)
                
                # 同拍时，保留优先级高的（如 13 优先于 1B/1C，起到剔除左脚效果）
                if abs_time - current_foot_window < 0.01:
                    if diff_key == 'adv':
                        note['keep'] = False
                        continue
                
                if current_bar_foot_count < max_foots:
                    note['keep'] = True
                    current_foot_window = abs_time
                    last_note_time[ch] = abs_time
                    current_bar_foot_count += 1
                else:
                    note['keep'] = False
            else:
                note['keep'] = True
                last_note_time[ch] = abs_time

        # 第三阶段：回写数据
        for note in all_notes:
            if not note['keep']:
                l_idx = note['line_idx']
                o_idx = note['obj_idx']
                parsed_lines[l_idx]['objs'][o_idx] = '00'
                
        out_lines = []
        for l_idx, pl in enumerate(parsed_lines):
            line_upper = lines[l_idx].upper()
            if line_upper.startswith('#TITLE:'):
                out_lines.append(f"#TITLE: {original_title} (AI mode)\n")
                continue
            if line_upper.startswith('#DLEVEL:'):
                try:
                    val = float(lines[l_idx].split(':')[1].strip())
                    new_val = int(val * diff_cfg['diff_ratio'])
                    out_lines.append(f"#DLEVEL: {new_val}\n")
                except:
                    out_lines.append(lines[l_idx])
                continue
                
            if pl['is_drum']:
                new_seq = ''.join(pl['objs'])
                out_lines.append(f"{pl['prefix']}: {new_seq}\n")
            else:
                out_lines.append(pl['raw'])
                
        out_path = file_path.replace('.dtx', diff_cfg['suffix'])
        with open(out_path, 'w', encoding=enc) as f:
            f.writelines(out_lines)
            
        generated_files[diff_key] = os.path.basename(out_path)
        
    return original_title, generated_files, enc

def process_directory(dir_path):
    try:
        print(f"Scanning directory: {dir_path}")
    except:
        pass
    
    set_def_path = os.path.join(dir_path, "set.def")
    if os.path.exists(set_def_path):
        try:
            # 尝试读取第一行判断是否为 AI mode
            enc = detect_encoding(set_def_path)
            is_ai = False
            with open(set_def_path, 'r', encoding=enc, errors='ignore') as f:
                first_line = f.readline()
                if "(AI mode)" in first_line:
                    is_ai = True
            
            if not is_ai:
                try: print("Skipping directory (Protected Original)")
                except: pass
                return
            else:
                try: print("Updating AI generated set.def")
                except: pass
        except Exception as e:
            try: print("Skipping directory (Error reading set.def)")
            except: pass
            return
    
    dtx_files = [f for f in os.listdir(dir_path) if f.lower().endswith('.dtx')]
    main_dtx = None
    for f in dtx_files:
        fl = f.lower()
        if not any(x in fl for x in ['_aimode_bsc', '_aimode_adv', '_aimode_ext', '_aimode_mstr', '_bsc', '_adv', '_ext', '_mstr', '_easy']):
            main_dtx = f
            break
            
    if not main_dtx:
        return
        
    main_dtx_path = os.path.join(dir_path, main_dtx)
    title, gen_files, enc = process_single_dtx(main_dtx_path)
    
    set_def_path = os.path.join(dir_path, "set.def")
    with open(set_def_path, 'w', encoding=enc) as f:
        f.write(f"#TITLE {title} (AI mode)\n\n")
        f.write(f"#L1LABEL BASIC\n")
        f.write(f"#L1FILE {gen_files['bsc']}\n\n")
        f.write(f"#L2LABEL ADVANCED\n")
        f.write(f"#L2FILE {gen_files['adv']}\n\n")
        f.write(f"#L3LABEL EXTREME\n")
        f.write(f"#L3FILE {gen_files['ext']}\n\n")
        f.write(f"#L4LABEL MASTER\n")
        f.write(f"#L4FILE {gen_files['mstr']}\n\n")
        f.write(f"#L5LABEL MASTER+\n")
        f.write(f"#L5FILE {main_dtx}\n")
        
    try:
        print(f"Created set.def successfully in {dir_path}")
    except:
        pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(1)
    
    target = sys.argv[1]
    if os.path.isfile(target):
        process_directory(os.path.dirname(target))
    elif os.path.isdir(target):
        for root, dirs, files in os.walk(target):
            has_dtx = any(f.lower().endswith('.dtx') for f in files)
            if has_dtx:
                process_directory(root)
