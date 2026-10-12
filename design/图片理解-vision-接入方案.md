# 图片理解（Vision）接入方案

> 目标：让 MiniClaw 能「用图片对话」——用户在对话中提供图片，模型（DeepSeek `deepseek-flash`）理解并分析图片内容。
> 状态：**已确认并实施**（传图方式=base64 内联；多轮策略=仅当前轮；UI=剪贴板/拖拽/文件选择；CLI=图片文件路径；非 vision 明确提示；detail=auto；P2 本期不做）。
> 参考：<https://api-docs.deepseek.com/zh-cn/guides/vision> 、[entrance.md](../entrance.md)

---

## 一、DeepSeek Vision 关键约束（摘自官方文档）

- 模型：**`deepseek-flash`** 支持图片输入；旧 `deepseek-v4-flash-vision-exp` 已下线。
- 协议：**OpenAI 兼容**，`content` 为**块数组**（非纯字符串）：
  ```json
  {"role": "user", "content": [
    {"type": "text", "text": "这张图片里有什么？"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<b64>"}}
  ]}
  ```
  也支持 `file`（`file_id` / `file_data`）块。
- **图片只能出现在 `user` 消息里**；`system` / `assistant`（含 `tool`）消息携带图片会 **400**。
- 支持格式：JPEG / PNG / GIF / WebP（按**内容**判断，不看扩展名）。
- 限制：请求体 48 MiB（内联）；单图 32 MiB（base64/URL）、64 MiB（Files API `file_id`）；单请求 ≤ 600 张；单边 ≤ 8192 px；每图约 **≤1024 token**。
- 可选 `detail`：`low`（缩放到 512×512，省 token）/ `high` / `original` / `auto`。

---

## 二、现状盘点（代码定位）

| 相关点 | 现状 | 位置 |
| --- | --- | --- |
| 图片数据结构 | **已有** `ImageBlock` / `Base64Source` / `URLSource`；`ToolResponse` 可含 `TextBlock|ImageBlock` | `agents/base_llm_client.py` |
| Provider 消息 | `_build_completion_kwargs` **原样透传 `messages`** 给 litellm → **天然支持 content 块数组** | `agents/providers/litellm_provider.py` |
| 用户消息 | `content` 为**纯字符串**；系统提示词/技能合并进字符串 | `app/runtime.py::append_user_message`、`utils/common.py::merge_system_prompt_into_user` / `build_skill_injection` |
| 工具结果回传模型 | 被序列化成 **JSON 文本**（`_tool_response_to_text` / `model_dump_json`）→ **图片块丢失**，模型看不到 | `app/runtime.py`、`cli/stream_runner.py` |
| `view_image` 工具 | **已删除**：原返回 `ImageBlock(本地路径)`，但工具结果最终被转成文本 → 图片到不了模型、形同虚设 | ~~`agents/tools/view_image.py`~~ |
| 前端输入 | `Composer` 无图片输入；`ChatStreamRequest` 无图片字段；`UIMessage` 无图片 | `frontend/src/components/chat/Composer.tsx`、`api/client.ts`、`store/appStore.ts` |
| 落盘 | 历史为 JSONL 消息字典；若图片以 base64 直接入历史会**撑爆文件** | `cli/history_store.py` |

> 结论：**providers 层已支持多模态**；缺的是「用户图片输入 + 内部图片表示 + 请求构建时转成块数组 + 工具图片投喂 + 前端」。

---

## 三、总体方案（分阶段）

- **P1（核心，本期做）**：用户在对话中提供图片 → 多模态 `user` 消息 → 端到端（UI ↔ 后端 ↔ 模型 ↔ 历史）。
- **P2（可选，本期可一并做）**：让**工具产生的图片**（`view_image` / `desktop_screenshot` / `browser_use`）能被模型看到。
- **P3（后续）**：Files API 复用、外部图片 URL、`detail=low` 等优化。

---

## 四、P1 详细设计：用户图片（粘贴 / 选择 / 拖拽）

### 4.1 内部表示（消息里的图片）

