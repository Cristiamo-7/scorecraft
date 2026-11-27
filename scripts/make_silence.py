#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""造一段静音音轨：没有范唱录音时也能预览谱面、跑版面体检。

为什么需要它：page 的唯一时钟是 audio.currentTime，**没有可解码的音频就会退回虚拟时钟**，
动画不再跟着注入的时间走，check_layout.py 的逐拍扫描就失去意义。

用法：
    python3 make_silence.py 范唱.wav --seconds 90     # 只生成文件
    python3 make_silence.py --score score.json        # 按 meta.audio 换后缀生成，并改写 meta.audio
    python3 make_silence.py 静音.wav --score score.json   # 指定名字，同时改写 meta.audio

纯标准库（wave + struct），不需要 ffmpeg。生成的是 8kHz 单声道 16bit PCM，
90 秒约 1.4MB，内嵌进 HTML 后 base64 约 1.9MB。
"""
import argparse
import json
import os
import sys
import wave

RATE = 8000          # 8kHz 足够：只要时长可读，采样率不影响版面与动画
WIDTH = 2            # 16bit


def write_silence(path, seconds):
    total = int(RATE * seconds)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(WIDTH)
        w.setframerate(RATE)
        w.writeframes(b'\x00\x00' * total)        # 全零即静音，头部信息由 wave 写好


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target', nargs='?', help='输出文件名（默认按 --score 的 meta.audio 或 silence.wav）')
    ap.add_argument('--score', default=None, help='谱例 JSON：从中读 meta.audio，并把它改成生成的 wav')
    ap.add_argument('--seconds', type=float, default=90, help='时长（默认 90 秒）')
    a = ap.parse_args()

    score_path = os.path.abspath(a.score) if a.score else None
    data = None
    if score_path:
        if not os.path.isfile(score_path):
            sys.exit('✗ 找不到 %s' % score_path)
        data = json.load(open(score_path, encoding='utf-8'))

    name = a.target
    if not name and data is not None:
        old = (data.get('meta') or {}).get('audio') or 'silence.wav'
        name = os.path.splitext(old)[0] + '.wav'      # 同名换后缀，方便一眼看出是占位音轨
    name = name or 'silence.wav'

    out = os.path.join(os.path.dirname(score_path) or '.', name) if score_path else name
    write_silence(out, a.seconds)
    size = os.path.getsize(out) / 1024

    if data is not None:
        data.setdefault('meta', {})['audio'] = name
        with open(score_path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('  meta.audio → %s' % name)

    print('✓ 静音音轨 %s（%.0f 秒，%.0f KB）' % (out, a.seconds, size))


if __name__ == '__main__':
    main()
