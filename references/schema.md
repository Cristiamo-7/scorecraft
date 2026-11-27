# score.json 字段速查

一份谱例就是一个 JSON：`meta`（元信息）+ `notes`（音符）+ `slurs`（一字多音）+ `dynamics`（力度/速度记号）+ `sections`（分段）。全部拍数用**拍**（beat）计，不写秒；秒数由 `meta.tempo` 与 `meta.audioOffset` 换出来。

## meta

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | ✔ | 歌名，进 `<title>`、页头大标题 |
| `lyricist` / `composer` | | 词曲作者，显示在标题下方 |
| `key` / `keyLabel` | | `G` / `1=G`，右上角胶囊 |
| `timeSig` | | `[4,4]`，右上角胶囊固定显示 `4/4` |
| `tempo` | ✔ | BPM。**由 `align.py` 自动算出并写回**，不要手猜 |
| `tempoText` | | 如 `行板  深情地` |
| `audio` | ✔ | 音频文件名（相对工作目录）。单文件打包时会内嵌 |
| `audioOffset` | ✔ | 「第一个音唱出来的秒数」。由 `align.py` 写入 |
| `introBeats` | | 前奏有多少拍（决定前奏小节、倒计时、负拍区间）。align.py 会推算 |
| `offsetVersion` | | 改了 offset 就 +1，前端会丢弃旧的本地同步微调（localStorage 键含版本号） |
| `mode` | | `sing`（本模板只实现演唱模式） |
| `background` | | 底图文件名；留空则纯纸色。build.py 会把它转成 data URI 内嵌 |
| `skin` | | 默认音块形状：`bubble`（气泡，默认）/ `solid`（实心）/ `jelly`（果冻） |
| `palette` | | 默认配色：`soft`（柔和，默认）/ `autumn`（暖秋）/ `candy`（糖果）/ `nianhua`（年画） |

> `skin` / `palette` 只是**默认值**；课堂上点了按钮会存进 localStorage，下次打开按本机记忆，不再跟 meta 走。

## notes（按 startBeat 升序）

| 字段 | 必填 | 说明 |
|---|---|---|
| `degree` | ✔ | 简谱音级 1–7，`0` = 休止 |
| `octave` | ✔（可省=0） | 加/减八度。`+1` 显示上点、`-1` 显示下点；`0` 无点 |
| `startBeat` | ✔ | 起始拍，可含 0.5（八分）、0.25（十六分） |
| `durBeats` | ✔ | 时值（拍）。本曲只用了 0.5/1/2/3 |
| `lyric` | | 该音对应的**一个字**。一字多音时只在第一个音写，后面留空 |

排布铁律：

- **不能重叠**：`startBeat[n+1] >= startBeat[n] + durBeats[n]`。build.py 会检查并警告。
- **休止也是音符**：`degree:0` + 时值照写，占住拍位；舞台上不画块（只由下方简谱的 `0` 表达），精灵会**停在最后一个实音的高度**不动。
- 音高 = `67 + SEMI[degree] + 12*octave`（`1` 唱 G4 时为 67）。同一音高在舞台上共用一条横向音级行，行数 = 出现过的不同音高个数（本曲 9 行）。
- 八度点必须与 `octave` 一致：`degree` 相同但 `octave` 不同 → 是**两行**、两个不同的音级卡片。

## slurs（一字多音的连音弧）

```json
{ "startBeat": 2, "endBeat": 4, "kind": "melisma" }
```

- `kind` 固定 `melisma`；`[startBeat, endBeat)` 内**至少两个实音**才画。
- 弧线画在简谱该组**音符上方**（不贴、不压数字）；组里有高八度点时整条再抬高 6px。
- 只对落在同一句（16 拍）内的组生效。

## dynamics（力度 / 速度记号）

```json
{ "beat": 0, "text": "mp", "kind": "dyn" }
{ "beat": 32, "text": "渐慢", "kind": "tempo" }
```

画在谱面对应小节上沿；`kind` 只有 `dyn` 与 `tempo` 两种字号。

## sections（分段，同时决定简谱分页）

```json
{ "label": "第一句", "startBeat": 0, "endBeat": 16, "text": "去年我回去，你们刚穿新棉袍" }
```

- **每一段 = 简谱面板的一页**，也是「选段」按钮的一项。默认每段 16 拍（4 小节）。
- 段数决定右上角 `1 / N` 与翻页按钮；`text` 显示在屏幕右上的段落提示条。
- 段长必须与 `LINE_BEATS`（模板里默认 16）一致，否则简谱会串行。

## 完整最小样例

```json
{
  "meta": { "title": "小星星", "keyLabel": "1=C", "timeSig": [4,4], "tempo": 84,
            "audio": "范唱.mp3", "audioOffset": 0, "introBeats": 8,
            "background": "", "skin": "bubble", "palette": "soft" },
  "notes": [
    { "degree": 1, "octave": 0, "startBeat": 0, "durBeats": 1, "lyric": "一" },
    { "degree": 0, "octave": 0, "startBeat": 1, "durBeats": 1, "lyric": "" }
  ],
  "slurs": [], "dynamics": [], "sections": [
    { "label": "第一句", "startBeat": 0, "endBeat": 8, "text": "示例" }
  ]
}
```

`scripts/new_project.py` 生成的就是这个骨架（带 6 个音），直接改比从零写省事。
