#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 score.json 打包成可直接双击打开的单文件 index.html。

用法：
    python3 build.py                 # 用同目录的 score.json（默认：底图+音频全部内嵌，单文件离线可用）
    python3 build.py --link          # 不内嵌底图/音频，只做外链版（体积小，方便反复改样式）
    python3 build.py 别处/score.json  # 指定其它谱例文件

换歌流程：改 score.json（或复制一份改）→ 把新音频放进本目录 → 跑一次这个脚本。
"""
import base64, json, html, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, 'score.template.html')
OUT = os.path.join(HERE, 'index.html')

MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.webp': 'image/webp', '.gif': 'image/gif',
        '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.wav': 'audio/wav',
        '.ogg': 'audio/ogg'}


def die(msg):
    print('✗ ' + msg)
    sys.exit(1)


def data_uri(path):
    """把本地文件读成 data: URI，方便塞进 HTML 里。"""
    ext = os.path.splitext(path)[1].lower()
    mime = MIME.get(ext, 'application/octet-stream')
    with open(path, 'rb') as f:
        b = base64.b64encode(f.read()).decode('ascii')
    return 'data:%s;base64,%s' % (mime, b)


def probe_duration(path):
    """用 ffprobe 读音频时长，失败就返回 None。"""
    if not shutil.which('ffprobe'):
        return None
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nw=1:nk=1', path],
            capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip())
    except Exception:
        return None


def validate(d):
    m = d.get('meta', {})
    notes = d.get('notes', [])
    if not notes:
        die('score.json 里没有 notes，无法生成。')

    for k in ('title', 'tempo', 'audioOffset'):
        if k not in m:
            die('meta 缺少必需字段：%s' % k)

    # 每个 note 的必需字段
    for i, n in enumerate(notes):
        for k in ('degree', 'startBeat', 'durBeats'):
            if k not in n:
                die('第 %d 个音符缺少字段 %s' % (i + 1, k))
        n.setdefault('octave', 0)
        if not (0 <= n['degree'] <= 7):
            die('第 %d 个音符 degree=%s 越界（应为 0~7）' % (i + 1, n['degree']))
        if n['durBeats'] <= 0:
            die('第 %d 个音符 durBeats 必须大于 0' % (i + 1))

    # 排序与重叠检查（重叠会让音块叠在一起）
    notes.sort(key=lambda n: (n['startBeat'], -n['durBeats']))
    for a, b in zip(notes, notes[1:]):
        if b['startBeat'] < a['startBeat'] + a['durBeats'] - 1e-6:
            print('  ! 提示：beat %g 起的两个音重叠，显示会相互压盖'
                  % b['startBeat'])
            break

    beats = max(n['startBeat'] + n['durBeats'] for n in notes)
    # 小节数按拍数推算，补齐到 4 拍的整数倍
    print('  音符 %d 个，共 %.1f 拍 ≈ %d 小节' % (len(notes), beats, round(beats / 4)))

    for s in d.get('sections', []):
        if s.get('endBeat', 0) > beats + 1e-6:
            print('  ! 提示：%s 的 endBeat 超出谱面总拍数' % s.get('label', '?'))
    return m


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    inline = '--link' not in sys.argv          # 默认把底图、音频都嵌进 HTML
    src = argv[0] if argv else os.path.join(HERE, 'score.json')
    if not os.path.isfile(src):
        die('找不到 %s' % src)
    if not os.path.isfile(TPL):
        die('找不到模板 score.template.html')

    d = json.load(open(src, encoding='utf-8'))
    m = validate(d)

    tpl = open(TPL, encoding='utf-8').read()
    for ph in ('__SCORE_JSON__', '__TITLE__', '__SUB__', '__AUDIO__'):
        if ph not in tpl:
            die('模板缺少占位符 %s' % ph)

    # 副标题：词曲作者 + 用途，缺作者时只留用途
    who = []
    if m.get('lyricist'):
        who.append('%s 词' % m['lyricist'])
    if m.get('composer'):
        who.append('%s 曲' % m['composer'])
    sub = (' · '.join(who) + ' &nbsp;|&nbsp; ' if who else '') + '课堂跟唱 · 演唱动态谱'

    audio = m.get('audio', '')

    # 底图内嵌：meta.background 指向本地图片时换成 data URI，拷到别的电脑也不会丢背景
    bg = m.get('background') or ''
    if bg and not bg.startswith('data:'):
        p = os.path.join(HERE, bg)
        if os.path.isfile(p):
            if inline:
                m['background'] = data_uri(p)
        elif inline:
            print('  ! 底图 %s 不在本目录，背景会缺失' % bg)

    # 音频内嵌：单文件版把 mp3 也塞进 <audio>，班级电脑只拷一个 html 就能出声
    audio_src = audio
    if inline and audio:
        p = os.path.join(HERE, audio)
        if os.path.isfile(p):
            audio_src = data_uri(p)
        else:
            print('  ! 音频 %s 不在本目录，页面会没有声音' % audio)

    js = json.dumps(d, ensure_ascii=False, separators=(',', ':'))

    out = (tpl
           .replace('__TITLE__', html.escape(m['title']))
           .replace('__SUB__', sub)
           .replace('__AUDIO__', html.escape(audio_src, quote=True))
           .replace('/*__SCORE_JSON__*/ null', js))

    open(OUT, 'w', encoding='utf-8').write(out)

    # 自检：音频是否到位、时长是否够唱完
    spb = 60.0 / m['tempo']
    end = m['audioOffset'] + (max(n['startBeat'] + n['durBeats'] for n in d['notes'])) * spb
    if audio and os.path.isfile(os.path.join(HERE, audio)):
        dur = probe_duration(os.path.join(HERE, audio))
        if dur:
            print('  音频 %.1fs，谱面唱到 %.1fs (@%g BPM, 起唱 %.2fs)'
                  % (dur, end, m['tempo'], m['audioOffset']))
            if dur < end - 0.5:
                print('  ! 音频比谱面短 %.1fs，末尾会被截断' % (end - dur))

    kb = len(out.encode('utf-8')) / 1024
    if not inline:
        note = '，底图/音频仍为外链'
    else:
        got = []
        if str(m.get('background', '')).startswith('data:'):
            got.append('底图')
        if audio_src.startswith('data:'):
            got.append('音频')
        note = ('，%s已内嵌，单个文件拷到任何电脑双击即可离线播放' % '+'.join(got)) if got \
            else '，未内嵌底图/音频（文件缺失）'
    print('✓ 已生成 %s（%.1f MB%s）' % (OUT, kb / 1024, note))


if __name__ == '__main__':
    main()