- `user` 消息 `content` 支持**块数组**（内部格式）：
  ```
  [{"type": "text", "text": "<用户文本>"},
   {"type": "image", "path": "<本地绝对路径>", "mime": "image/png"}]
  ```
- 图片以**文件**落盘，历史 JSONL 只存**路径引用**（不内嵌 base64）。
- 纯文本消息仍可为字符串（向后兼容）。

### 4.2 图片存储

- 目录：`~/.miniclaw/multimodal/uploads/<session_id>/<uuid>.<ext>`（与既有 `multimodal/` 一致）。
- 后端收到 base64 → 落盘 → 消息里记绝对路径 + mime。

### 4.3 请求构建（关键：转成 DeepSeek/OpenAI 块）

- `_build_request_messages`（`app/runtime.py`）在构造请求副本时，把内部 `image` 块**转成**：
  ```
  {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<读到文件的b64>", "detail": "auto"}}
  ```
- **适配系统提示词/技能注入**：`merge_system_prompt_into_user` / `build_skill_injection` 需支持 content 为数组——把注入文本并入（或新增）第一个 `text` 块。
- **校验**：图片只放 `user` 消息（DeepSeek 约束）。

### 4.4 接口

- `models.py::ChatStreamRequest` 增加：
  ```
  images: list[ImageInput] = []      # ImageInput: {mime?: str, data_base64: str}
  ```
- `chat_router` 透传到 `ChatSession.stream_events(message, images)`。

### 4.5 前端

- `Composer`：支持 **粘贴 / 文件选择 / 拖拽** 图片；显示缩略图 + 删除；发送时读为 base64。
- `client.ts::streamChat`：body 增加 `images`。
- `appStore.sendMessage(text, images)`：`UIMessage` 增加 `images: {dataUrl, name}[]`。
- `MessageItem`：`user` 气泡渲染图片缩略图。
- `mapHistory`：后端快照里的图片块还原为缩略图（路径 → 经后端接口取字节或 `file://`）。

### 4.6 上下文与预算

- `utils/context.py` 估算 token 时，**每张图片按 ~1024 token** 计入。
- 精简（shrink）策略需定义图片取舍（见「待确认」）。

---

## 五、P2（可选）：工具图片投喂给模型

- **约束**：DeepSeek **不允许 `tool` 消息带图**（仅 `user`）。因此不能直接把工具结果里的 ImageBlock 放进 `tool` 消息。
- **方案**：把工具返回的图片**转为紧随其后的 `user` 消息**注入（如「【工具返回图片】」文本 + `image_url` 块），模型即可看到。
  - 请求构建时：遍历 `tool` 消息，若含 `ImageBlock`，在其后追加一条内部 `user` 图片消息。
  - 同时修正 `view_image`：把 `source.url` 的**本地路径转为 base64 data URL**。
- **代价**：会改变对话结构（多出一条 user 图片消息），需注意历史/配对清理（`_sanitize_messages`）。
- **前置验证**：先用 `deepseek-flash` 实测「tool 消息内 image_url」是否真的 400，再决定是否用注入方案。

---

## 六、模型与配置

- `.env`：`LLM_MODEL=deepseek/deepseek-flash`（或经 `/llm`、`/model` 切换）；确认 `LLM_BASE_URL` / `LLM_CLIENT_PROVIDER`。
- 可选开关：`MINICLAW_VISION_ENABLED`（默认 true）；非 vision 模型时**忽略/明确提示**图片。
- `detail` 默认 `auto`（可配 `low` 省 token）。

---

## 七、影响面与兼容

- Provider、`_sanitize_messages` **无需改**（透传 content 数组）。
- 需要改的是：消息构建（数组化）、请求构建（转块）、接口、前端、上下文估算、历史还原。
- 纯文本对话**不受影响**（content 仍可为字符串）。
- 历史里图片存**路径**；若图片文件被删除，回放/请求时降级为文本占位。

---

## 八、改动清单（预计）

