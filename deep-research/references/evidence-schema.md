# Evidence Schema

深度研究时先建立证据表，再写结论。可以使用 Markdown 表格，也可以使用 JSON。复杂研究优先 JSON，便于后续筛选和审计。

## JSON 结构

```json
{
  "research_question": "主研究问题",
  "generated_at": "YYYY-MM-DD",
  "scope": {
    "time_range": "研究时间范围",
    "region": "地域范围",
    "included": ["包含对象"],
    "excluded": ["排除对象"]
  },
  "subquestions": [
    {
      "id": "Q1",
      "question": "子问题",
      "status": "sufficient | partial | insufficient"
    }
  ],
  "evidence": [
    {
      "id": "E1",
      "claim": "证据支持或反驳的主张",
      "source": "URL、文件路径、论文、仓库或数据集",
      "source_title": "来源标题",
      "source_type": "official_docs | paper | news | blog | repository | financial_filing | regulation | local_file | dataset | other",
      "published_or_updated": "YYYY-MM-DD 或 unknown",
      "retrieved_at": "YYYY-MM-DD",
      "summary": "用自己的话概括证据",
      "direct_quote": "可选，短引用",
      "reliability": "high | medium | low",
      "supports": ["Q1"],
      "stance": "supports | contradicts | contextualizes",
      "limitations": "证据局限、偏见或适用范围"
    }
  ],
  "conflicts": [
    {
      "topic": "冲突主题",
      "sources": ["E1", "E2"],
      "analysis": "冲突原因和当前判断"
    }
  ],
  "gaps": [
    {
      "question": "仍缺证据的问题",
      "why_it_matters": "为什么影响结论",
      "next_search": "下一步可检索方向"
    }
  ]
}
```

## 可信度参考

- `high`: 官方文档、标准、论文、监管文件、财报、源代码、直接数据。
- `medium`: 权威媒体、专家机构报告、维护良好的技术博客、可信二手分析。
- `low`: 未注明来源的博客、论坛评论、营销材料、无法确认日期或作者的页面。

## 充分性参考

- 决策性结论：优先需要高可信来源。
- 当前事实：必须确认发布日期或更新时间。
- 争议性观点：至少列出双方证据。
- 成本、法律、医疗、金融、安全相关建议：需要更保守表达，并列出限制。
