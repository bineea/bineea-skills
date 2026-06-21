---
name: gitlab-mr-review-with-glab
description: Use when you need to review a GitLab Merge Request and write the review back as a summary note; generate inline discussions only when the user explicitly asks for inline discussions (e.g., “inline discussions/逐行评论/inline”). Especially useful on Windows where bash cannot find glab, flags differ by subcommand, or shell quoting/encoding breaks multi-line comments.
---

# 用 glab 给 GitLab MR 做评审并回写（note + inline discussions）

## 目标
- 拉取 MR 元信息与 diff
- 生成评审结论
- 回写到 GitLab：
  - 默认：仅 1 条总体评论（MR note）
  - 仅在用户明确要求时：再生成 N 条 inline discussions（按文件+行号定位）

## 适用场景 / 触发信号
- 你已经在 GitLab 创建 MR，需要用 Claude Code 做 review 并回写到 MR
- Windows 环境常见坑：
  - Claude Code 的 Bash 环境 `glab: command not found`
  - `--hostname` 在 `mr view/diff` 等子命令不支持（但 `glab api` 支持）
  - bash 特殊字符/历史展开（例如 `!`）导致长命令截断
  - 中文输出在 Python subprocess 里触发 GBK 解码错误

## 核心原则（避免翻车）
1) **读 MR/写 note 用 `glab mr ...`；写 inline discussions 用 `glab api` 调 GitLab discussions API。**
2) **Windows + bash 下，优先用 glab.exe 绝对路径调用。**
3) **inline discussions 不要用长 bash 命令直接拼多行字符串**；推荐用 Python 逐条调用 `glab api`。

---

## 步骤 0：准备 glab 与认证
### 0.1 验证 glab
在 PowerShell：
```powershell
glab --version
(Get-Command glab).Source
```
如果 Claude Code Bash 找不到 glab，用绝对路径（示例）：
- `D:/ProgramFiles/glab/glab.exe`

### 0.2 登录（自建 GitLab 必须指定 hostname）
```powershell
glab auth login --hostname <gitlab-host>
# 通常选择 HTTPS + Token(PAT)

glab auth status --hostname <gitlab-host>
```
PAT 最少建议 scope：`api`（能发 note/discussion）。

---

## 步骤 1：确定 MR 定位信息（URL → host + repo + iid）
从 MR URL：
`https://<host>/<group>/<project>/-/merge_requests/<iid>`
得到：
- `HOST=<host>`
- `REPO=<group>/<project>`
- `MR_IID=<iid>`

### 1.1 推荐：用脚本自动解析（避免手抄出错）
本目录脚本 `glab_mr_fetch.py` 内置了 MR URL 解析能力：

```bash
python glab_mr_fetch.py --mr "<MR_URL>" --out mr_review_out
```
它会在 `mr_review_out/context.json` 里写出 `host/repo/mr_iid/project_id/diff_refs`，后续脚本可直接使用。

---

## 步骤 2：拉取 MR 元信息与 diff（用于评审）
### 2.1 推荐：脚本一键拉取（更稳、更省命令）
```bash
python glab_mr_fetch.py --mr "https://<host>/<group>/<project>/-/merge_requests/<iid>" --out mr_review_out
```
产物：
- `mr_review_out/diff.txt`
- `mr_review_out/context.json`（含 project_id 与 diff_refs）

### 2.2 手工命令（需要你自己管理 host/repo/iid）
> 说明：`mr view/diff/changes` 子命令可能不支持 `--hostname`，因此用 `GITLAB_HOST=...` 绑定实例。

```bash
GITLAB_HOST=<host> "<glab.exe>" mr view <iid> -R <group>/<project>
GITLAB_HOST=<host> "<glab.exe>" mr changes <iid> -R <group>/<project>
GITLAB_HOST=<host> "<glab.exe>" mr diff <iid> -R <group>/<project> > mr.diff.txt
```

---

## 评审维度（复用性/质量/效率）与输出规范（参考 simplify）