| 层 | 文件 | 说明 |
| --- | --- | --- |
| 后端 | `app/models.py` | `ChatStreamRequest` 增加 `images` |
| 后端 | `app/routers/chat_router.py` | 透传 images |
| 后端 | `app/runtime.py` | `append_user_message`/`_build_request_messages`/`snapshot` 支持图片块；请求时转 `image_url` |
| 后端 | `utils/common.py` | `merge_system_prompt_into_user`/`build_skill_injection` 适配数组 content |
| 后端 | `utils/context.py` | 图片按 ~1024 token 估算、精简策略 |
| 后端 | 新增/复用图片存储工具 | 落地 `~/.miniclaw/multimodal/uploads/<sid>/` |
| 后端 | （P2）投递层（`cli/stream_runner.py` 等）+ 新图片载体 | 把工具产出的图片转成 `user` 图片消息（`view_image` 已删） |
| 前端 | `components/chat/Composer.tsx` | 粘贴/选择/拖拽 + 缩略图 |
| 前端 | `api/client.ts`、`store/appStore.ts`、`components/chat/MessageItem.tsx` | 传图、UIMessage.images、气泡显示、mapHistory |
| 样式 | `styles/index.css` | 缩略图/拖拽区样式 |

---

## 九、验收标准

- 粘贴 / 选择 / 拖拽一张图片并提问，模型能**描述/识别图中内容**；
- 历史回放显示图片缩略图；多轮对话中模型能继续参考该图（按策略）；
- 非 vision 模型或超限（大小/数量/格式）时有**清晰提示**；
- 图片以**文件**落盘，JSONL **不内嵌 base64**；
- 纯文本对话行为不变。

---

## 十、关于 `tools/` 的影响（结论）

- **P1（用户提供图片）→ 不涉及 `tools/`**：用户图片进入 `user` 消息的 content 块数组，**不经过任何工具调用**。
- **`view_image` 工具已删除**（本轮决定）：
  - 原因：它返回 `ImageBlock(source.url=<本地路径>)`，而工具结果回传时被序列化成 JSON 文本 → **图片到不了模型、形同虚设**；全仓除注册外无任何依赖。
  - 已改动：`tools/__init__.py`、`llm_tools_manager.py`（移除 import 与 `BUILTIN_TOOLS` 项）、删除 `tools/view_image.py`，并更新 `entrance.md` / `README.md`。
- **P2（工具产生的图片）若要做**：因 `view_image` 已删，需要一个**新的“把图片文件带入模型上下文”的载体**（例如重加一个精简工具，或直接在投递层把 `desktop_screenshot`/`browser_use` 的图片路径转成 `user` 图片消息）。届时再定：
  - 约束：DeepSeek **禁止 `tool` 消息带图** → 图片必须转成一条 `user` 图片消息；
  - `desktop_screenshot`、`browser_use` 目前只返回文件路径（文本），**无需改**（由投递层决定如何把该路径变成图片）。
- 结论：**P1 不碰 `tools/`；`view_image` 已移除；P2 待到执行时再决定新载体。**

---

## 十一、已定：输入方式与其它决策

- **UI**：支持**剪贴板粘贴 + 拖拽 + 文件选择**（三种）图片。
- **CLI**：**只接受图片文件路径**（如 `/image <path>` 斜杠命令，或在输入中识别存在的图片文件路径）。
- 两者最终汇聚为**同一内部表示**：`user` 消息的 content 块数组（文本块 + image 块），后端处理逻辑共用。
- **非 vision 模型**：**明确提示**「当前模型不支持图片」。
- **`detail`**：默认 **`auto`**。
- **P2（工具图片投喂）**：**本期不做**。

---

## 十二、多轮图片上下文策略（三选一）

> 背景：每张图片约 ≤1024 token，历史里图片累积会**快速膨胀**。图片**落盘**（历史 JSONL + UI 回放）与**发给模型**是两件事——本策略只影响后者。

