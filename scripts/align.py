#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从音频自动测出「速度」和「起唱位置」，写回 score.json。

    python3 align.py            # 只报告，不改文件
    python3 align.py --write    # 把结果写进 score.json（之后跑 build.py 打包）

原理：带通 250~1000Hz 提取人声旋律基频 → 找「音高发生变化的点」（这些点必然
      对应某个音符的攻击时刻）→ 用谱面的音高变化点去匹配，全局扫描速度与偏移，
      再对匹配上的点做最小二乘精修。chroma 对齐只作为交叉验证与兜底。
"""
import json, os, re, subprocess, sys, tempfile, wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_SEMI = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6,
            'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
DEG_SEMI = [0, 2, 4, 5, 7, 9, 11]


# ------------------------------------------------------------------ 音频
def load_wav(path):
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
    try:
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-i', path, '-ac', '1', '-ar', '22050', '-f', 'wav', tmp],
                       check=True, timeout=180)
    except FileNotFoundError:
        sys.exit('✗ 需要 ffmpeg（brew install ffmpeg）')
    except subprocess.CalledProcessError:
        sys.exit('✗ 音频解码失败：%s' % path)
    w = wave.open(tmp)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close(); os.unlink(tmp)
    return x.astype(np.float32) / 32768.0, sr


def f0_track(x, sr, hop=256, win=1024):
    """250~1000Hz 带通 + 自相关，得到基频轨迹（Hz，无声为 0）。"""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    X[(f < 250) | (f > 1000)] = 0
    y = np.fft.irfft(X, len(x)).astype(np.float32)
    n = max(0, (len(y) - win) // hop)
    f0 = np.zeros(n); amp = np.zeros(n)
    lo, hi = int(sr / 1000), int(sr / 240)
    for i in range(n):
        seg = y[i * hop:i * hop + win]
        amp[i] = np.sqrt((seg ** 2).mean())
        s = seg * np.hanning(win)
        ac = np.correlate(s, s, 'full')[win - 1:]
        ac /= (ac[0] + 1e-9)
        sl = ac[lo:hi]
        j = int(np.argmax(sl))
        if sl[j] > 0.30:
            a, b, c = sl[max(0, j - 1)], sl[j], sl[min(len(sl) - 1, j + 1)]
            f0[i] = sr / (lo + j + 0.5 * (a - c) / (a - 2 * b + c + 1e-12))
    times = np.arange(n) * hop / sr
    return times, f0, amp


def pitch_change_onsets(times, f0, amp, min_gap=0.12, rel_amp=0.05):
    """音高跳变的时刻：每个都对应一个音符攻击点。"""
    midi = np.where(f0 > 0, 69 + 12 * np.log2(np.maximum(f0, 1e-6) / 440), np.nan)
    q = np.round(midi)
    sm = q.copy()
    for i in range(len(q)):                      # 3 帧中值，压掉颤音抖动
        s = q[max(0, i - 2):i + 3]
        s = s[~np.isnan(s)]
        sm[i] = np.median(s) if len(s) else np.nan
    thr = amp.max() * rel_amp
    out = []
    for i in range(1, len(sm)):
        if np.isnan(sm[i]) or amp[i] < thr:
            continue
        if np.isnan(sm[i - 1]) or abs(sm[i] - sm[i - 1]) >= 1:
            if not out or times[i] - out[-1] > min_gap:
                out.append(times[i])
    return np.array(out)


def chroma_feats(x, sr, hop=256, win=2048):
    n = max(0, (len(x) - win) // hop)
    idx = np.arange(n)[:, None] * hop + np.arange(win)[None, :]
    S = np.abs(np.fft.rfft(x[idx] * np.hanning(win)[None, :], axis=1))
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    band = (freqs > 160) & (freqs < 2400)
    pcs = np.round(69 + 12 * np.log2(np.maximum(freqs[band], 1e-9) / 440)).astype(int) % 12
    w = S[:, band] * (freqs[band] ** -0.5)
    C = np.zeros((n, 12))
    for pc in range(12):
        C[:, pc] = w[:, pcs == pc].sum(axis=1)
    C /= (C.sum(axis=1, keepdims=True) + 1e-9)
    return C, np.vstack([np.zeros((1, 12)), np.cumsum(C, axis=0)]), np.arange(n) * hop / sr


# ------------------------------------------------------------------ 谱面
def score_events(score):
    """返回 [(pc, startBeat, durBeats)] 与「音高变化点」的 beat 列表。"""
    key = score['meta'].get('key', 'C').strip()
    base = KEY_SEMI.get(key[:2] if key[:2] in KEY_SEMI else key[:1], 0)
    pcs, changes, prev = [], [], None
    for n in score['notes']:
        if n['degree'] == 0:
            prev = None
            continue
        pc = (base + DEG_SEMI[n['degree'] - 1] + 12 * n.get('octave', 0)) % 12
        pcs.append((pc, float(n['startBeat']), float(n['durBeats'])))
        cur = (n['degree'], n.get('octave', 0))
        if prev is not None and cur != prev:
            changes.append(float(n['startBeat']))
        prev = cur
    return pcs, np.array(changes)


def g_lookup(chg, dur, dt=0.001):
    """g(u) = u 到最近音高变化点的距离，预计算成采样表。"""
    grid = np.arange(0, dur + 0.5, dt)
    g = np.full(len(grid), 9.9, dtype=np.float32)
    for c in chg:
        lo, hi = max(0, int((c - 0.4) / dt)), min(len(grid), int((c + 0.4) / dt) + 2)
        np.minimum(g[lo:hi], np.abs(grid[lo:hi] - c), out=g[lo:hi])
    return g, dt


def scan(g, dt, changes, dur, bpms, off_step=0.01, tol=0.06, topn=40):
    """每个速度取最佳偏移，返回命中数最高的若干候选（可能含错拍/前奏假解）。"""
    out = []
    max_beat = float(changes.max())
    for bpm in bpms:
        spb = 60.0 / bpm
        hi = dur - max_beat * spb - 0.05
        if hi <= 0:
            continue
        offs = np.arange(0.0, hi, off_step)
        u = offs[:, None] + changes[None, :] * spb
        dd = g[np.clip((u / dt).astype(int), 0, len(g) - 1)]
        hit = (dd < tol).sum(axis=1)
        for k in np.argsort(hit)[::-1][:3]:
            out.append((int(hit[k]), float(bpm), float(offs[k]), float(np.median(dd[k]))))
    out.sort(key=lambda r: -r[0])
    keep = []
    for r in out:                       # 抑制同源相邻解
        if all(abs(r[1] - q[1]) > 0.6 or abs(r[2] - q[2]) > 0.25 for q in keep):
            keep.append(r)
        if len(keep) >= topn:
            break
    return keep


def pitch_score(midi_q, dt_f, pcs, spb, off, shift):
    """在谱面每个音的持续段里取音频基频，与应有音级比对，返回一致比例。"""
    ok = tot = 0
    for pc, b, d in pcs:
        t = off + (b + 0.35 * d) * spb
        i = int(t / dt_f)
        if i < 0 or i >= len(midi_q):
            continue
        m = midi_q[i]
        if np.isnan(m):
            continue
        tot += 1
        if (int(m) - shift) % 12 == pc:
            ok += 1
    return ok / tot if tot else 0.0


def refine_ls(changes, chg, spb, off, tol=0.12):
    exp = off + changes * spb
    j = np.abs(chg[None, :] - exp[:, None]).argmin(axis=1)
    r = chg[j] - exp
    m = np.abs(r) < tol
    if m.sum() < 6:
        return None
    for _ in range(4):
        B, T = changes[m], chg[j][m]
        A = np.vstack([B, np.ones(len(B))]).T
        sol, *_ = np.linalg.lstsq(A, T, rcond=None)
        r = T - (sol[0] * B + sol[1])
        keep = np.abs(r) < max(0.05, 2.5 * np.median(np.abs(r - np.median(r))))
        if keep.sum() < 6:
            break
        m[np.where(m)[0][~keep]] = False
    B, T = changes[m], chg[j][m]
    A = np.vstack([B, np.ones(len(B))]).T
    sol, *_ = np.linalg.lstsq(A, T, rcond=None)
    rms = float(np.sqrt(np.mean((T - (sol[0] * B + sol[1])) ** 2)))
    return float(sol[0]), float(sol[1]), int(m.sum()), rms


def chroma_fit(pcs, Cs, hop_s, spb, off):
    tot, cnt = 0.0, 0
    for pc, b, d in pcs:
        t0, t1 = off + b * spb, off + (b + d) * spb
        i0, i1 = int((t0 + (t1 - t0) * 0.2) / hop_s), int((t1 - (t1 - t0) * 0.25) / hop_s)
        if i1 <= i0 or i0 < 0 or i1 >= len(Cs):
            continue
        tot += (Cs[i1, pc] - Cs[i0, pc]) / (i1 - i0); cnt += 1
    return tot / cnt if cnt else 0.0


# ------------------------------------------------------------------ 主流程
def main():
    args = sys.argv[1:]
    write = '--write' in args
    args = [a for a in args if a != '--write']
    force = {}
    for k in ('--tempo', '--offset'):
        if k in args:
            i = args.index(k)
            force[k] = float(args[i + 1]); del args[i:i + 2]

    sj = next((a for a in args if a.endswith('.json')), os.path.join(HERE, 'score.json'))
    score = json.load(open(sj, encoding='utf-8'))
    rest = [a for a in args if not a.endswith('.json')]
    audio = rest[0] if rest else os.path.join(os.path.dirname(os.path.abspath(sj)),
                                              score['meta'].get('audio', ''))
    if not os.path.isfile(audio):
        sys.exit('✗ 找不到音频：%s' % audio)

    print('音频：%s' % os.path.basename(audio))
    x, sr = load_wav(audio)
    dur = len(x) / sr
    print('时长：%.2fs' % dur)

    pcs, changes = score_events(score)
    beats = max(n['startBeat'] + n['durBeats'] for n in score['notes'])
    print('谱面：%d 个音、%d 个音高变化点、共 %.0f 拍' % (len(pcs), len(changes), beats))

    shift = 0
    if '--tempo' in force and '--offset' in force:
        spb, off, src = 60.0 / force['--tempo'], force['--offset'], '人工指定'
        nm = None
    else:
        times, f0, amp = f0_track(x, sr)
        chg = pitch_change_onsets(times, f0, amp)
        print('检出音高变化点：%d 个' % len(chg))
        if len(chg) < 12 or len(changes) < 6:
            sys.exit('✗ 音高变化点太少，改用 --tempo/--offset 手工指定')

        C, Cs, ctimes = chroma_feats(x, sr)
        hop_c = ctimes[1] - ctimes[0]
        g, dt = g_lookup(chg, dur)
        cands = scan(g, dt, changes, dur, np.arange(40, 200.5, 0.5), off_step=0.02)
        if not cands:
            sys.exit('✗ 扫描失败，请用 --tempo/--offset 手工指定')

        # 用「那个时刻唱的是不是这个音」排除前奏/错拍假解
        midi = np.where(f0 > 0, 69 + 12 * np.log2(np.maximum(f0, 1e-6) / 440), np.nan)
        midi_q = np.round(midi)
        dt_f = times[1] - times[0]
        # 全局移调：谱面音级分布 × 音频 chroma 分布，最吻合的旋转量
        hs = np.zeros(12)
        for pc, _, d in pcs:
            hs[pc] += d
        ha = C.sum(axis=0)
        shift = int(np.argmax([np.dot(ha, np.roll(hs, k)) for k in range(12)]))

        best = None
        for hit_c, bpm_c, off_c, _md in cands[:60]:
            spb_c = 60.0 / bpm_c
            shifted = [((pc + shift) % 12, b, d) for pc, b, d in pcs]
            cf = chroma_fit(shifted, Cs, hop_c, spb_c, off_c)
            ps = pitch_score(midi_q, dt_f, pcs, spb_c, off_c, shift)
            sc = cf + 0.5 * ps + 0.002 * hit_c     # chroma 为主，音高一致为辅
            if best is None or sc > best[0]:
                best = (sc, bpm_c, off_c, shift, ps, cf, hit_c)
        _, bpm, off, shift, ps, cf, hit = best
        print('复核：chroma %.3f、音高一致 %.0f%%、移调 %+d 半音、初筛命中 %d/%d'
              % (cf, ps * 100, shift, hit, len(changes)))

        r = refine_ls(changes, chg, 60.0 / bpm, off)
        if r:
            spb, off, nm, rms = r
            src = '音高变化点最小二乘'
            print('精修：%d 个点参与，残差 RMS %.0fms，初筛命中 %d/%d'
                  % (nm, rms * 1000, hit, len(changes)))
        else:
            spb, src = 60.0 / bpm, '全局扫描'
            print('精修：匹配点不足，沿用扫描结果（命中 %d/%d）' % (hit, len(changes)))

    bpm = 60.0 / spb

    # 交叉验证：chroma 对齐度（随机基准 1/12 ≈ 0.083）
    C, Cs, ctimes = chroma_feats(x, sr)
    f = chroma_fit([((pc + shift) % 12, b, d) for pc, b, d in pcs],
                   Cs, ctimes[1] - ctimes[0], spb, off)

    meta = score['meta']
    old = meta.get('tempo'), meta.get('audioOffset')
    meta['tempo'] = round(bpm, 2)
    meta['audioOffset'] = round(off, 3)
    meta['introBeats'] = int(round(off / spb))

    print('')
    print('  速度   %.2f BPM（每拍 %.4fs）  来源：%s' % (bpm, spb, src))
    print('  起唱   beat 0 = %.2fs，前奏 ≈ %d 拍' % (off, meta['introBeats']))
    print('  唱完   %.1fs' % (off + beats * spb))
    print('  校验   chroma 对齐度 %.3f（随机 0.083）%s'
          % (f, '' if f > 0.2 else '  ← 偏低，建议人工复核'))

    if old[0] is not None:
        d_t, d_o = bpm - old[0], off - old[1]
        if abs(d_t) > 0.3 or abs(d_o) > 0.05:
            drift = beats * 60.0 * abs(1.0 / bpm - 1.0 / old[0])
            print('  变化   %.2f→%.2f BPM，%.2fs→%.2fs（到曲末累计差 %.2fs）'
                  % (old[0], bpm, old[1], off, drift))
    if write:
        txt = open(sj, encoding='utf-8').read()
        for key, val in (('tempo', meta['tempo']),
                         ('audioOffset', meta['audioOffset']),
                         ('introBeats', meta['introBeats'])):
            txt, n = re.subn(r'("%s"\s*:\s*)-?[\d.]+' % key, r'\g<1>%s' % val, txt, count=1)
            if n == 0:
                print('  ! score.json 里没找到 %s 字段，请手工填入 %s' % (key, val))
        open(sj, 'w', encoding='utf-8').write(txt)
        print('  ✓ 已写回 %s（只改这三个数字，格式原样保留）' % os.path.basename(sj))
    else:
        print('  （未写回；确认无误后加 --write）')


if __name__ == '__main__':
    main()