## 最小覆盖策略（效率优先，但避免只抓“低垂果实”）
在 diff 很大时，至少覆盖以下关键面（每类至少 1-2 个锚点评论，能落到 diff hunk）：
- **入口层**：Controller / API handler（参数校验、权限、返回码/异常映射）
- **主流程**：Service/Manager（状态机、幂等、事务边界、异常处理一致性）
- **数据层**：Mapper/Repository + XML/SQL（where 条件、delete_flag、生效时间窗口、N+1 风险）
- **配置与测试**：application*.yml、*Test（CI 噪音、断言覆盖、调试输出）

如果行号/位置无法自信定位到新增 hunk：按前述“inline 降级策略”改写到总体 note。

### Scope（范围）与噪音控制
1) **只评审 MR 的已变更代码（diff）**
- 不对未改动区域做大改建议（除非本次变更明确引入/暴露了结构性问题）。
- 评论必须能指向本 MR 的某个 diff hunk（文件 + 行）。

2) **只检查，不修改本地代码**
- 本 skill 仅产出 review 结论并回写到 GitLab（1 条总体 note + N 条 inline discussions）。
- 可以提供“建议性示例代码片段”，但不得在本地生成补丁/修改文件。

3) **证据驱动 + 可执行建议**
- 每条 inline 评论必须包含：问题 + 影响 + 建议（见下方模板）。

4) **分级输出（推荐强制）**
- **P0：阻断合并**（正确性/安全/数据一致性/灾难性性能/明显回归）
- **P1：建议修复**（可维护性/清晰度/中等性能风险/测试缺口等）
- **P2：可选优化**（风格、轻微简化、潜在复用但收益不确定）

---

### 维度 1：复用性（Reuse）
目标：避免重复造轮子，最大化复用现有能力/模式。

检查清单：
1) **搜索现有 utilities/helpers** 是否能替代新写代码
- 常见候选：字符串/时间/时区、路径、重试、分页、错误包装、日志、鉴权、类型守卫、配置读取等。

2) **标记“新增函数/逻辑与既有实现重复”**
- 如果发现重复：指出应改用的现有函数/模块（若不知道精确名字，提供建议搜索关键词/目录）。

3) **标记“可复用但被手写”的内联逻辑**
- 手写 string 操作、manual path handling、ad-hoc env check、手写解析/校验等。

4) **标记 copy-paste + 轻微变体**
- 建议抽函数/抽策略对象/表驱动配置，减少维护点。

产出要求：
- 指出“应复用什么”（函数/模块/模式）+ “为什么复用更好”（一致性、bug surface 更小、减少维护点）。

---

### 维度 2：质量（Quality）
目标：提升可读性、可维护性、正确性与可测试性。

检查清单：
1) **冗余状态**：能推导的状态被缓存/复制，导致不一致风险
2) **参数膨胀（parameter sprawl）**：为新需求不断加参数而不是重构结构
3) **近重复代码块**：建议统一抽象，避免分叉演进
4) **泄漏抽象**：暴露内部细节，破坏现有边界（调用方被迫知道内部结构）
5) **字符串化（stringly-typed）**：魔法字符串/数字，本应常量/枚举/类型约束
6) **复杂度/可读性**：深层嵌套 if/循环；建议早返回、拆分函数、引入 guard clause
7) **注释**：删除解释 WHAT 的注释，保留解释 WHY 的注释（约束、不变量、坑位原因）
8) **边界与错误处理**：空值/缺省语义一致；避免吞错；错误信息是否保留关键上下文
9) **并发/时序**：竞态、共享可变状态、异步顺序依赖
10) **可测试性**：关键路径是否可覆盖；是否存在难测结构（硬编码时间/随机/全局单例）

产出要求：
- 每条问题说明“风险类型”（正确性/可维护性/可测试性等）并给出最小改动建议。

---

### 维度 3：效率（Efficiency）
目标：避免明显性能回归与资源浪费，尤其关注热路径。

