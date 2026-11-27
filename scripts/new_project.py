#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给一首新歌开一个工作目录，把模板、脚本、字体、谱例骨架一次放好。

用法：
    python3 new_project.py ~/Downloads/小星星动态谱
    python3 new_project.py . --title "小星星"     # 当前目录，顺便写好标题

开完目录后要做三件事（详见 SKILL.md）：
    1. 把范唱 mp3 拷进目录，改 score.json 的 meta.audio
    2. 逐音录谱（score.json 的 notes），再跑 align.py 对拍
    3. make_font.py → build.py 出单文件 index.html
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
TPL = os.path.join(SKILL, 'assets', 'template', 'score.template.html')
FONTS = os.path.join(SKILL, 'assets', 'fonts')
SCRIPTS = ['build.py', 'align.py', 'make_font.py']


def die(msg):
    print('✗ ' + msg)
    sys.exit(1)


def skeleton(title):
    """最小可用谱例骨架：2 小节、6 个音、1 句，字段齐全可直接改。"""
    return {
        "meta": {
            "title": title,
            "lyricist": "",
            "composer": "",
            "key": "C",
            "keyLabel": "1=C",
            "timeSig": [4, 4],
            "tempo": 84,
            "tempoText": "行板  深情地",
            "audio": "范唱.mp3",
            "audioOffset": 0,
            "introBeats": 8,
            "offsetVersion": 1,
            "mode": "sing",
            "background": "",
            "skin": "bubble",
            "palette": "soft",
        },
        "notes": [
            {"degree": 1, "octave": 0, "startBeat": 0, "durBeats": 1, "lyric": "一"},
            {"degree": 2, "octave": 0, "startBeat": 1, "durBeats": 1, "lyric": "二"},
            {"degree": 3, "octave": 0, "startBeat": 2, "durBeats": 1, "lyric": "三"},
            {"degree": 3, "octave": 0, "startBeat": 3, "durBeats": 1, "lyric": "三"},
            {"degree": 5, "octave": 0, "startBeat": 4, "durBeats": 2, "lyric": "五"},
            {"degree": 0, "octave": 0, "startBeat": 6, "durBeats": 2, "lyric": ""},
        ],
        "slurs": [],
        "dynamics": [{"beat": 0, "text": "mf", "kind": "dyn"}],
        "sections": [{"label": "第一句", "startBeat": 0, "endBeat": 8,
                      "text": "把这一句的歌词写在这里"}],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target', help='工作目录（不存在会自动创建）')
    ap.add_argument('--title', default='新歌', help='歌名，写进 score.json')
    ap.add_argument('--force', action='store_true', help='目标已存在文件时也覆盖')
    a = ap.parse_args()

    dst = os.path.abspath(os.path.expanduser(a.target))
    if not os.path.isfile(TPL):
        die('找不到模板 %s' % TPL)
    os.makedirs(dst, exist_ok=True)

    def put(src, rel):
        out = os.path.join(dst, rel)
        if os.path.exists(out) and not a.force:
            print('  · 已存在，跳过 %s' % rel)
            return
        os.makedirs(os.path.dirname(out) or dst, exist_ok=True)
        shutil.copy2(src, out)
        print('  + %s' % rel)

    put(TPL, 'score.template.html')
    for s in SCRIPTS:
        put(os.path.join(HERE, s), s)
    for f in sorted(os.listdir(FONTS)):
        put(os.path.join(FONTS, f), os.path.join('fonts', f))

    score = os.path.join(dst, 'score.json')
    if not os.path.exists(score) or a.force:
        with open(score, 'w', encoding='utf-8') as fh:
            json.dump(skeleton(a.title), fh, ensure_ascii=False, indent=1)
        print('  + score.json（骨架，含 6 个示例音，替换成你的谱）')

    print('\n目录就绪：%s' % dst)
    print('下一步：')
    print('  1) cp 范唱.mp3 .        # 音频放进目录，文件名与 meta.audio 一致')
    print('  2) 编辑 score.json      # 逐音写 notes（degree/octave/startBeat/durBeats/lyric）')
    print('  3) python3 align.py --write   # 自动测速度与起唱，写回 meta')
    print('  4) python3 make_font.py       # 重切字库（歌词换了就要跑）')
    print('  5) python3 build.py           # 出单文件 index.html（底图+音频内嵌）')


if __name__ == '__main__':
    main()
