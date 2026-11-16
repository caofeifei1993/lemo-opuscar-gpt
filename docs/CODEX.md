# 在 Codex 桌面应用中使用

本分支把 [Lemo-Opuscar by Lemomo (LemoLab)](https://github.com/lemomo-ai/lemo-opuscar) 适配为 Codex 技能。99 种风格、原始演示和制作方法保留；修改了技能入口、提问方式、库定位和更新逻辑。授权仍以 [LICENSE](../LICENSE) 为准。

Codex 在当前登录会话中编写代码，本机 Chromium 和 FFmpeg 渲染成片，无需另填 OpenAI API Key。这里没有新增模型 API 服务。普通聊天环境如果没有本地执行工具，只能协助编写方案与源码，不能凭这些文件直接宣称渲染成功。

## 安装和调用

在这个项目根目录运行：

```sh
python3 tools/install_codex.py
sh plugin/skills/lemo-opuscar/scripts/setup.sh deps
```

安装器创建 `~/.agents/skills/lemo-opuscar` 符号链接，指向本项目的 `plugin/skills/lemo-opuscar`。保留项目所在目录；重复运行安装器会识别已有链接，其他同名目录则拒绝覆盖。指定另一安装位置时，`--dest` 是完整的技能目录：

```sh
python3 tools/install_codex.py --dest /path/to/skills/lemo-opuscar
```

仓库还带有 `.agents/skills/lemo-opuscar` 项目级入口。技能目录和符号链接遵循 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)。全局安装后，在其他项目中也可以调用；如果列表没有刷新，先新建聊天，必要时重启应用。

在 Codex 里直接说：

```text
使用 lemo-opuscar，用水彩笔刷风格制作一支 30 秒中文短片，介绍我的咖啡店。
横屏 1920×1080，有旁白，先给我看分镜。
```

也可以用 `$lemo-opuscar` 显式引用技能，或先问“列出适合科技科普的风格”。只看风格不会安装依赖。你指定的语言、素材和分镜偏好会沿用；未要求分镜审核时，默认继续制作。

## 运行环境

核心工具需要 Node.js 20+、FFmpeg 7+（包含 `ffprobe`）、Python 3.11+ 或 `uv`。`deps` 安装项目内 Node 包、Playwright 的无头浏览器和 `.venv` 核心 Python 包。不会安装全局系统软件。macOS 是本次实际验证环境；其他系统尚未实测本分支。

按影片需要再装可选依赖：

```sh
sh plugin/skills/lemo-opuscar/scripts/setup.sh deps voice
sh plugin/skills/lemo-opuscar/scripts/setup.sh deps music
```

`voice` 包括本地语音模型与转写检查；中文 `edge-tts` 路径需要联网并把配音文本发送给相应服务。音色和配乐库的详细依赖见 [TECHNIQUE.md](../TECHNIQUE.md)。标 ✦ 的三个风格优先使用当前会话可用的生图工具；CLI 生图助手只是备用路径。

## 库路径和更新

`setup.sh` 无参或 `check` 只检查，不联网更新、不安装依赖。查找顺序是：

1. `LEMO_OPUSCAR_HOME` 显式指定的库。
2. 当前所在的库仓库。
3. 技能所属的本地库（会解析符号链接）。
4. `~/lemo-opuscar-gpt`。

如果只有独立复制的技能而没有库，运行 `setup.sh install` 下载本分支。`LEMO_OPUSCAR_REPO` 只控制新下载的来源，默认是 `caoofeifie1993/lemo-opuscar-gpt`，不会改写已有库的 origin。

需要更新时显式运行：

```sh
sh plugin/skills/lemo-opuscar/scripts/setup.sh update
sh plugin/skills/lemo-opuscar/scripts/setup.sh deps
```

只对干净的 main 分支，从现有 origin 做快进更新；本地修改或分叉时停止，保留文件。不要用强制重置来解决更新失败。未提交的适配修改只存在本机，远程 GitHub 仓库要经你另行授权提交、推送后才会包含它们。

## 输出与检查

在本库内发起制作：`films/<名字>/`；在其他项目调用：当前项目的 `<名字>/`。每支片子的制作方案、代码、音频、字幕和 MP4 都放在它的目录里。个人风格仍保存在 `~/lemo-my-styles/`。

运行两秒技术检查：

```sh
python3 tools/smoke_codex.py
```

每次在 `films/codex-smoke/` 创建新目录，通过原项目的 `events → still → video → mux` 工具生成测试片，并检查实际视频和音轨。输出包括 `codex-smoke.mp4`、`stills/`、`check.json`。`--out` 可指定一个空目录；已有文件时拒绝覆盖。该检查不生成旁白、不调用生图服务。

安装与更新脚本的离线回归测试：

```sh
python3 -m unittest discover -s tools/tests -v
```

上述渲染检查与离线回归测试均通过时，表示已验证核心渲染链路及技能安装行为，并不表示 99 种风格、旁白模型、在线服务或 GPU 密集型 3D 场景已全部验证。制作具体影片时，仍按导演指南检查实际画面与声音。

## 卸载

确认路径是安装器创建的符号链接后，只移除链接：

```sh
test -L "$HOME/.agents/skills/lemo-opuscar" && unlink "$HOME/.agents/skills/lemo-opuscar"
```

项目内 `.agents/skills/lemo-opuscar` 入口在打开本仓库时仍可用。卸载全局入口不会删除本项目、已生成影片或个人风格。