### (a) 仅当前轮携带（最省 token）
1. **落盘照旧**：图片仍记入历史（路径引用），UI 回放时正常显示缩略图。
2. **构造请求时（`_build_request_messages`）**：
   - 只把**最后一条 `user` 消息**里的图片块转成 `image_url`（base64 data URL）；
   - 所有**更早**的 `user` 消息里的图片块**剔除**——若该消息还留有文本，就只发文本；若整条只剩图片、没有文本，则用文本占位块（如 `"[图片]（历史图片，已省略）"`）保证消息非空。
3. **效果**：任一时刻的请求里**最多只有“当前这一轮”的图片**，token 占用有上界。
4. **代价**：若下一轮**不再贴图**、却问“刚那张图里还有什么？”，模型**看不到**那张图 → 需要用户**重新贴图**。

### (b) 只带最近 N 张（跨轮）
- 请求时从**时间最近的图片块**往前取 N 张（如 2–3 张）转 `image_url`，其余剔除；多轮追问“刚那张图”在 N 张窗口内可继续。

### (c) 全部保留
- 历史所有图片都回传，最“连贯”但 token 增长最快。

> 我的倾向：**(a)**（最省、实现最简）；若你希望支持“不重贴图继续追问”，再上 **(b)**。

---

## 十三、传图方式对比（base64 内联 / 外部 URL / Files API）

DeepSeek 支持**三种**传图方式（内容块均放在 `user` 消息里）：

| 方式 | 形态 | 适用 | 代价 |
| --- | --- | --- | --- |
| **base64 内联** | `{"type":"image_url","image_url":{"url":"data:...;base64,..."}}` | 本地文件、最简 | 每次请求都携带 base64；请求体 ≤48 MiB；单图 ≤32 MiB |
| **外部 URL** | `image_url` 用 http(s) 链接 | 图片已公开可访问 | 我们的图是本地文件 → **不适用** |
| **Files API** | 先 `POST /files`（multipart：`file` + `purpose=user_data`）→ `file_id` → `{"type":"file","file_id":"file-api-..."}` | 同一张图多请求复用 / >32 MiB 大图 | 需**上传 + 文件生命周期**（默认永久，可 `expires_after`；删除会话时应清理） |

- Files API 细节：单文件 ≤64 MiB；引用时单图 ≤64 MiB；`file` 块也可用 `file_data`(base64) **内联**（与 `file_id` 互斥，可带 `filename`）。
- **Files API 上传接口**（`POST {base_url}/files`，multipart/form-data）：
  - 必填：`file`（binary，≤64 MiB，JPEG/PNG/GIF/WebP）、`purpose=user_data`；
  - 可选：`expires_after[anchor]=created_at` + `expires_after[seconds]`（3600–2592000 秒；**省略则永久有效**）；
  - 返回 `{ "id": "file-api-...", "object":"file", "bytes", "created_at", "filename", "purpose", "expires_at"? }`；
  - 清理：`DELETE {base_url}/files/{file_id}`；列出/查询：`GET {base_url}/files` / `.../files/{file_id}`。
- **可移植性（关键）**：`file` / `file_id` 是 **DeepSeek 专有**；`image_url`（base64 data URL）是 **OpenAI 标准、可跨 provider**。本工程支持多 provider（litellm），故**默认用 `image_url` 更通用**，Files API 仅作 DeepSeek 场景的优化。
- 与多轮策略的关系：**base64 内联 + 多轮保留图片** → 每轮都要重发 base64；**Files API** → 上传一次、用 `file_id` 多轮引用更省。

**本期决定**：采用 **base64 内联**（典型粘贴截图几百 KB~几 MB，远低于 48 MiB，实现最简、无需上传与清理）。
**Files API 列为 P3（后续优化）**：当出现「同图多轮复用」或大图（>32 MiB）需求时再接入，并配套生命周期管理（上传设 `expires_after`、删除会话时删除 `file_id`）。

---

## 十四、待确认事项

1. ~~范围~~（已定）：UI = 剪贴板+拖拽+文件选择；CLI = 图片文件路径。
2. ~~P2~~（已定）：**本期不做**。
3. ~~输入方式/非 vision/detail~~（已定）：三种输入都做；非 vision **明确提示**；`detail=auto`。
4. **多轮图片上下文策略**：**（a）/（b）/（c）取哪个？**（见第十二节，倾向 (a)）
5. **默认模型**：是否把默认模型切到 `deepseek-flash`？（`.env` 的 `LLM_MODEL`）

