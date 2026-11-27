#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无头浏览器版面体检：把动态谱跑一遍，量出所有会露馅的地方。

检什么：
  · 舞台   音块尺寸、歌词与音块/歌词互相是否压盖、歌词是否被谱面上下沿切掉
  · 简谱   每一句的数字/减时线/低音点/歌词是否超出面板、歌词是否压住数字
  · 精灵   全曲逐拍扫一遍，跳动的音符有没有冲出谱面上沿、有没有算出 NaN
  · 运行   全程有没有 JS 报错

用法：
    python3 check_layout.py index.html
    python3 check_layout.py index.html --chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    python3 check_layout.py index.html --json

退出码：0 全通过；1 有需要修的问题（详情会打印出来）。
原理：把 index.html 复制到临时目录，注入一段探针（把 rAF 换成 setTimeout、
      用可控时钟顶替音频 currentTime），用 Chrome headless --dump-dom 取回结果。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
]

# 注入到 <head> 最前面的补丁：headless 里 rAF 不一定跑，且音频时钟要能人为拖动
SHIM = """<script>
window.requestAnimationFrame = function(cb){ return setTimeout(function(){ cb(performance.now()); }, 16); };
window.__t = 0; window.__errs = [];
window.onerror = function(m, s, l){ window.__errs.push(m + ' @' + l); };
Object.defineProperty(HTMLMediaElement.prototype, 'currentTime',
  { configurable: true, get: function(){ return window.__t; }, set: function(v){ window.__t = v; } });
HTMLMediaElement.prototype.play = function(){ return Promise.resolve(); };
</script>"""