检查清单：
1) **不必要的工作**：重复计算/重复序列化、重复 IO/网络调用
2) **N+1**：循环内查询/循环内请求/循环内写日志等
3) **并发/批处理缺失**：独立操作是否可并行（如 Promise.all / goroutines）；多次小请求是否可合并
4) **热路径膨胀**：把新逻辑加到启动/每请求/每渲染路径；引入同步阻塞
5) **轮询/事件 no-op 更新**：无变化也更新；建议 change-detection guard，避免下游重复刷新
6) **TOCTOU（存在性预检查）**：先 exists 再操作通常不如直接操作并处理错误
7) **内存与清理**：无界集合增长；listener/订阅/定时器未释放
8) **过宽操作**：读全量文件/全表只为取一个值；建议限制范围

产出要求：
- 必须说明“触发条件/热路径位置/为何会成为瓶颈”，避免空泛性能建议。

---

### 总体 note（MR note）输出模板（必须按此结构生成）
> 用于 `glab mr note` 回写。

```md
## 总体结论
- 风险等级：P0 ×N / P1 ×M / P2 ×K
- 关注范围：仅基于本 MR 的已变更代码（diff）

## P0（阻断合并）
- [file:line] 问题一句话结论 —— 影响（正确性/安全/数据一致性/灾难性性能/明显回归），建议修复方向

## P1（建议修复）
- [file:line] ...

## P2（可选优化）
- [file:line] ...

## 复用性/质量/效率概览
- 复用性：发现的重复/可复用点（按模块归类）
- 质量：可维护性/边界处理/测试缺口
- 效率：可能的热路径或明显浪费点（写清触发条件）
```

**重要：** `glab_mr_writeback.py` 在回写前会自动把 `[file:line]` 转换为 GitLab blob 可点击链接，确保 note 中的代码位置能够直接跳转。这是通过检测 `diff_refs.head_sha` 并生成标准 URL 实现的，无需在 review.json 中手动写 URL。

### Inline discussion 输出模板（每条必须包含三段）
> 用于 discussions API 回写；每条评论要短、具体，可落到该行/该函数。

```md
**问题**：这里新增了 X（重复逻辑/复杂分支/潜在 N+1/热路径阻塞）

**影响**：会导致 Y（维护成本/一致性风险/性能回归/难测/回归风险）

**建议**：
- 优先：复用/替换为（现有 util/模块/模式）或抽取为函数/统一抽象
- 次选：如果保留现实现，至少加上（guard/缓存/并发/测试/常量化）
```

### Inline 定位可靠性（必须）
- **只对“新增行（+）或上下文行（空格行）”发 inline**；不要对纯删除行发 inline。
- `glab_mr_writeback.py` 会自动处理：
  1. **刷新最新 MR 版本**：回写前重新拉取 MR 详情，获取最新 `diff_refs`（base_sha / start_sha / head_sha），避免使用旧版本上下文。
  2. **diff hunk 命中校验**：解析当前 MR diff，检查每个 inline 的 `(new_path, new_line)` 是否仍落在新增/上下文 hunk 范围内。
  3. **自动降级**：命中的 inline 正常发 discussion；未命中的 inline 自动降级到总体 note 的“未能锚定到当前 diff 的评论”区域，并转成可点击链接，避免只出现在时间线。

---

## 步骤 3：拿到 inline discussions 必需的 diff_refs（三段 SHA）
用 API 获取（`glab api` 支持 `--hostname`）。**注意：不同 GitLab/网关策略下，可能出现“MR 列表能看到，但详情接口 404”的情况**，需要按以下顺序做探针与 fallback。

### 3.1 获取 `PROJECT_ID`
优先用“按 path 取项目”最稳：

```bash
# repo=group/project 需要 URL encode（/ -> %2F）
"<glab.exe>" api --hostname <host> "/projects/<group>%2F<project>" --output json
```
如果你不方便 encode，才用 search：

```bash
"<glab.exe>" api --hostname <host> "/projects?search=<project>&simple=true&per_page=100" --output json
```
找到目标项目的 `id`。

### 3.2 获取 MR 详细信息并提取 diff_refs
目标字段：
- `diff_refs.base_sha`
- `diff_refs.start_sha`
- `diff_refs.head_sha`

**首选（正常情况）：**
```bash
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>/merge_requests/<MR_IID>" --output json
```