> 确认 4、5 后即可开始编码。

---

## 十五、实施记录（已完成）

**已定决策**：传图方式=**base64 内联**；多轮策略=**仅当前轮**；UI 输入=**剪贴板/拖拽/文件选择**；CLI=**图片文件路径**；非 vision→**明确提示**；`detail=auto`；**P2 本期不做**；`view_image` **已删除**。

**内部表示**：`{"role":"user","content":"<文本>","images":[{"path":"<绝对路径>","mime":"image/png"}]}`（图片落盘为文件，历史只存路径）。仅在**构造请求**时转成 OpenAI 兼容块数组（base64 `data:` URL）。

**改动文件**
| 层 | 文件 | 说明 |
| --- | --- | --- |
| 后端 | `utils/multimodal.py` | **新增**：图片落盘、`data:` URL、`build_user_content`、快照用 `images_for_snapshot` |
| 后端 | `app/runtime.py` | `append_user_message(images)`、`_save_user_images`、`_build_request_messages` 图片转块（仅当前轮）、`snapshot` 附 `data_url`、非 vision 校验、`_model_supports_vision` |
| 后端 | `app/models.py` | `ChatStreamRequest.images` + `ChatImageInput` |
| 后端 | `app/routers/chat_router.py` | 透传 images（stream/chat 均支持「纯图片」消息） |
| 后端(CLI) | `cli/main.py` | `_pending_images` + `_cmd_image` + `_append_user_message` 附带图片 + `_build_request_messages` 图片转块 |
| 后端(CLI) | `cli/commands.py` | 新增 `/image` 命令 |
| 前端 | `components/chat/Composer.tsx` | 剪贴板粘贴 / 拖拽 / 文件选择 + 缩略图 |
| 前端 | `api/client.ts` | `streamChat` body 增加 `images` |
| 前端 | `store/appStore.ts` | `UIMessage.images`、`sendMessage(text, images)`、`mapHistory` 还原图片 |
| 前端 | `components/chat/MessageItem.tsx` | 用户气泡显示图片 |
| 样式 | `styles/index.css` | 用户图片与输入区缩略图样式 |

**使用**
- **UI**：在输入框**粘贴**截图、或**拖拽/选择**图片 → 出现缩略图 → 发送（可与文字一起，也可只发图片）。**缩略图/消息中的图片点击可放大预览**（灯箱：点击空白处或按 Esc 关闭）。
- **CLI**：`/image <图片路径>` 附加 → 下一条消息携带；`/image clear` 清空。
- 需把模型切到支持视觉的 **`deepseek-flash`**（`/llm`、`/model` 或 `.env` 的 `LLM_MODEL`）；非 vision 模型发图会收到**明确提示**。

**验证**
- 后端单测：图片落盘 / `data:` URL / `build_user_content` 块；请求构建**仅当前轮带图**（旧图剔除、纯文本保持）；`snapshot` 带 `data_url`；`_model_supports_vision` 判定。
- CLI 命令注册 `/image` 通过；`py_compile`、`app._app` 与 `cli.main` 导入 OK；`pytest` 19 passed。
- 前端 `tsc --noEmit` + `npm run build` 通过。

**局限**：本地未做“真实视觉模型”的端到端验证；请用 `deepseek-flash` 贴一张图实测确认。

---

## 十六、问题修复：litellm 的 `deepseek/` provider 会丢弃图片

**现象**：贴图提问后，模型“看不到图”，反而去列目录、读会话文件、用 OCR 脚本识别——最后基于 OCR 作答。