PROBE = """<script>
(function(){
  var RES = { err: [], stage: {}, lines: [], sprite: {}, ok: true };
  var f = document.querySelector('#frame');
  if (!f) { RES.fatal = 'no #frame'; document.title = JSON.stringify(RES); return; }
  var s = (new DOMMatrixReadOnly(getComputedStyle(f).transform)).a || 1;
  var fr = f.getBoundingClientRect();
  function R(el){ var b = el.getBoundingClientRect();
    return { t:(b.top-fr.top)/s, b:(b.bottom-fr.top)/s, l:(b.left-fr.left)/s, r:(b.right-fr.left)/s,
             w:b.width/s, h:b.height/s }; }
  function ov(a,b){ var ox=Math.min(a.r,b.r)-Math.max(a.l,b.l), oy=Math.min(a.b,b.b)-Math.max(a.t,b.t);
    return (ox>0.6 && oy>0.6) ? Math.min(ox,oy) : 0; }

  function scanSprite(done){
    var SPB = 60/SCORE.meta.tempo, OFF = SCORE.meta.audioOffset || 0;
    var INTRO = SCORE.meta.introBeats || 0;
    var end = 0; SCORE.notes.forEach(function(n){ end = Math.max(end, n.startBeat + n.durBeats); });
    var sun = document.querySelector('#sun');
    var minTop = 1e9, maxTop = -1e9, nan = 0, frames = 0;
    var b = -INTRO, tick = 0, MAXT = 900;
    document.querySelector('#btnPlay').click();
    var id = setInterval(function(){
      b += 0.3; window.__t = OFF + b*SPB; tick++;
      var t = parseFloat(sun.style.top);
      if (!isFinite(t)) nan++; else { if(t<minTop) minTop=t; if(t>maxTop) maxTop=t; frames++; }
      if (b > end + 2 || tick > MAXT){
        clearInterval(id);
        document.querySelector('#btnPlay').click();
        RES.sprite = { ticks: tick, frames: frames, nan: nan,
                       minTop: +minTop.toFixed(1), maxTop: +maxTop.toFixed(1),
                       vh: +document.querySelector('.viewport').getBoundingClientRect().height/s };
        done();
      }
    }, 18);
  }

  function measure(){
    // ---------- 舞台 ----------
    var vp = R(document.querySelector('.viewport'));
    var blks = [].slice.call(document.querySelectorAll('.blk:not(.rest)')).map(function(e){
      return { i:+e.dataset.i, box:R(e) }; });
    var lyrs = [].slice.call(document.querySelectorAll('.lyr')).map(function(e){
      return { i:+e.dataset.i, box:R(e) }; });
    var hits = [], worst = 0;
    lyrs.forEach(function(L){
      blks.forEach(function(B){
        if (L.i === B.i) return;
        var o = ov(L.box, B.box);
        if (o > 0.6) { worst = Math.max(worst, o);
          if (hits.length < 5) hits.push({ what:'歌词压音块', i:L.i, overlap:+o.toFixed(1) }); }
      });
    });
    var lyl = 0;
    lyrs.forEach(function(A,x){ lyrs.slice(x+1).forEach(function(B){ if (ov(A.box,B.box) > 0.6) lyl++; }); });
    var clip = lyrs.filter(function(L){ return L.box.b > vp.b+0.5 || L.box.t < vp.t-0.5; }).length;
    var sizes = {};
    blks.forEach(function(b){ var k = Math.round(b.box.h); sizes[k] = (sizes[k]||0)+1; });
    RES.stage = {
      vpW: +vp.w.toFixed(0), vpH: +vp.h.toFixed(0),
      blocks: blks.length, lyrics: lyrs.length,
      blockSizes: sizes, lyricBlkHits: hits.length, worstOverlap: +worst.toFixed(1),
      lyricLyricHits: lyl, lyricClipped: clip,
      minBlock: Math.min.apply(null, blks.map(function(b){ return b.box.h; })),
      detail: hits
    };
    if (hits.length) RES.ok = false;
    if (lyl || clip) RES.ok = false;

    // ---------- 简谱（逐句翻） ----------
    var panelEl = document.querySelector('.jianpu');
    var panel = R(panelEl);
    var nLine = (SCORE.sections || []).length || 4;
    var segs = document.querySelectorAll('[data-seg]');
    for (var i = 0; i < nLine; i++){
      if (segs.length > i+1) segs[i+1].click();
      else document.querySelector('#nextLine').click();
      var line = document.querySelector('.jp-line');
      if (!line) continue;
      var els = [].slice.call(line.querySelectorAll('.jp-n b, .jp-rest, .jp-lyr, .jp-beam'));
      var boxes = els.map(function(e){
        var tag = e.tagName;
        var cls = e.getAttribute('class') || '';
        return { tag:tag, cls:cls, box:R(e) };
      });
      var overflow = 0, ovBot = 0;
      boxes.forEach(function(o){
        if (o.box.b > panel.b - 1) { overflow++; ovBot = Math.max(ovBot, o.box.b - panel.b); }
        if (o.box.r > panel.r - 2) overflow++;
      });
      var digits = boxes.filter(function(o){ return o.tag === 'B' || o.cls.indexOf('jp-rest') >= 0; });
      var beams  = boxes.filter(function(o){ return o.cls.indexOf('jp-beam') >= 0; });
      var lyric  = boxes.filter(function(o){ return o.cls.indexOf('jp-lyr') >= 0; });
      var lhits = [];
      lyric.forEach(function(L){
        digits.forEach(function(D){ var o = ov(L.box, D.box);
          if (o > 0.6 && lhits.length < 5) lhits.push({ what:'歌词压数字', overlap:+o.toFixed(1) }); });
        beams.forEach(function(D){ var o = ov(L.box, D.box);
          if (o > 0.6 && lhits.length < 5) lhits.push({ what:'歌词压减时线', overlap:+o.toFixed(1) }); });
      });
      var maxBot = Math.max.apply(null, boxes.map(function(o){ return o.box.b; }));
      RES.lines.push({ line:i+1, count:els.length, overflow:overflow, ovBot:+ovBot.toFixed(1),
                       lyricHits:lhits.length, maxBottom:+maxBot.toFixed(1),
                       panelBottom:+panel.b.toFixed(1), detail:lhits });
      if (overflow || lhits.length) RES.ok = false;
    }
    RES.meta = { scale:+s.toFixed(3) };
    RES.err = window.__errs.slice(0, 6);
    if (RES.err.length) RES.ok = false;
    if (RES.sprite && (RES.sprite.nan > 0 || RES.sprite.minTop < 0)) RES.ok = false;
    document.title = JSON.stringify(RES);
  }

  if (document.readyState === 'complete') setTimeout(function(){ scanSprite(measure); }, 250);
  else window.addEventListener('load', function(){ setTimeout(function(){ scanSprite(measure); }, 250); });
})();
</script>"""