**如果返回 404，按序 fallback：**
1) 先确认 MR 确实存在于列表（避免把权限问题误判成“MR 不存在”）：
```bash
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>/merge_requests?state=opened&per_page=100" --output json
```
2) 再尝试带 query 的详情接口（部分实例需要额外参数才能返回详情）：
```bash
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>/merge_requests/<MR_IID>?include_diverged_commits_count=true" --output json
```
3) 若仍 404：
- 说明更可能是权限/网关策略问题；此时 **不要回写 inline**，退化为只回写总体 note（仍可引用 file:line + 代码片段）。
- 同时用 discussions 探针确认是否具备 discussions 权限：
```bash
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>/merge_requests/<MR_IID>/discussions?per_page=1" --output json
```

---

## 步骤 3.5（推荐）：效率优先的回写策略（可选去重）
本 skill 默认偏向**效率优先（B 模式）**：能回写就回写，inline 覆盖更多点。

- **默认行为**：直接回写 1 条 note + N 条 inline
- **可选去重（推荐在反复运行同一 MR 时启用）**：
  - 给每条 inline comment body 追加一个稳定 tag（例如 `<!-- cc-review:<hash> -->`）
  - 再次运行时先拉 discussions 搜索 tag，已存在则跳过

> 脚本支持：`glab_mr_writeback.py --dedupe-tag "cc-review:<hash>"`（只对 inline 去重；note 不去重）。

---

## 步骤 3.9（推荐）：回写前校验 review.json
在回写前，建议先校验 `review.json` 的 JSON 语法与结构，避免因少逗号/引号未闭合导致回写脚本直接失败：

```bash
python validate_review.py --review review.json
# 如需同时检查 inline 是否仍命中当前 MR 最新 diff hunk（提示潜在降级）
python validate_review.py --review review.json --context mr_review_out/context.json --check-diff warn
```

## 步骤 4：回写总体评论（MR note）
### 4.1 推荐：用脚本回写（避免 bash 多行转义问题）
- `glab_mr_writeback.py` 默认只预览；加 `--confirm` 才会写回。

### 4.2 直接用 glab（短文本可用；长多行不推荐）
```bash
GITLAB_HOST=<host> "<glab.exe>" mr note <MR_IID> -R <group>/<project> -m "<你的总体review markdown>"
```

### 4.3 更稳：把 note 写入文件再回写（减少引号/换行翻车）
> 若你的 glab 版本支持从文件读入（不同版本参数可能不同），优先用文件方式；不支持就退回脚本。

- 先生成 `note.md`（UTF-8）
- 再由 Python/脚本读取并调用 `glab mr note`（见 `glab_mr_writeback.py` 的实现建议）

建议总体评论包含：
- Blocking（阻断项）
- Non-blocking（建议项）
- 每条问题带链接（blob + sha + 行号范围）

---

## 步骤 5：回写 inline discussions（最稳方案：Python 逐条 POST）
### 5.1 为什么不用 bash 直接发
- 多行/反引号/`!` 容易触发 bash 历史展开或转义失败
- Windows 控制台编码导致 Python `text=True` 解码报错

### 5.2 生成一组 payload（推荐 jsonl，一行一个 JSON）
每条 payload 结构：
```json
{
  "body": "评论内容",
  "position": {
    "position_type": "text",
    "base_sha": "...",
    "start_sha": "...",
    "head_sha": "...",
    "new_path": "path/to/file",
    "new_line": 123
  }
}
```

### 5.3 Python 逐条调用 glab api（修复编码问题）
把下面脚本中的变量替换成你的值：

```python
import json, subprocess, sys

exe = r"D:/ProgramFiles/glab/glab.exe"
host = "<host>"
endpoint = "/projects/<PROJECT_ID>/merge_requests/<MR_IID>/discussions"

base_sha = "<base_sha>"
start_sha = "<start_sha>"
head_sha = "<head_sha>"

items = [
  {"new_path": "path/to/file", "new_line": 10, "body": "阻断：..."},
]

for it in items:
  cmd = [
    exe, "api", "--hostname", host, "--method", "POST", endpoint,
    "-F", f"body={it['body']}",
    "-F", "position[position_type]=text",
    "-F", f"position[base_sha]={base_sha}",
    "-F", f"position[start_sha]={start_sha}",
    "-F", f"position[head_sha]={head_sha}",
    "-F", f"position[new_path]={it['new_path']}",
    "-F", f"position[new_line]={it['new_line']}"
  ]
  r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  out = r.stdout.decode("utf-8", "replace")
  print(out)
  if r.returncode != 0:
    sys.exit(r.returncode)
```

