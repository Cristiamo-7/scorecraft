# scorecraft · 音块动态谱工坊

把「教材谱例 + 范唱录音」做成一份**可投屏、音画同步的课堂动态谱**，最后压成**一个可以离线双击打开的 HTML**。

给音乐老师用：谱面随范唱滚动，一个金色音符踩着拍点从一个音块跳到下一个音块，块下逐字歌词，底部简谱同步标红。

![style](https://img.shields.io/badge/format-single--file%20HTML-informational) ![offline](https://img.shields.io/badge/offline-yes-success) ![fonts](https://img.shields.io/badge/fonts-SIL%20OFL%201.1-blue)

## 它长什么样

- **左侧音级轴**：do/re/mi 圆角卡片，当前音放大发光
- **彩色音块**：短音正圆、长音胶囊，三套形状（bubble / solid / jelly）× 四套低饱和配色
- **跳动音符**：随旋律上行跳跃、下行滑落，起跳拉长、落地压扁回弹，原地留残影
- **逐字歌词**：贴在各自音块正下方，唱到哪个字哪个字放大变色
- **简谱同步面板**：小节线、成组减时线、高低音点、一字多音连音弧，当前音实时标红
- **课堂功能**：前奏倒计时、选段循环、慢练倍速、同步微调、翻句

## 安装

把整个目录放到用户级技能目录：

```bash
git clone <this-repo> ~/.workbuddy/skills/scorecraft
```

或直接复制目录到 `~/.workbuddy/skills/scorecraft`。之后在对话里说「做一份动态谱」即可触发。

## 快速开始

```bash
# 1. 开工作目录（模板、脚本、字体、谱例骨架一次放好）
python3 ~/.workbuddy/skills/scorecraft/scripts/new_project.py ~/Downloads/小星星动态谱 --title "小星星"

cd ~/Downloads/小星星动态谱

# 2. 逐音录谱：编辑 score.json（字段见 references/schema.md）

# 3. 对拍：自动测速度与起唱位置
cp 范唱.mp3 ./范唱.mp3
python3 align.py            # 先看报告
python3 align.py --write    # 认可后写回 tempo / audioOffset

# 4. 切字体子集 + 打包单文件
python3 make_font.py
python3 build.py            # 出 index.html，内置底图与音频（约 4MB）

# 5. 版面体检
python3 ~/.workbuddy/skills/scorecraft/scripts/check_layout.py index.html
```

课上只需要拷 `index.html` 一个文件。

## 目录结构

```
scorecraft/
├── SKILL.md                     # 技能说明：工作流、10 条硬规矩、验收判读、故障表
├── scripts/
│   ├── new_project.py           # 开工作目录
│   ├── align.py                 # 音频对拍（chroma + 音高一致率）
│   ├── make_font.py             # 按用字切字体子集并 base64 内嵌
│   ├── build.py                 # 打包单文件 HTML（默认内嵌底图+音频，--link 出外链版）
│   └── check_layout.py          # 无头浏览器版面体检，退出码 0/1
├── assets/
│   ├── template/score.template.html   # 页面模板：唯一样式与引擎来源
│   ├── fonts/                   # 站酷快乐体 + Baloo 2 + OFL 授权
│   └── example/score.json       # 完整真实谱例（64 音 / 4 句）
└── references/
    ├── schema.md                # score.json 字段速查
    ├── design-spec.md           # 尺寸常量、动画物理参数、改尺寸的三处联动
    └── user-guide-example.md    # 交付给老师的说明文样例
```

## 体检脚本在查什么

```bash
python3 scripts/check_layout.py index.html
```

注入 rAF 兼容层与可控时钟，用无头 Chrome 跑完全曲，报告：

- 歌词压音块 / 歌词互相压 / 歌词出界
- 简谱逐句越界、歌词压字
- 精灵冲出谱面上沿、NaN、JS 报错

全绿才交付。故意把字号撑爆时它会准确报出越界位置，退出码 1。

## 硬规矩（摘）

1. 音频 `currentTime` 是唯一时钟，动画只读它
2. 不手改 `index.html`，改模板或 `score.json` 后重新 `build.py`
3. 休止 = **停住**，不是掉下去
4. 同一音级行的歌词共用一条基线
5. 简谱只用 `--dig-h` 一个变量联动
6. 尺寸按「后排看得清」定，动完必须重跑体检
7. 交付必须单文件离线（字体、底图、音频全部内嵌）

## 说明

- `assets/fonts/` 内字体遵循 **SIL Open Font License 1.1**，见 `assets/fonts/OFL.txt`。
- `assets/example/score.json` 与 `references/user-guide-example.md` 是课堂实践产物，仅作录谱参考，相关词曲著作权归原作者。