def find_chrome(explicit=None):
    if explicit:
        return explicit if os.path.exists(explicit) else None
    env = os.environ.get('CHROME')
    if env and os.path.exists(env):
        return env
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    for name in ('google-chrome', 'chromium', 'chrome', 'msedge'):
        p = shutil.which(name)
        if p:
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('html', help='打包好的 index.html')
    ap.add_argument('--chrome', default=None, help='Chrome/Edge 可执行文件路径')
    ap.add_argument('--json', action='store_true', help='直接打印原始 JSON')
    a = ap.parse_args()

    src = os.path.abspath(a.html)
    if not os.path.isfile(src):
        sys.exit('✗ 找不到 %s' % src)
    chrome = find_chrome(a.chrome)
    if not chrome:
        sys.exit('✗ 没找到 Chrome / Edge，可用 --chrome 指定路径')

    html = open(src, encoding='utf-8').read()
    if 'id="frame"' not in html:
        sys.exit('✗ 这不像动态谱页面（缺 #frame）')
    probe = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">' + SHIM, 1)
    if SHIM not in probe:                        # 模板没写这个 meta 时退而求其次
        probe = probe.replace('<head>', '<head>' + SHIM, 1)
    probe = probe.replace('</body>', PROBE + '</body>')

    tmp = tempfile.mkdtemp(prefix='scorecheck-')
    try:
        # 外链版（build.py --link）也能查版面：把同级目录里的素材一起带过去
        base = os.path.dirname(src)
        for f in os.listdir(base):
            p = os.path.join(base, f)
            if os.path.isfile(p) and f != os.path.basename(src):
                try:
                    shutil.copy2(p, tmp)
                except OSError:
                    pass
        page = os.path.join(tmp, 'probe.html')
        open(page, 'w', encoding='utf-8').write(probe)
        cmd = [chrome, '--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
               '--window-size=1280,720', '--virtual-time-budget=25000',
               '--dump-dom', 'file://' + page]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        m = re.search(r'<title>(.*?)</title>', r.stdout, re.S)
        if not m:
            sys.exit('✗ 页面没跑起来（没有拿到结果），可先手动双击打开看看控制台')
        raw = (m.group(1).replace('&amp;', '&').replace('&lt;', '<')
               .replace('&gt;', '>').replace('&quot;', '"'))
        res = json.loads(raw)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res.get('ok') else 1

    print('版面体检：%s' % os.path.basename(src))
    st = res.get('stage', {})
    print('  舞台 %d×%d，音块 %d 个（最小 %.0fpx，尺寸分布 %s）／歌词 %d 字'
          % (st.get('vpW', 0), st.get('vpH', 0), st.get('blocks', 0), st.get('minBlock', 0),
             st.get('blockSizes', {}), st.get('lyrics', 0)))
    line1 = []
    line1.append('歌词压音块 %d 处（最深 %.1fpx）' % (st.get('lyricBlkHits', 0), st.get('worstOverlap', 0)))
    line1.append('歌词互相压 %d 处' % st.get('lyricLyricHits', 0))
    line1.append('歌词出界 %d 处' % st.get('lyricClipped', 0))
    print('    ' + '，'.join(line1))
    for d in st.get('detail', []):
        print('    ! %s：第 %s 个音，重叠 %.1fpx' % (d['what'], d['i'], d['overlap']))

    for L in res.get('lines', []):
        flag = '✓' if not (L['overflow'] or L['lyricHits']) else '✗'
        print('  简谱第 %d 句 %s  %d 个元素，越界 %d，歌词压字 %d（最低点 %.0f / 面板 %.0f）'
              % (L['line'], flag, L['count'], L['overflow'], L['lyricHits'],
                 L['maxBottom'], L['panelBottom']))
        for d in L.get('detail', []):
            print('    ! %s，重叠 %.1fpx' % (d['what'], d['overlap']))

    sp = res.get('sprite', {})
    if sp:
        okS = sp.get('nan', 0) == 0 and sp.get('minTop', 0) >= 0
        print('  精灵 全曲 %d 帧：最高 %.1fpx（谱面上沿 0）%s，NaN %d 次'
              % (sp.get('frames', 0), sp.get('minTop', 0), '✓' if okS else '✗（冲出去了）',
                 sp.get('nan', 0)))
    err = res.get('err') or []
    print('  JS 报错：%s' % ('无' if not err else '；'.join(err)))
    print('\n%s' % ('✓ 全部通过' if res.get('ok') else '✗ 有问题，按上面标注的位置改 score.template.html'))
    return 0 if res.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
