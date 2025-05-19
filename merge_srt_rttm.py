import srt
from datetime import timedelta
from pathlib import Path

def parse_rttm(rttm_path):
    """
    讀取 .rttm，回傳 list of dict:
    [{'start': float(s), 'end': float(s), 'speaker': 'speaker_1'}, ...]
    """
    segments = []
    for line in open(rttm_path, encoding='utf-8'):
        # RTTM 格式: TYPE FILE CHANNEL START DUR ORTH TYP SPEAKER_ID CONF
        parts = line.strip().split()
        if len(parts) < 9: 
            continue
        start = float(parts[3])
        dur   = float(parts[4])
        speaker = parts[7]
        segments.append({'start': start, 'end': start+dur, 'speaker': speaker})
    return segments

def find_best_speaker(seg_start, seg_end, diarization_segments):
    """
    給一個字幕段 (start/end in sec)，找出重疊時間最長的 speaker
    """
    best, best_overlap = None, 0.0
    for d in diarization_segments:
        # 計算重疊時間
        overlap_start = max(seg_start, d['start'])
        overlap_end   = min(seg_end,   d['end'])
        overlap = max(0.0, overlap_end - overlap_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = d['speaker']
    return best or "unknown"

def merge_srt_rttm(srt_path, rttm_path, output_path):
    # 1. 解析 RTTM
    diarization = parse_rttm(rttm_path)
    # 2. 解析 SRT
    with open(srt_path, encoding='utf-8') as f:
        subs = list(srt.parse(f.read()))
    # 3. 為每句字幕加上 speaker 標籤
    new_subs = []
    for sub in subs:
        start_sec = sub.start.total_seconds()
        end_sec   = sub.end.total_seconds()
        spk = find_best_speaker(start_sec, end_sec, diarization)
        # 在每段文字前加上「Speaker_X: 」
        sub.content = f"{spk}: {sub.content}"
        new_subs.append(sub)
    # 4. 輸出為新的 SRT
    result = srt.compose(new_subs)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"已輸出結合語者的字幕：{output_path}")

# 範例呼叫
merge_srt_rttm(
    srt_path = Path("output/meeting_20250519_174055.srt"),
    rttm_path= Path("output/meeting_20250519_174055.rttm"),
    output_path=Path("output/meeting_20250519_174055.speaker.srt")
)
