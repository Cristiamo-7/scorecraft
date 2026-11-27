#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能自检：结构、占位符、谱例字段、脚本可编译。CI 与本地都能跑。

用法：
    python3 check_skill.py                 # 检查本脚本所在的 skill 目录
    python3 check_skill.py /path/to/skill  # 检查指定目录

退出码：0 全通过；1 有问题（逐条打印）。
和 check_layout.py 的分工：这个查「skill 本身是否完整」，那个查「生成的谱面是否有版面问题」。
"""
import json
import os
import py_compile
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

REQUIRED = [
    'SKILL.md',
    'README.md',
    'LICENSE',
    'assets/template/score.template.html',
    'assets/fonts/ZCOOLKuaiLe-Regular.ttf',
    'assets/fonts/Baloo2-Variable.ttf',
    'assets/fonts/OFL.txt',
    'assets/example/score.json',
    'references/schema.md',
    'references/design-spec.md',
    'references/user-guide-example.md',
    'scripts/new_project.py',
    'scripts/align.py',
    'scripts/make_font.py',
    'scripts/build.py',
    'scripts/check_layout.py',
    'scripts/check_skill.py',
    'scripts/make_silence.py',
]

# 模板必须保留的占位符（少一个就会把上一首歌的标题/音频带进新谱）
PLACEHOLDERS = ['__TITLE__', '__SUB__', '__AUDIO__', '__SCORE_JSON__']

# 模板里不允许再出现的硬编码内容（曾经写死过曲名，换歌就会显示错标题）
FORBIDDEN = ['西风的话', '廖辅叔', '黄自']

TEXT_EXT = ('.md', '.py', '.html', '.json', '.txt', '.yml', '.yaml', '.gitignore')

problems = []
notes = []


def fail(msg):
    problems.append(msg)


def read_text(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf'):
        fail('%s 带 UTF-8 BOM，某些编辑器会读出错位' % os.path.relpath(path, ROOT))
        raw = raw[3:]
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError as e:
        fail('%s 不是合法 UTF-8：%s' % (os.path.relpath(path, ROOT), e))
        return ''


def check_frontmatter():
    p = os.path.join(ROOT, 'SKILL.md')
    if not os.path.isfile(p):
        return
    txt = read_text(p)
    if not txt.startswith('---'):
        fail('SKILL.md 缺少 YAML frontmatter（--- 开头）')
        return
    end = txt.find('\n---', 3)
    if end < 0:
        fail('SKILL.md frontmatter 没有闭合的 ---')
        return
    head = txt[3:end]
    fields = {}
    for line in head.splitlines():
        if ':' in line and not line.startswith(' '):
            k, v = line.split(':', 1)
            fields[k.strip()] = v.strip()
    for k in ('name', 'description'):
        if not fields.get(k):
            fail('SKILL.md frontmatter 缺少 %s' % k)
    if fields.get('name') and fields['name'] != 'scorecraft':
        fail('SKILL.md name 应为 scorecraft，实际是 %s' % fields['name'])
    # description 是所有技能的总入口，太短说明触发词不够
    d = fields.get('description', '')
    if d and len(d) < 40:
        fail('SKILL.md description 太短（%d 字），触发词不足' % len(d))
    notes.append('SKILL.md：name=%s，description %d 字' % (fields.get('name'), len(d)))


def check_files():
    for rel in REQUIRED:
        if not os.path.isfile(os.path.join(ROOT, rel)):
            fail('缺少文件 %s' % rel)


def check_template():
    p = os.path.join(ROOT, 'assets/template/score.template.html')
    if not os.path.isfile(p):
        return
    txt = read_text(p)
    got = [ph for ph in PLACEHOLDERS if ph in txt]
    for ph in PLACEHOLDERS:
        if ph not in got:
            fail('模板缺少占位符 %s' % ph)
    for bad in FORBIDDEN:
        if bad in txt:
            fail('模板里残留硬编码内容「%s」，换歌会显示错信息' % bad)
    for need in ('id="frame"', 'id="sun"', 'id="btnPlay"', '#slurLayer'):
        if need not in txt:
            fail('模板缺少关键结构 %s（版面体检与播放都依赖它）' % need)
    notes.append('模板：占位符 %d/%d，%.0f KB'
                 % (len(got), len(PLACEHOLDERS), len(txt.encode()) / 1024))


def check_score():
    p = os.path.join(ROOT, 'assets/example/score.json')
    if not os.path.isfile(p):
        return
    try:
        d = json.loads(read_text(p))
    except Exception as e:
        fail('示例 score.json 不是合法 JSON：%s' % e)
        return
    m = d.get('meta', {})
    for k in ('title', 'tempo', 'audioOffset'):
        if k not in m:
            fail('示例谱例 meta 缺少 %s' % k)
    notes_d = d.get('notes') or []
    if not notes_d:
        fail('示例谱例没有 notes')
        return
    prev = -1e9
    for i, n in enumerate(notes_d):
        for k in ('degree', 'startBeat', 'durBeats'):
            if k not in n:
                fail('示例谱例第 %d 个音缺少 %s' % (i + 1, k))
        if not (0 <= n.get('degree', 0) <= 7):
            fail('示例谱例第 %d 个音 degree 越界' % (i + 1))
        if n.get('durBeats', 0) <= 0:
            fail('示例谱例第 %d 个音 durBeats 必须 > 0' % (i + 1))
        if n.get('startBeat', 0) < prev:
            fail('示例谱例第 %d 个音 startBeat 倒退（未按拍序排列）' % (i + 1))
        prev = n.get('startBeat', 0)
    # 音符不能重叠：重叠会让音块压在一起，视觉上一定出问题
    srt = sorted(notes_d, key=lambda n: n['startBeat'])
    for a, b in zip(srt, srt[1:]):
        if b['startBeat'] < a['startBeat'] + a['durBeats'] - 1e-6:
            fail('示例谱例 %.2f 拍处两个音重叠' % b['startBeat'])
            break
    beats = max(n['startBeat'] + n['durBeats'] for n in notes_d)
    secs = [s.get('label') for s in d.get('sections', [])]
    notes.append('示例谱例：%d 音 / %.0f 拍 / %d 句 / %d 字%s'
                 % (len(notes_d), beats, len(secs),
                    sum(1 for n in notes_d if n.get('lyric')),
                    '，含休止' if any(n['degree'] == 0 for n in notes_d) else ''))


def check_scripts():
    sdir = os.path.join(ROOT, 'scripts')
    if not os.path.isdir(sdir):
        return
    tmp = tempfile.mkdtemp(prefix='scorecraft-py-')
    ok = 0
    for f in sorted(os.listdir(sdir)):
        if not f.endswith('.py'):
            continue
        try:
            py_compile.compile(os.path.join(sdir, f),
                               cfile=os.path.join(tmp, f + 'c'), doraise=True)
            ok += 1
        except py_compile.PyCompileError as e:
            fail('脚本 %s 语法错误：%s' % (f, str(e).splitlines()[-1]))
    notes.append('脚本可编译：%d 个' % ok)


def check_encoding():
    bad = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules')]
        for f in files:
            if not f.lower().endswith(TEXT_EXT):
                continue
            p = os.path.join(base, f)
            try:
                open(p, encoding='utf-8').read()
            except (UnicodeDecodeError, IsADirectoryError):
                bad += 1
                fail('%s 不是合法 UTF-8' % os.path.relpath(p, ROOT))
    notes.append('文本文件编码：%s' % ('全部 UTF-8' if not bad else '%d 个异常' % bad))


def main():
    global ROOT
    ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE))
    if not os.path.isdir(ROOT):
        sys.exit('✗ 找不到目录 %s' % ROOT)

    print('技能自检：%s' % ROOT)
    check_files()
    check_frontmatter()
    check_template()
    check_score()
    check_scripts()
    check_encoding()

    for n in notes:
        print('  · ' + n)
    if problems:
        print('\n✗ 发现 %d 个问题：' % len(problems))
        for p in problems:
            print('  ! ' + p)
        return 1
    print('\n✓ 结构完整，占位符与示例谱例都正常')
    return 0


if __name__ == '__main__':
    sys.exit(main())
