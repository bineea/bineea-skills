#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保守型 sufficiency judge。

输入 JSON：
{
  "question": "...",
  "clarifications": [{"question": "...", "user_answer": "..."}] 或 ["..."],
  "asked_questions": ["..."],
  "items": [{"id": "...", "text": "...", "metadata": {"_compact": {...}}, "source": {...}}]
}

输出严格 JSON：
{"sufficient": boolean, "reason": string, "clarifying_questions": string[], "query_rewrite": string}

设计目标：
- 提供可直接调用的 judge 工具，避免执行流程卡在“只有 prompt，没有脚本”。
- 宁可保守追问，也不要在适用范围、地区、人群、时间口径不明时放行。
- 不依赖外部包，不调用 LLM。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


CATEGORY_PATTERNS = {
    "地区/适用地": re.compile(r"北京|上海|广州|深圳|杭州|成都|京外|当地|各地|地区|地域|城市|省|市|境内|境外|所在地"),
    "适用对象/人群": re.compile(r"正式|实习|外包|劳务派遣|兼职|全职|员工|员工类型|人群|对象|签约主体|合同主体|供应商|客户"),
    "时间/版本口径": re.compile(r"自.*起|截至|最新|修订|版本|生效|失效|日期|年度|年份|202\d|19\d\d|20\d\d|目前|当前"),
    "制度/政策口径": re.compile(r"政策|制度|规定|办法|流程|口径|标准|细则|以.*为准|按.*执行|参照|法定|公司"),
    "条件/资格限制": re.compile(r"适用|范围|条件|前提|资格|限制|例外|除外|须|需|必须|满足|不适用|不同|差异"),
}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        err = {
            "sufficient": False,
            "reason": f"judge 工具参数错误：{message}",
            "clarifying_questions": ["请检查 judge 命令参数；推荐使用 --retrieve-query，或用 --input - 从 stdin 传入完整 JSON。"],
            "query_rewrite": "",
        }
        sys.stdout.write(json.dumps(err, ensure_ascii=False, separators=(",", ":")) + "\n")
        raise SystemExit(0)


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_retrieve_module() -> Any:
    path = _script_dir() / "kb_retrieve_compact.py"
    spec = importlib.util.spec_from_file_location("kb_retrieve_compact", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 compact 检索脚本：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_loads_value(value: str, field_name: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{field_name} 不是合法 JSON：{exc}") from exc


def _read_json(path: Optional[str]) -> Dict[str, Any]:
    if path and path != "-":
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise RuntimeError("没有收到 judge 输入 JSON")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"输入不是合法 JSON：{exc}") from exc
    if not isinstance(obj, dict):
        raise RuntimeError("输入 JSON 必须是对象")
    return obj


def _build_input_from_args(args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    if args.retrieve_query:
        retrieve_module = _load_retrieve_module()
        retrieve_args = Namespace(
            query=args.retrieve_query,
            topk=args.topk,
            max_items=args.max_items,
            max_text_chars=args.max_text_chars,
            max_total_text_chars=args.max_total_text_chars,
            dedupe_source=args.dedupe_source,
            cache_ttl_s=args.cache_ttl_s,
            no_cache=args.no_cache,
            base_retrieval=args.base_retrieval,
            include_raw_preview=False,
            raw_preview_chars=1000,
            pretty=False,
        )
        retrieval_result = retrieve_module.retrieve_compact(retrieve_args)
        clarifications: Any = []
        if args.clarifications_json:
            clarifications = _json_loads_value(args.clarifications_json, "--clarifications-json")
        asked_questions: Any = []
        if args.asked_questions_json:
            asked_questions = _json_loads_value(args.asked_questions_json, "--asked-questions-json")
        return {
            "question": args.question or args.retrieve_query,
            "clarifications": clarifications,
            "asked_questions": asked_questions,
            "items": retrieval_result.get("items", []),
        }

    if not args.question:
        return None

    items: Any = []
    if args.items_json:
        obj = _json_loads_value(args.items_json, "--items-json")
        if isinstance(obj, dict) and isinstance(obj.get("items"), list):
            items = obj.get("items")
        elif isinstance(obj, list):
            items = obj
        else:
            raise RuntimeError("--items-json 必须是 items 数组，或包含 items 数组的对象")
    elif args.items_file:
        obj = _read_json(args.items_file)
        if isinstance(obj.get("items"), list):
            items = obj.get("items")
        else:
            raise RuntimeError("--items-file 必须指向包含 items 数组的 JSON 文件")

    clarifications: Any = []
    if args.clarifications_json:
        clarifications = _json_loads_value(args.clarifications_json, "--clarifications-json")

    asked_questions: Any = []
    if args.asked_questions_json:
        asked_questions = _json_loads_value(args.asked_questions_json, "--asked-questions-json")

    return {
        "question": args.question,
        "clarifications": clarifications,
        "asked_questions": asked_questions,
        "items": items,
    }


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_as_text(v) for v in value)
    if isinstance(value, dict):
        parts = []
        for key in ("question", "user_answer", "answer", "text"):
            if key in value:
                parts.append(_as_text(value.get(key)))
        return "\n".join(parts)
    return str(value)


def _combined_clarification_text(clarifications: Any) -> str:
    if not isinstance(clarifications, list):
        return _as_text(clarifications)
    return "\n".join(_as_text(item) for item in clarifications)


def _categories_in_text(text: str) -> Set[str]:
    found: Set[str] = set()
    for category, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(text):
            found.add(category)
    return found


def _items_text(items: Iterable[Dict[str, Any]]) -> str:
    chunks = []
    for item in items:
        chunks.append(_as_text(item.get("text")))
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            compact = metadata.get("_compact")
            if isinstance(compact, dict):
                signals = compact.get("scope_signals")
                chunks.append(_as_text(signals))
    return "\n".join(chunks)


def _has_truncated_scope_signal(items: Iterable[Dict[str, Any]]) -> bool:
    for item in items:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        compact = metadata.get("_compact")
        if not isinstance(compact, dict):
            continue
        if compact.get("truncated") and compact.get("scope_signals"):
            return True
    return False


def _filter_new_questions(candidates: List[str], asked_questions: Any) -> List[str]:
    asked_text = _as_text(asked_questions)
    out: List[str] = []
    for question in candidates:
        normalized = question.strip()
        if not normalized:
            continue
        if normalized in asked_text:
            continue
        if normalized not in out:
            out.append(normalized)
    return out[:2]


def _questions_for_missing(missing: List[str]) -> List[str]:
    questions = []
    for category in missing:
        if category == "地区/适用地":
            questions.append("请确认这次问题适用的地区或城市是什么？")
        elif category == "适用对象/人群":
            questions.append("请确认这次问题适用的对象或人员类型是什么？")
        elif category == "时间/版本口径":
            questions.append("请确认你要按哪个时间点或政策版本口径来判断？")
        elif category == "制度/政策口径":
            questions.append("请确认你希望按公司制度、当地规定，还是其他指定政策口径来判断？")
        elif category == "条件/资格限制":
            questions.append("请补充会影响适用条件或资格限制的关键信息。")
    return questions


def judge(obj: Dict[str, Any]) -> Dict[str, Any]:
    question = _as_text(obj.get("question") or obj.get("original_question")).strip()
    clarifications = obj.get("clarifications", [])
    asked_questions = obj.get("asked_questions", [])
    items = obj.get("items", [])
    if not isinstance(items, list):
        items = []

    clarification_text = _combined_clarification_text(clarifications)
    known_context = f"{question}\n{clarification_text}"
    evidence_text = _items_text([item for item in items if isinstance(item, dict)])

    if not question:
        return {
            "sufficient": False,
            "reason": "缺少用户原始问题，无法判断证据是否足够。",
            "clarifying_questions": ["请提供你要查询的原始问题。"],
            "query_rewrite": "",
        }

    if not items:
        return {
            "sufficient": False,
            "reason": "当前没有可用的知识库证据，不能给出可靠结论。",
            "clarifying_questions": _filter_new_questions(["请补充更具体的查询对象、范围或关键词。"], asked_questions),
            "query_rewrite": f"{question} 需要补齐查询对象、范围或关键词",
        }

    evidence_categories = _categories_in_text(evidence_text)
    known_categories = _categories_in_text(known_context)
    missing = sorted(evidence_categories - known_categories)

    # 截断过且出现范围信号时，要特别保守；否则可能裁掉“仅适用于/不适用于”的关键句。
    truncated_scope_risk = _has_truncated_scope_signal([item for item in items if isinstance(item, dict)])
    if truncated_scope_risk:
        for category in ("地区/适用地", "适用对象/人群", "时间/版本口径", "条件/资格限制"):
            if category in evidence_categories and category not in known_categories and category not in missing:
                missing.append(category)

    if missing:
        questions = _filter_new_questions(_questions_for_missing(missing), asked_questions)
        if not questions:
            questions = ["请补充会影响适用范围或结论口径的关键信息。"]
        return {
            "sufficient": False,
            "reason": "证据中出现适用范围、对象、时间或口径信号，但用户问题和已澄清信息尚未覆盖这些关键条件。",
            "clarifying_questions": questions,
            "query_rewrite": f"{question}；仍需补齐：{'、'.join(missing)}",
        }

    if truncated_scope_risk:
        question_text = "请确认是否存在会影响结论适用范围的地区、人群、时间或资格条件。"
        return {
            "sufficient": False,
            "reason": "证据文本被截断且存在适用范围信号，为避免遗漏限制条件，需要先确认关键适用条件。",
            "clarifying_questions": _filter_new_questions([question_text], asked_questions),
            "query_rewrite": f"{question}；确认地区、人群、时间、资格条件后再检索",
        }

    return {
        "sufficient": True,
        "reason": "当前 compact items 提供了可用证据，且未检测到尚未覆盖的关键适用范围、对象、时间或口径缺口。",
        "clarifying_questions": [],
        "query_rewrite": question,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = JsonArgumentParser(description="保守型 KB sufficiency judge，读取 JSON 并输出严格 JSON 决策对象")
    parser.add_argument("--input", help="输入 JSON 文件；传 - 或省略时从 stdin 读取")
    parser.add_argument("--retrieve-query", help="先运行 compact 检索，再直接 judge；推荐主路径，避免在 shell 中搬运 JSON")
    parser.add_argument("--topk", type=int, default=10, help="--retrieve-query 模式下的远程检索条数")
    parser.add_argument("--max-items", type=int, default=10, help="--retrieve-query 模式下输出证据条数上限")
    parser.add_argument("--max-text-chars", type=int, default=2200, help="--retrieve-query 模式下每条 text 字符数上限")
    parser.add_argument("--max-total-text-chars", type=int, default=18000, help="--retrieve-query 模式下所有 text 总字符数上限")
    parser.add_argument("--dedupe-source", action=argparse.BooleanOptionalAction, default=False, help="--retrieve-query 模式下按来源去重")
    parser.add_argument("--cache-ttl-s", type=int, default=3600, help="--retrieve-query 模式下缓存 TTL 秒数")
    parser.add_argument("--no-cache", action="store_true", help="--retrieve-query 模式下禁用缓存")
    parser.add_argument(
        "--base-retrieval",
        default="C:/Users/guowb1/.claude/skills/kb-qa-loop/vector_retrieval.py",
        help="--retrieve-query 模式下原始 vector_retrieval.py 路径",
    )
    parser.add_argument("--question", help="直接传入用户原始问题；使用该参数时可配合 --items-json 或 --items-file")
    parser.add_argument("--items-json", help="直接传入 items 数组 JSON，或包含 items 字段的检索结果 JSON")
    parser.add_argument("--items-file", help="传入包含 items 字段的检索结果 JSON 文件")
    parser.add_argument("--clarifications-json", help="clarifications 数组 JSON，默认 []")
    parser.add_argument("--asked-questions-json", help="asked_questions 数组 JSON，默认 []")
    parser.add_argument("--pretty", action="store_true", help="美化 JSON 输出")
    args = parser.parse_args(argv)

    try:
        obj = _build_input_from_args(args)
        if obj is None:
            obj = _read_json(args.input)
        result = judge(obj)
        if args.pretty:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        err = {
            "sufficient": False,
            "reason": f"judge 工具执行失败：{exc}",
            "clarifying_questions": ["请检查 judge 输入 JSON 是否包含 question、items、clarifications 和 asked_questions。"],
            "query_rewrite": "",
        }
        sys.stdout.write(json.dumps(err, ensure_ascii=False, separators=(",", ":")) + "\n")
        # 始终返回 0，避免 Claude Code 把严格 JSON 决策对象包装成 Bash Error。
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
