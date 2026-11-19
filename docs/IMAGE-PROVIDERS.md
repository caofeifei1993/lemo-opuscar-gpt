# 为插画和分镜选生图工具

在 Codex 制作视频时，可以直接说：

> 分镜用 ChatGPT 原生生图。成片插画用 OpenArt 的 Seedream 5.5，横屏，三张图的主角要保持一致。

也可以说“先列出我在 OpenArt 能用的插画模型”或“两种都用原生”。Codex 在制片简报里记录选择。插画与概念分镜可以各选一种，每支影片独立保存。**ChatGPT 原生**调用当前会话的图像工具，具体模型由宿主自动选择。**OpenArt**可点名模型；Codex 从当前工作区的实时目录核对模型、参考图支持与积分。只有确定要生成的素材才需要选工具。精准图表和正式渲染帧继续走原项目的绘制流程。

## 在影片中保存选择

下列命令由制作影片的 Codex 从库根目录执行。假设影片目录 `films/harbor` 已存在。示例模型 ID 需与实时目录核对。

```sh
python3 core/image/image_route.py configure films/harbor --kind storyboard --provider native
python3 core/image/image_route.py configure films/harbor --kind illustration --provider openart --model byte-plus-seedream-5-5
python3 core/image/image_route.py show films/harbor
```

用 `--kind both` 可以一次指定两种用途。文件 `image-providers.json` 存在影片目录，后续制作或修改可沿用；缺省为原生自动。用户已点名的模型无法使用时，说明原因，让用户选替代方案。首次存储 OpenArt 首选项时尽量保存实时目录的精确 ID。

## 从计划到素材

制作方案确定后，为每张插画或每格分镜取一个独立名称，准备构图、人物锚点、光线和风格提示词。示例如下。

```sh
python3 core/image/image_route.py plan films/harbor --kind storyboard --name shot-01 \
  --aspect 16:9 --prompt '远景，傍晚的渡轮靠向栈桥。主角站在船头左侧，视线朝岸边。' --save
```

`plan` 输出 JSON，`--save` 会将这次请求写入 `.image-jobs/storyboard/shot-01/plan.json`。长提示词可用 `--prompt-file`。普通 shell 用这些命令准备请求和保存图片；提交生图由当前 Codex 会话调用计划中的宿主工具。保存计划后，提交前先用 `image_route.py status PROJECT --kind KIND --name NAME` 检查已保存计划。已提交的 OpenArt 素材按原任务继续，已完成的素材直接复用。换构图或重新生成时使用新的素材名。

### 原生生图

1. 将计划中 `call.arguments` 传给当前会话的 `image_gen.imagegen`。需要参考本机图片时先查看，再为每张图给 `plan` 加上 `--ref 文件`（相对路径按影片目录解析）。需要引用最近的聊天附件时使用 `--recent-images N`，取能包含全部目标的最小数量，最多 5 张。两种引用方式择一。透明底新素材可加 `--transparent-background`。
2. 工具完成后，把它实际返回或保存的图片交给导入命令。取当前请求对应的结果。宿主若只返回内联图像，解码其图像数据，使用 `--stdin` 传入原始图片字节。

```sh
.venv/bin/python core/image/save_asset.py films/harbor --kind storyboard --name shot-01 \
  --provider native --aspect 16:9 --file '/path/to/returned-image.png'
```

### OpenArt

按上述影片配置，为第一张成片插画保存独立计划。例如在库根目录运行：

```sh
python3 core/image/image_route.py plan films/harbor --kind illustration --name plate-01 \
  --aspect 16:9 --prompt '渡轮靠岸的横幅插画。侧面全景，黄昏，红色船舷映在静水中。' --save
PLAN=films/harbor/.image-jobs/illustration/plate-01/plan.json
TMP=$(mktemp -d)
```

1. 依计划调用 `openart_model_list`。展示或选择当前工作区中支持 `text2image` 或 `image2image` 的模型，用返回的 ID 对应用户指定的名称。需要参考图时，生成计划时填 `--reference-count N`。对聊天附件使用宿主的 `openart_upload_import` 绑定，逐项确认成功并保持次序。宿主给出的已有 `upload:` / `resource:` 引用按原样使用。本地文件先通过宿主附件入口提供；不把本机路径当作云端引用。
2. 本地适配器读取宿主响应的 `structuredContent`。将模型目录、表单和报价暂存于本次请求的临时目录；命令中的 `PLAN` 是上一步保存的计划，`TMP` 是临时目录。依次取适配器输出的 `form`、`cost`、`generate` 对象，从各对象的 `toolName` 找到当前宿主工具，并传入相应的 `arguments`。带签名的引用与完成回执只作临时输入。

```sh
# 输出 form 调用。把 openart_model_form_get 的结果放入 form.json。
python3 core/image/openart_request.py --plan "$PLAN" --catalog "$TMP/catalog.json" --resolve-only

# 输出 cost 调用。把 openart_model_cost 对这组参数的结果放入 quote.json。
python3 core/image/openart_request.py --plan "$PLAN" --catalog "$TMP/catalog.json" --form "$TMP/form.json"

# 核对报价后输出 generate 调用，由宿主调用 openart_generate_image。
python3 core/image/openart_request.py --plan "$PLAN" --catalog "$TMP/catalog.json" --form "$TMP/form.json" --quote "$TMP/quote.json"
```

   有参考图时，后两条命令使用同一份 `--refs "$TMP/refs.json"`（成功导入的结果或有序 visualReference 数组）。指定分辨率等额外设置时，两步也使用同一个 `--params` 文件，字段来自该模型的实时表单。提示词、比例、模式、参考图或计价选项有变动，需重新查价。显示当前报价及张数。额度不足时按宿主给出的余额和充值入口提示用户，不自动改变选择。有多张不同构图时，分别建立计划、核价，检查合计，再按实时批量工具契约将独立请求组合成 `openart_generate_image_batch`。按实际接受的项目逐张记录任务；先前已经提交的项目不可重复发送。

3. 拿到提交响应立刻记录该素材对应的 `historyId` 和已解析的模型 ID。对于显示自刷结果卡的桌面宿主，报告已提交并让卡片继续更新，按工具契约结束本次调用；完成通知或用户继续后，用已记录 ID 接续。文本宿主使用其提供的等待能力。在已知任务状态前避免重新提交；如果提交响应丢失，核对服务历史后再决定如何继续。

```sh
python3 core/image/image_route.py submitted films/harbor --kind illustration --name plate-01 \
  --model byte-plus-seedream-5-5 --history-id "$HISTORY_ID"
.venv/bin/python core/image/finish_openart.py films/harbor --kind illustration --name plate-01 \
  --result "$TMP/completed.json"
```

   `finish_openart.py` 仅导入与该记录匹配的成功结果。它读取 `resources[].url` 的原图用于本机视频渲染，可通过 `--result -` 直接读标准输入；多个资源需要明确指定 `--resource-id`。在宿主卡片中展示 OpenArt 结果时遵循该工具的展示规则。

## 在成片中使用

插画保存为 `assets/illustrations/<名称>.png`，概念分镜保存为 `storyboard/images/<名称>.png`。同名 JSON 记录来源、模型、像素尺寸和校验值。实际文件会解码并校验；指定的比例容差为 5%。在影片代码和素材清单中使用保存的项目相对路径。如风格有固定文件名，将素材映射到对应位置。用概念分镜商定构图；影片审片时再用真实渲染的镜头确认画面和字幕。将使用的来源及提示词位置记录在影片的 `CREDITS`。
