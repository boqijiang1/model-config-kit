# 模型配置模块（Model Config Kit）

给软件快速加一块「模型设置」：多供应商、API Key 管理、模型清单、自动选型、体检，
自带一套可以直接嵌进页面的前端组件。后端是 FastAPI 路由 + 独立的业务层，前端是
一个原生自定义元素，没有任何前端构建步骤。

这套模块是从「漫剧分镜拆解工作台」的模型设置页完整抽取出来的，行为、文案和
测试都经过真机使用打磨，可以直接搬到下一个软件里。

## 能做什么

- **多供应商**：火山方舟（API / Coding Plan / Agent Plan 三条线各自地址与 Key）、
  DeepSeek、OpenAI 开箱即用；目录里没有的平台可以「创建自定义供应商」接任意
  OpenAI 兼容地址。
- **Key 管理**：Key 粘贴完当场真调验证，通过才落盘；页面上只显示圆点，点小眼睛
  才从本机接口取明文出来看。
- **模型清单**：每个供应商自己的模型清单；支持添加、改名、删除、单独开关；
  有在线模型列表的平台可以「从账号同步」。
- **自动选型**：按清单位置逐家、家内逐个发 1-token 极小请求真调，第一个能回包的
  当选；也可以点某个模型的名字手动指定（同样当场验证，调不通不让存）。
- **体检**：启动后台查一遍所有能用的供应商；增删改后自动复检；页面上有状态点、
  黄条和大白话原因。
- **模型行实测凭据**：清单里每个模型旁边会标「✓实测通过 / ✗没调通」，只来自本次
  运行真正调过的结果；换 Key、改地址、改模型名后旧结果自动作废。
- **给宿主直接用**：一行 `service.build_current_provider()` 就能拿到「现在生效的
  模型」客户端，直接 `chat()`。

## 目录结构

```
API层面模块/
├─ model_config/              后端 Python 包（不依赖 FastAPI 也能用核心层）
│  ├─ providers.py            OpenAI 兼容客户端（流式、重试、超时保险丝、手动停止）
│  ├─ registry.py             供应商模板 + 实例清单 + 老配置搬家
│  ├─ store.py                配置落盘（原子写；含 Key，务必 gitignore）
│  ├─ connection.py           验 Key / 拉模型列表 / 自动选型 / 错误翻人话
│  ├─ transport.py            真实网络的接缝（测试可换假实现，不联网）
│  ├─ service.py              业务层：供应商/Key/模型/选型/体检/实测凭据
│  └─ router.py               FastAPI 路由（挂到你的 app 上）
├─ ui/
│  ├─ model-config.js         前端组件：<model-config-panel>
│  └─ model-config.css        组件样式（Shadow DOM 内生效，不污染宿主）
├─ demo/                      可运行的独立演示
├─ tests/                     31 个测试（不联网）
├─ requirements.txt
├─ requirements-dev.txt
└─ pyproject.toml
```

## 30 秒跑起来（演示）

```bash
pip install -r requirements.txt
python demo/app.py
# 打开 http://127.0.0.1:8765
```

演示会把配置写到 `demo/data/model_config.json`（含 Key，已被 `.gitignore` 忽略）。

## 集成到你的软件（FastAPI）

### 1. 复制两个目录

把 `model_config/` 和 `ui/` 复制到你的项目里。

### 2. 后端挂路由

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from model_config import ModelConfigService, ModelConfigStore, create_router

app = FastAPI()

store = ModelConfigStore("data/model_config.json")
service = ModelConfigService(store, auto_start=True)   # 启动后台体检

app.include_router(create_router(service), prefix="/api/model-config")
app.mount("/static/model_config", StaticFiles(directory="ui"), name="model_config")
```

- `auto_start=True`：启动时后台体检一次，不阻塞服务启动；没配 Key 时不发任何网络请求。
- 如果你已有自己的配置文件，也可以把 `ModelConfigStore` 指到那个文件——模块只读写
  自己那几个字段（`provider_instances / model / model_provider / model_auto /
  thinking_level`），不会碰你别的字段。
- 端口/前缀随便换，前端用 `api-base` 对上即可。

### 3. 页面放一个标签

```html
<model-config-panel api-base="/api/model-config"></model-config-panel>
<script src="/static/model_config/model-config.js"></script>
```

可选属性：

| 属性 | 默认 | 说明 |
|---|---|---|
| `api-base` | `/api/model-config` | 接口前缀 |
| `css-href` | 与 js 同目录的 `model-config.css` | 样式地址（CDN/打包后可手填） |
| `show-thinking` | 开 | `"false"` 隐藏「思考深度」三档 |
| `heading` | 模型设置 | 页面大标题 |

组件会抛两个事件，宿主可以监听：

```js
const panel = document.querySelector("model-config-panel");
panel.addEventListener("mc-ready", e => console.log("加载完成", e.detail));
panel.addEventListener("mc-change", e => console.log("状态变了", e.detail));
// 也可以直接 panel.status / await panel.refresh()
```

### 4. 用「现在生效的模型」发请求

```python
provider = service.build_current_provider(timeout=300)
if provider is None:
    raise RuntimeError("还没有可用的模型：去模型设置页配一下")

