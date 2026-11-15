# LLM 辅助统一说话人

声纹模型回答声音是否相似；LLM 整理证据、定位矛盾、提出合并或拆分。纯文本 LLM 无法从文字恢复声音；音频多模态模型也需要校验，不能假定优于专门声纹模型。

## 判断依据

- 看多段清晰发言的相似度分布，不只看最高分；短句、噪声和重叠降低证据权重。
- 对照用户确认参考，以及与其他候选人的差距；数值不能跨模型直接比较。
- 同时存在两个不同声音是反证，但自动时间重叠可能是分段错误，须先检查。
- 原组内部差异大时，先拆混入片段，再考虑合并。
- 用户确认可记为身份依据；话题、称呼、角色习惯只帮助找候选。会议室设备名不是个人名。
- 唯一女性条件用于用户确认的参考人物，不用于自动性别分类或跨会议身份识别。

阈值不能直接照搬旧会议。有确认的同人、异人片段时检查本场分布；缺少标注则保守使用并声明未校准。扩展参考只能用多个高相似度、无冲突的清晰窗口，保留原始参考，最多扩展一轮后复核，不反复用弱匹配自我强化。

## 证据包

准备选定片段 JSON，例如：

```json
[
  {"id":"ref-a", "start":20.0, "end":25.0, "speaker":"参考A", "confirmed_reference":true, "text":"用户确认的发言"},
  {"id":"seg-002", "start":90.0, "end":95.0, "speaker":"原组7", "text":"待核对的发言"}
]
```

```powershell
& $runtime "$skillDir\scripts\speaker_evidence.py" --audio "$jobDir\audio.wav" --segments "$jobDir\review-segments.json" --model "$modelDir\speaker-hf.onnx" --out "$jobDir\review-01"
```

输出 `evidence.json`（输入 SHA256、片段、声纹分数、交叠提示）、向量和试听 WAV。先选每组 2–3 段清晰代表发言及全部参考，不把整场音频或海量矩阵塞入上下文；混组则追加片段。

给 LLM 的复核任务：

> 依据证据包和用户确认参考，找可能同人的片段。列出声学支持、反对证据、文字线索和不足。文本线索不能单独支持合并。未读取音频不声称已听过。每次修改指定片段 ID、统一标签、依据和状态，不修改正文或时间。证据不足则待确认，或提出最少的关键试听问题。

## 应用及审计

`apply_speaker_map.py` 接受实际要修改的片段列表。全会议处理时先将所有分段规范化；确认原组纯净后可显式列出其各段 ID。不能仅因两个代表片段相似就给整个未经检查的原组背书。

```json
{
  "decisions":[
    {"segment_ids":["seg-002"], "target_speaker":"说话人1", "status":"acoustic_match", "basis":"acoustic", "evidence_ids":["ref-a","seg-002"], "reason":"参考和代表片段支持匹配；未发现反对证据，仍属自动复核"}
  ]
}
```

- `status`：`user_confirmed`、`acoustic_match`、`uncertain`。
- `basis`：`user_confirmation`、`acoustic`、`text_only`。纯文字依据只接受 `uncertain`。
- 用户确认需在 `reason` 引述或概括确认内容，不能伪造用户确认。
- 声学匹配必须引用证据包中目标片段和其他参考。脚本验证证据存在及目标一致，不替 LLM 判断相似度是否足够，也不证明身份准确。

```powershell
& $runtime "$skillDir\scripts\apply_speaker_map.py" --segments "$jobDir\review-segments.json" --decisions "$jobDir\review-decisions.json" --evidence "$jobDir\review-01\evidence.json" --out "$jobDir\reviewed-01"
```

输出 `segments-reviewed.json` 和 `speaker-map-audit.json`；时间、正文和 ID 不变，另存原标签、统一标签及状态。`uncertain` 自动加“待确认”；已有输出拒绝覆盖。新一轮用新目录，保留回退依据。

检查修改进入最终文字稿，而不只停在审计表。大规模合并抽查早、中、晚多个片段；不确定内容列出时间和试听。说明哪些已统一、哪些未确定，不能仅报组数减少。