---

## 常见故障与排障（最小证据）
### A) `glab: command not found`
- 结论：Claude Code Bash PATH 没包含 glab
- 处理：用绝对路径 `D:/.../glab.exe`

### B) `Unknown flag: --hostname`（在 mr 子命令）
- 结论：该子命令不支持 `--hostname`
- 处理：改用 `GITLAB_HOST=<host>` 或直接用 `glab api --hostname`

### C) `bash: ... command not found`（长评论/包含特殊字符）
- 结论：shell 转义/历史展开导致命令被截断
- 处理：inline 用 Python 逐条 POST；总体 note 尽量用单行 `-m`，必要时改为编辑器模式（不自动化）

### F) `JSONDecodeError`（review.json 语法错误）
- 结论：`review.json` 不是合法 JSON（缺逗号/引号未闭合/尾逗号等）
- 处理：先运行 `python validate_review.py --review review.json`，或直接运行 writeback 脚本查看带行列与上下文的友好定位信息

### D) `UnicodeDecodeError: gbk codec can't decode ...`
- 结论：Windows 默认编码导致 subprocess 文本解码失败
- 处理：`subprocess.run(..., stdout=PIPE, stderr=STDOUT)`，再 `decode('utf-8','replace')`

### E) `404 Not Found`（API）
- 先用 GET 探针确认 endpoint：
```bash
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>?simple=true" --output json
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>/merge_requests/<MR_IID>" --output json
"<glab.exe>" api --hostname <host> "/projects/<PROJECT_ID>/merge_requests/<MR_IID>/discussions?per_page=1" --output json
```
- 若 simple=true 才能访问项目，说明权限/接口策略限制，继续用 `?simple=true` 验证可见性。

---

## 最小模板（可复制替换）
- 总体评论：`glab mr note <iid> -R <repo> -m "..."`
- inline：`glab api POST /projects/<id>/merge_requests/<iid>/discussions` + `position[...]`

---

## 脚本化工具（减少重复命令 + 仅最后回写确认）
本目录提供两个脚本，把固定的命令行流程固化下来：

1) `glab_mr_fetch.py`：只读拉取 MR 信息与 diff（不回写）
- 输入：MR URL
- 输出：`diff.txt`、`context.json`（含 project_id 与 diff_refs）等

2) `glab_mr_writeback.py`：将 `review.json` 回写到 GitLab（note + inline）
- 默认只预览
- 只有传入 `--confirm` 才会真正回写（把确认点集中到最后一步）
- 回写前自动刷新最新 MR 版本和 diff_refs，避免使用过期的 diff_refs 导致 inline 失效
- 自动把 note 中的 `[file:line]` 转换为 GitLab blob 可点击链接
- inline 发送前自动校验 hunk 命中情况，未命中的自动降级到 note
- 支持 `--dedupe-tag` 去重，避免重复发相同评论

### 使用示例
```bash
python glab_mr_fetch.py --mr "https://<host>/<group>/<project>/-/merge_requests/<iid>" --out mr_review_out

# 生成模板 review.json（空白骨架 + inline 占位）
python glab_mr_review_draft.py --diff mr_review_out/diff.txt --out review.json

# 填充/调整 review.json 后先预览（不回写）：
python glab_mr_writeback.py --context mr_review_out/context.json --review review.json

# 最终确认后回写：
python glab_mr_writeback.py --context mr_review_out/context.json --review review.json --confirm
```

### review.json 格式
```json
{
  "note": "markdown...",
  "inline": [
    {"new_path": "path/to/file", "new_line": 123, "body": "评论 markdown..."}
  ]
}
```

