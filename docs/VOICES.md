# 语音包与角色配音

项目内置 32 个精选语音预设，来自 20 个 Edge 基础音色，覆盖普通话、东北与陕西口音、粤语、台湾国语、美式/英式英语及日语。一个预设包括音色、语速、音高和试音文案。同一基础音色的不同语速会形成不同预设，不计为新增音色。目录源文件为 [`core/tts/voice_presets.json`](../core/tts/voice_presets.json)。

“温柔”“活力”“沉稳”是选角与韵律建议，不是情绪模型开关。Edge 可调整音色、语速和音高，不支持自定义 SSML 情绪标签；详见 [edge-tts 上游文档](https://github.com/rany2/edge-tts#custom-ssml)。

## 查看与试听

以下命令在项目根目录运行。合成需要已安装语音依赖：

```sh
sh plugin/skills/lemo-opuscar/scripts/setup.sh deps voice
```

查询本地预设目录不联网；加 `--json` 便于工具读取：

```sh
.venv/bin/python core/tts/tts_zh.py --list-presets
.venv/bin/python core/tts/tts_zh.py --list-presets --json
```

先生成一个预设，或一次生成全部试听：

```sh
.venv/bin/python core/tts/tts_zh.py --preview zh-warm-female --out-dir films/voice-preview
.venv/bin/python core/tts/tts_zh.py --preview all --out-dir films/voice-library
```

用浏览器打开输出目录中的 `index.html`，逐个播放比较。目录中还会生成 WAV、`dur.json` 和 `manifest.json`，保留声音参数及音频时长。合成使用 Microsoft 在线服务，会向其发送试音文本，无需单独 API Key。生成后的音频和试听页可在本机离线播放；这些预设本身不是离线模型包。

## 激情预设

在完整试听页搜索“激情”，可以连续比较 8 个预设。赛事冲刺和电竞快评适合紧跟动作，舞台开场、倒计时主持和现场助威适合带观众一起参与。热血预告的低音慢速给关键一句留出空间，赛前动员用更接近日常说话的速度凝聚注意力。粤语球评适合用粤语口吻报动作和比分。

冲线解说可以把动作分成三拍，“最后十米，追平了，冲线！”赛前动员可以先放稳一句，再给出指令，“抬头，看一眼你的队友。准备好了，我们一起上场！”需要让第二句踩在画面切点时，把它单独写成一条台词，在时间线上安排停顿。

## 预设目录

| ID | 名称 | 基础音色 | 语速 / 音高 |
|---|---|---|---|
| `zh-warm-female` | 温柔讲书女声 | `zh-CN-XiaoxiaoNeural` | `-15%` / `-1Hz` |
| `zh-standard-female` | 标准解说女声 | `zh-CN-XiaoxiaoNeural` | `+0%` / `+0Hz` |
| `zh-lively-female` | 活力解说女声 | `zh-CN-XiaoyiNeural` | `+8%` / `+0Hz` |
| `zh-story-female` | 轻柔童话女声 | `zh-CN-XiaoyiNeural` | `-8%` / `+0Hz` |
| `zh-youth-male` | 青年叙事男声 | `zh-CN-YunxiNeural` | `+0%` / `+0Hz` |
| `zh-explainer-male` | 活力科普男声 | `zh-CN-YunxiNeural` | `+8%` / `+0Hz` |
| `zh-documentary-male` | 沉稳纪录片男声 | `zh-CN-YunyangNeural` | `-10%` / `-2Hz` |
| `zh-news-male` | 标准播报男声 | `zh-CN-YunyangNeural` | `+0%` / `+0Hz` |
| `zh-dramatic-male` | 有力叙事男声 | `zh-CN-YunjianNeural` | `-3%` / `-2Hz` |
| `zh-child-male` | 童话少年男声 | `zh-CN-YunxiaNeural` | `-5%` / `+0Hz` |
| `zh-northeast-female` | 东北口音女声 | `zh-CN-liaoning-XiaobeiNeural` | `+0%` / `+0Hz` |
| `zh-shaanxi-female` | 陕西口音女声 | `zh-CN-shaanxi-XiaoniNeural` | `+0%` / `+0Hz` |
| `yue-warm-female` | 粤语亲切女声 | `zh-HK-HiuMaanNeural` | `-5%` / `+0Hz` |
| `yue-bright-female` | 粤语轻快女声 | `zh-HK-HiuGaaiNeural` | `+3%` / `+0Hz` |
| `yue-story-male` | 粤语讲述男声 | `zh-HK-WanLungNeural` | `-8%` / `+0Hz` |
| `zh-tw-warm-female` | 台湾国语女声 | `zh-TW-HsiaoChenNeural` | `-5%` / `+0Hz` |
| `zh-tw-soft-female` | 台湾国语慢叙女声 | `zh-TW-HsiaoYuNeural` | `-8%` / `+0Hz` |
| `zh-tw-male` | 台湾国语男声 | `zh-TW-YunJheNeural` | `-3%` / `+0Hz` |
| `en-us-female` | 美式英语女声 | `en-US-JennyNeural` | `-5%` / `+0Hz` |
| `en-us-male` | 美式英语男声 | `en-US-GuyNeural` | `-5%` / `+0Hz` |
| `en-gb-female` | 英式英语女声 | `en-GB-SoniaNeural` | `-5%` / `+0Hz` |
| `en-gb-male` | 英式英语男声 | `en-GB-RyanNeural` | `-5%` / `+0Hz` |
| `ja-female` | 日语女声 | `ja-JP-NanamiNeural` | `-5%` / `+0Hz` |
| `ja-male` | 日语男声 | `ja-JP-KeitaNeural` | `-5%` / `+0Hz` |
| `zh-sports-sprint-male` | 冲线解说男声 | `zh-CN-YunjianNeural` | `+22%` / `+5Hz` |
| `zh-stage-host-female` | 舞台开场女声 | `zh-CN-XiaoyiNeural` | `+12%` / `+6Hz` |
| `zh-trailer-male` | 热血预告男声 | `zh-CN-YunjianNeural` | `-7%` / `-5Hz` |
| `zh-rally-female` | 赛前动员女声 | `zh-CN-XiaoxiaoNeural` | `+5%` / `+3Hz` |
| `zh-esports-male` | 电竞快评男声 | `zh-CN-YunxiNeural` | `+18%` / `+4Hz` |
| `zh-countdown-male` | 倒计时主持男声 | `zh-CN-YunyangNeural` | `+9%` / `+3Hz` |
| `zh-cheer-female` | 现场助威女声 | `zh-CN-XiaoyiNeural` | `+17%` / `+8Hz` |
| `yue-match-male` | 粤语球评男声 | `zh-HK-WanLungNeural` | `+16%` / `+4Hz` |

用匹配语言的文案试听外语预设；粤语建议使用粤语表达，切换音色不会自动翻译。声线是否适合角色应以试听为准，尤其是少年角色。在线服务的目录会变化，可用 `.venv/bin/python -m edge_tts --list-voices` 查询当时的服务端列表。

## 配音与多角色

现有输入格式仍是逐句 JSON。`text` 保留给字幕，`say` 可另写数字、缩写的实际读法。下面是一组通用讲解片角色：

`lines.json`：

```json
[
  {"id": "v01", "role": "narrator", "text": "每一次好奇，都是探索的开始。"},
  {"id": "v02", "role": "host", "text": "今天，我们来看看这台机器如何工作。"}
]
```

`cast.json`：

```json
{
  "narrator": "zh-warm-female",
  "host": {"preset": "zh-youth-male", "rate": "+5%"}
}
```

将两个文件放到影片目录，再执行：

```sh
.venv/bin/python core/tts/tts_zh.py films/my-film/lines.json films/my-film/voices --cast films/my-film/cast.json
```

只有一个旁白时，无需 `role` 或 `cast.json`：

```sh
.venv/bin/python core/tts/tts_zh.py films/my-film/lines.json films/my-film/voices --preset zh-warm-female
```

上述单旁白用法应搭配没有 `role` 字段的脚本。逐句 WAV 仍命名为 `<id>.wav`，时长仍写入 `dur.json`，可继续交给转写检查、字幕时间线和混音流程。更换语音后要按新的时长重排字幕与动画，不能直接沿用旧音轨的时间。

## 参数覆盖顺序

从低到高为：内置默认值 → 全局 `--preset` → 全局 `--voice/--rate/--pitch` → `cast` 角色配置 → 行内 `preset` → 行内 `voice/rate/pitch/speed`。每应用一个预设，会一起替换音色、语速、音高；同一层显式 `rate` 优先于 `speed`。`speed` 是倍速，例如 `0.85` 对应 `-15%`。

负值 CLI 参数使用等号，避免被解析为另一个选项：

```sh
.venv/bin/python core/tts/tts_zh.py films/my-film/lines.json films/my-film/voices --preset zh-warm-female --rate=-10% --pitch=-1Hz
```

不指定任何新选项时，仍使用原默认值 `zh-CN-XiaoxiaoNeural`、`+0%`、`+0Hz`；选用 `zh-warm-female` 才会应用慢速讲书设置。

加 `--dry-run` 可先看逐句最终参数，输出 JSON，不联网、不写配音文件：

```sh
.venv/bin/python core/tts/tts_zh.py films/my-film/lines.json films/my-film/voices --cast films/my-film/cast.json --dry-run
```

## 生成后检查

选好声音后仍需对真实台词执行转写检查，确认发音、数字和句尾完整；转写通过不等于声音自然度已通过试听。混音之后再检查成片音轨，避免背景音乐盖住句首。

```sh
.venv/bin/python core/tts/asr_check.py films/my-film/lines.json films/my-film/voices --lang zh
```

网络不可用时，原有 `core/tts/tts.py` 的 Kokoro 离线路径仍可使用；中文需在行内设置 `"lang": "cmn"` 并选用对应的 `zf_*` / `zm_*` 音色。Edge 预设 ID 不能直接传给 Kokoro，两种引擎也不会静默互换。