**排查过程**
1. 读会话文件 `s20261012230243-464b2b6.jsonl`：确认图片**已落盘**（`~/.miniclaw/multimodal/uploads/<sid>/…png`）且用户消息带 `images`；首条 assistant `reasoning`/行为表明它**没收到图片**（“there's an image that should have been provided…”）。
2. 复现请求构建：`_build_request_messages()` 对首条 user 消息确实产出 `[text, image_url]` 块（说明**我方已正确构造图片块**）。
3. 直连 DeepSeek 官方接口（`POST /chat/completions`，`image_url` data URL）：**200 且正确识别颜色**。
4. 经 **litellm** 发送同样的消息：
   - `model="deepseek/deepseek-v4-flash"`（默认 deepseek provider）→ **图片被丢弃**（回答“无色/无法确定”）；
   - `model="openai/deepseek-v4-flash"` 或 `model="deepseek-v4-flash" + custom_llm_provider="openai"` → **正确识别“红色”**。

**根因**：**litellm 内置的 `deepseek/` provider 会丢弃消息中的图片内容**（把它当作文本模型处理）；改走 OpenAI 兼容路径即正常。

**修复**（`agents/providers/litellm_provider.py::_build_completion_kwargs`）
- 新增 `_messages_contain_image(messages)`；
- 当消息**含图片**且 `model` 以 `deepseek/` 开头时：把 `model` 去前缀为 `<model>`，并设 `custom_llm_provider="openai"`（走 OpenAI 兼容路径）。
- **仅影响含图请求**；纯文本请求仍用原 `deepseek/`（不受影响）。

**验证**
- 参数改写：`deepseek/deepseek-v4-flash` → `deepseek-v4-flash` + `custom_llm_provider=openai`；
- 经工程 provider（`LiteLLMClient.chat`）发送 256×256 纯红图 → 模型回答 **“红色”**（修复前为“无色/无法确定”）。

**备注**
- 含图请求改走 OpenAI 兼容路径；DeepSeek 文本/推理与**纯文本**请求不受影响。
- 成本计算因去掉 `deepseek/` 前缀会回退到兜底单价（DEBUG 级日志；正常 INFO 级别不显示）。
- 请重启 UI 后，用 `deepseek-v4-flash`（或 `deepseek-flash`）重新贴图实测确认。

---

## 十七、性能优化：单轮图片编码缓存

**问题**：agent 模式下一轮 = `while True` 循环（每次工具调用后再调一次模型），每次迭代都重建请求 → 当前轮图片被**反复读盘 + base64 编码**（一次会话轮里可能 K+1 次）。

**方案**：**单轮（per-turn）缓存** —— 一轮内图片只编码一次、轮内复用，**轮结束即清理**。

**实现**
- `utils/multimodal.py`
  - `_cache_key(path)`：键 = `(绝对路径, mtime_ns, size)`；
  - `image_path_to_data_url(path, mime, cache=None)`：命中缓存直接返回（不读盘）；
  - `build_user_content(text, images, detail, cache=None)`：把 cache 透传；
  - `save_image_base64(..., cache=None)`：落盘后**用已有 base64 预热**缓存（本轮首次也无须再读盘）。
- `app/runtime.py`
  - `stream_events` 变为**薄包装**：轮内 `self._turn_image_cache = {}`，`try: … finally: self._turn_image_cache = None`（正常/异常/中断都清理）；原主体移入 `_stream_events_inner`；
  - `_build_request_messages` / `_save_user_images` 传入 `self._turn_image_cache`。
- `cli/main.py`
  - `stream` 建/清 `self._turn_image_cache`，主体移入 `_stream_loop`；`_build_request_messages` 传 cache。

**效果**：一轮里的 `K+1` 次模型调用，图片编码从 `K+1` 次降到 **1 次**（发送次数不变，仍每轮都发给模型）。

**边界**
- 缓存随 **轮** 创建/销毁（`finally` 保证清理）；
- 键含 `mtime/size`，图片文件被改动 → 自动重编码；
- 查找需要文件存在（用于 `stat` 取键）；图片文件在本工程按 UUID 落盘且不轻易变，故稳定。

**验证**：单测——落盘预热、缓存命中时**不读盘**（把 `read_bytes` 替换为抛错仍正常返回）、`build_user_content` 走缓存、`stream_events` 结束后 `_turn_image_cache is None`；`pytest` 19 passed。
