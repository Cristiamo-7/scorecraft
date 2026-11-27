#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把页面用到的字，从两套开源字体里切出来，内嵌进 score.template.html。

为什么要切：中文字库整包 1.5MB，内嵌进 HTML 太重；而本页实际只用到几百个字。
切完两三千字只要几十 KB，双击打开、拷到断网的教室电脑都不会掉字。

用法：
    python3 make_font.py

换歌以后如果发现某个字显示成了系统字体，跑一次这个脚本就好。
依赖：pip install fonttools brotli
"""
import base64
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, 'score.template.html')
SCORE = os.path.join(HERE, 'score.json')
FONT_DIR = os.path.join(HERE, 'fonts')

KC_TTF = os.path.join(FONT_DIR, 'ZCOOLKuaiLe-Regular.ttf')
BL_TTF = os.path.join(FONT_DIR, 'Baloo2-Variable.ttf')

# 页面里固定的界面文案（按钮、提示）——不在 score.json 里，但必须能显示
UI_EXTRA = (
    '播放暂停重来全曲一二三四句速度同步形状气泡实心果冻配色柔和暖秋糖果年画'
    '图标背景还原全屏音符简谱同步第一二三四句前奏准备跟唱终尾奏全曲结束空格重播'
    '课堂跟唱演唱动态谱词曲行板深情地年画皮肤水墨'
    '0123456789=♩♪.-–—·|/：:，。、（）()×%'
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
)


def die(msg):
    print('✗ ' + msg)
    sys.exit(1)


def collect_chars():
    """score.json 里的歌词 + 模板里的中文 + 固定界面文案。"""
    import json
    chars = set(UI_EXTRA)
    if os.path.isfile(SCORE):
        d = json.load(open(SCORE, encoding='utf-8'))
        for n in d.get('notes', []):
            chars |= set(n.get('lyric') or '')
        for s in d.get('sections', []):
            chars |= set(s.get('label', '')) | set(s.get('text', ''))
        for k in ('title', 'lyricist', 'composer', 'tempoText', 'keyLabel'):
            chars |= set(str(d.get('meta', {}).get(k, '')))
    if os.path.isfile(TPL):
        t = strip_b64(open(TPL, encoding='utf-8').read())
        chars |= set(re.findall(r'[\u4e00-\u9fff]', t))
    return ''.join(sorted(c for c in chars if c.strip()))


def strip_b64(html):
    """去掉已内嵌的 base64，免得把 64 个字母当成"用到的字"。"""
    return re.sub(r'base64,[A-Za-z0-9+/=]+', 'base64,', html)


def subset(ttf, text, weight=None):
    from fontTools import subset as ftsubset
    from fontTools.ttLib import TTFont

    font = TTFont(ttf)
    if weight is not None:
        from fontTools.varLib.instancer import instantiateVariableFont
        font = instantiateVariableFont(font, {'wght': weight})

    opts = ftsubset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = ['*']
    opts.hinting = False
    opts.desubroutinize = True
    opts.name_IDs = ['*']
    opts.notdef_outline = True

    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    font = TTFont(buf)

    sub = ftsubset.Subsetter(options=opts)
    sub.populate(text=text)
    out = io.BytesIO()
    sub.subset(font)
    font.flavor = 'woff2'
    font.save(out)
    return out.getvalue()


def embed(html, family, b64):
    # 一直吃到右括号：不管上次留下的是 base64 还是占位符，都整体换掉
    pat = re.compile(r'(font-family:"%s"[^}]*?base64,)[^)]*' % family)
    if not pat.search(html):
        die('模板里找不到 %s 的 @font-face' % family)
    return pat.sub(lambda m: m.group(1) + b64, html, count=1)


def main():
    for p in (KC_TTF, BL_TTF):
        if not os.path.isfile(p):
            die('缺少字体源文件 %s' % p)
    try:
        import brotli  # noqa: F401
    except ImportError:
        die('缺少 brotli：先跑 pip install fonttools brotli')

    text = collect_chars()
    print('  需要内嵌的字：%d 个' % len(text))

    kc = subset(KC_TTF, text)
    bl = subset(BL_TTF, '0123456789=:/.-×♩♪G', weight=800)
    print('  站酷快乐体 %.1f KB / Baloo 数字 %.1f KB' % (len(kc) / 1024, len(bl) / 1024))

    html = open(TPL, encoding='utf-8').read()
    html = embed(html, 'Kuaile', base64.b64encode(kc).decode())
    html = embed(html, 'BalooNum', base64.b64encode(bl).decode())
    open(TPL, 'w', encoding='utf-8').write(html)
    print('✓ 已写回 %s（%.1f KB）' % (TPL, len(html) / 1024))


if __name__ == '__main__':
    main()