reply = provider.chat(
    [{"role": "user", "content": "你好"}],
    {"max_tokens": 512},          # 平台参数原样透传
    on_chunk=lambda delta, is_content: print(delta, end=""),
)
provider.close()
print(reply.content, reply.usage)
```

`build_current_provider()` 按当前配置自动取接口地址、Key、家级默认参数和参数习惯
（OpenAI 推理系模型的 `max_completion_tokens` 等）。手动停止用 `provider.cancel()`。

## 接口一览

前缀就是 `include_router` 时给的前缀（下面写 `/api/model-config`）。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/status` | 页面所需全部状态（供应商、模型、体检、目录） |
| POST | `/providers` | 添加供应商（`template` 或 `name`+`base_url`） |
| PATCH | `/providers/{id}` | 改名字 / 地址 / 开关 |
| DELETE | `/providers/{id}` | 删除这家（Key 与模型一起删） |
| POST | `/providers/{id}/key` | 填/换 Key（验证通过才落盘）；空串=清掉 |
| GET | `/providers/{id}/key` | 取已存 Key 明文（本机小眼睛用） |
| POST | `/providers/{id}/test` | 测试这家（或指定模型） |
| POST | `/providers/{id}/models` | 添加模型 |
| PATCH | `/providers/{id}/models/enabled` | 模型开关 |
| PATCH | `/providers/{id}/models` | 改模型名 |
| DELETE | `/providers/{id}/models?model=` | 删除模型 |
| POST | `/providers/{id}/models/sync` | 从账号同步模型 |
| POST | `/providers/{id}/models/test` | 实测某个模型 |
| POST | `/config` | 自动选型 / 手动指定 / 思考深度 |
| POST | `/health/recheck` | 后台重跑一次体检 |

## 配置与安全

- 配置文件里有 **API Key**：`demo/data/`、`data/` 已在 `.gitignore` 里；接到别的
  软件时也务必把配置文件排除出版本库。
- `/status` 永远不返回 Key 本身，只返回「有没有」；明文只从
  `GET /providers/{id}/key` 单独取（前端点小眼睛才请求，和页面同源）。
- 页面与接口同源部署即可；如果跨源，需要你自己加 CORS，并想清楚是否允许取明文
  Key 的接口。
- 配置文件原子写（先写 `.tmp` 再替换），断电不会写坏原文件。手改坏了也只会丢掉
  坏的那一条实例，不会整份配置起不来。

## 自定义

### 换配色

组件颜色都是 CSS 变量，在宿主页面覆盖即可：

```css
model-config-panel {
  --mc-brand: #0f766e;
  --mc-brand-deep: #115e59;
  --mc-brand-weak: #ccfbf1;
  --mc-radius: 16px;
}
```

完整变量见 `ui/model-config.css` 顶部的 `:host`。

### 改供应商目录 / 加平台

编辑 `model_config/registry.py` 里的 `TemplateInfo`：

```python
TemplateInfo(
    template_id="my-provider",
    label="我的平台",
    base_url="https://api.example.com/v1",
    key_url="https://console.example.com/keys",
    models=("model-a", "model-b"),
    logo="",                      # 有品牌标就写 logo 键，没有就用名字首字
    hint="按量计费：用多少付多少",
    supports_model_list=True,     # 平台有 GET /models 就 True
)
```

如果平台没有在线模型列表（像火山方舟的订阅套餐），设
`supports_model_list=False` 并给一个 `probe_model`：验 Key 时拿它发 1-token 真调。

### 不用前端组件

所有行为都在 REST 接口里，`/status` 的数据结构是稳定的；你可以用自己的 UI
（React/Vue/小程序）照着一接。

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q          # 31 passed，全部不联网
```

测试通过注入假 `Transport` 来模拟「能调通 / 调不通 / Key 无效 / 模型列表」，
不会真的发请求，也不会花你的额度。

## 设计要点（为什么这样写）

- **模板 + 实例两层**：同一个平台可以加多条（方舟三条线各算一家），每条实例
  有自己的地址、Key、开关和模型清单；实例 id = 模板 id（第二条起加序号），
  所以不用查配置就能认出这家的调用习惯。
- **只信真调**：「Key 能用」不等于「每个模型都能用」。自动选型和手动指定都会
  逐个真调；模型行上的实测标记只来自真调结果，且换 Key / 改地址 / 改名后作废。
- **绝不静默换家**：某个实例被删或配置坏了，不会偷偷拿别家的 Key 去跑——那等于
  背着用户花另一家的钱。`build_current_provider()` 在没有可用模型时返回 `None`。
- **不阻塞请求**：验 Key 可能要十几秒，都在配置锁外做；体检在后台线程跑，界面靠
  轮询拿结果。
- **老配置能搬**：如果宿主软件以前用过「一家一行」的平铺字段（`ark_api_key` 等），
  第一次加载会自动搬成实例清单，Key、开关、锁定的模型都不丢；旧字段同步成回滚
  镜像。

## 常见问题

**Q：为什么订阅套餐的模型要手动加？**
A：火山方舟的 Coding Plan / Agent Plan 不提供 `GET /models`（实测 404，与 Key
对错无关），只能照平台控制台里的名字手动填。

**Q：为什么点「测试」要十几秒？**
A：那是一次真实的 1-token 对话请求，慢网下会久一些；结果会就地显示，不会卡住
页面其他部分。

**Q：配置文件能放进 git 吗？**
A：不能。里面有 API Key。只提交代码，配置留在本机/服务器。
