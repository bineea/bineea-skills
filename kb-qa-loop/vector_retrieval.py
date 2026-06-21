#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向量库 HTTPS 检索与响应标准化。

特性：
- 通过环境变量读取 URL、鉴权头、API Key 等敏感信息（不会写入明文密钥）
- 兼容响应中 metadata 字段为 JSON 字符串的情况，并尽量做解析与容错
- 输出标准化 JSON：
  {
    "items": [
      {
        "id": <nodeId>,
        "score": <number>,
        "text": <string>,
        "metadata": <object>,
        "source": {
          "docId": ...,
          "docName": ...,
          "fileType": ...,
          "origin_path": ...
        }
      }
    ],
    "raw": <raw_response_object>
  }

最小 CLI：
  python vector_retrieval.py --query "..." --topk 6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    v = os.environ.get(name, default)
    if required and (v is None or str(v).strip() == ""):
        raise RuntimeError(f"缺少必要环境变量：{name}")
    return v


def _maybe_json_loads(s: Any) -> Any:
    """若 s 是 JSON 字符串则解析，否则原样返回；解析失败时返回带错误信息的对象。"""
    if not isinstance(s, str):
        return s
    t = s.strip()
    if not t:
        return s
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            return json.loads(t)
        except Exception as e:
            return {"_raw": s, "_parse_error": str(e)}
    return s


def _to_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _fetch_access_token(timeout_s: int) -> Optional[str]:
    """按需获取 access_token。

    通过环境变量提供 token endpoint 与账号信息：
    - VECTOR_TOKEN_URL
    - VECTOR_TOKEN_USERNAME
    - VECTOR_TOKEN_PASSWORD

    使用 X-API-KEY（VECTOR_API_KEY）请求 token，返回 Bearer access_token。
    """

    token_url = _env("VECTOR_TOKEN_URL")
    username = _env("VECTOR_TOKEN_USERNAME")
    password = _env("VECTOR_TOKEN_PASSWORD")
    api_key = _env("VECTOR_API_KEY")

    if not token_url or not username or not password or not api_key:
        return None

    data = urllib.parse.urlencode(
        {
            "username": username,
            "password": password,
        }
    ).encode("utf-8")

    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    req = urllib.request.Request(url=token_url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(body)
            if isinstance(obj, dict):
                access_token = obj.get("access_token")
                token_type = obj.get("token_type") or "Bearer"
                if access_token and isinstance(access_token, str):
                    return f"{token_type} {access_token}".strip()
            raise RuntimeError("token 响应缺少 access_token")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        preview = _safe_error_body_preview(body)
        detail = f"：{preview}" if preview else ""
        raise RuntimeError(f"HTTP {e.code} 获取 token 失败{detail}") from e
    except urllib.error.URLError:
        raise RuntimeError("网络调用失败")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"token 响应不是合法 JSON：{e}") from e


def _build_headers(authorization: Optional[str] = None) -> Dict[str, str]:
    """从环境变量构造请求头。"""
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
    }

    if authorization:
        headers["Authorization"] = authorization.strip()

    x_api_key = _env("VECTOR_API_KEY")
    if x_api_key:
        headers["X-API-KEY"] = x_api_key

    km_verse_key = _env("KM_VERSE_KEY")
    if km_verse_key:
        headers["km-verse-key"] = km_verse_key

    # 可选：额外 header（JSON 字符串），例如：{"X-Trace-Id":"..."}
    extra = _env("VECTOR_EXTRA_HEADERS")
    if extra:
        extra_obj = _maybe_json_loads(extra)
        if isinstance(extra_obj, dict):
            for k, v in extra_obj.items():
                if v is None:
                    continue
                headers[str(k)] = str(v)

    return headers


def build_request_payload(query: str, topk: int) -> Dict[str, Any]:
    """根据样例构造检索 payload，并使用环境变量覆盖默认值。"""

    project_id = _to_int(_env("VECTOR_PROJECT_ID", required=True), 0)
    index_mode = _env("VECTOR_INDEX_MODE", "hybrid") or "hybrid"

    # 保护性处理：不让 topk 变成 0/负数导致服务端异常或空结果
    safe_topk = topk if isinstance(topk, int) and topk > 0 else 1

    # relation 允许通过 JSON 环境变量整体传入；否则使用 KB_ID / TAG_EXPRESSION 组装最小结构
    relation_env = _env("VECTOR_RELATION_JSON")
    if relation_env:
        relation = _maybe_json_loads(relation_env)
        if not isinstance(relation, list):
            raise RuntimeError("VECTOR_RELATION_JSON 必须是 JSON 数组")
    else:
        kb_ids_env = _env("VECTOR_KB_IDS")  # 逗号分隔
        tag_expr = _env("VECTOR_TAG_EXPRESSION", "") or ""

        kb_ids: List[int] = []
        if kb_ids_env:
            for part in kb_ids_env.split(","):
                part = part.strip()
                if not part:
                    continue
                kb_ids.append(_to_int(part, 0))

        # 若未提供 KB 列表，则 payload 仍可尝试（交由服务端校验）
        relation = [
            {
                "knowledgeBaseId": kb_id,
                "docIds": [],
                "filter": "",
                "tags": [],
                "tagExpression": tag_expr,
            }
            for kb_id in kb_ids
        ]

    payload: Dict[str, Any] = {
        "projectId": project_id,
        "relation": relation,
        "query": query,
        "indexMode": index_mode,
        "similarityTopK": safe_topk,
        # 下列字段按样例给默认值，可通过 env 覆盖
        "rerank": _to_int(_env("VECTOR_RERANK", "100"), 100),
        "contextCompletion": _to_int(_env("VECTOR_CONTEXT_COMPLETION", "1"), 1),
        "filenameCompletion": _to_int(_env("VECTOR_FILENAME_COMPLETION", "1"), 1),
        "score": _to_int(_env("VECTOR_SCORE_THRESHOLD", "20"), 20),
        "expandDocSummary": (_env("VECTOR_EXPAND_DOC_SUMMARY", "true").lower() == "true"),
    }

    # glossaryIds 可选，JSON 数组或逗号分隔
    glossary = _env("VECTOR_GLOSSARY_IDS")
    if glossary:
        gl = _maybe_json_loads(glossary)
        if isinstance(gl, list):
            payload["glossaryIds"] = gl
        else:
            payload["glossaryIds"] = [x.strip() for x in glossary.split(",") if x.strip()]

    return payload


def _safe_error_body_preview(body: str, max_len: int = 512) -> str:
    """截断错误响应体，避免泄露敏感信息或刷屏。"""

    if not body:
        return ""

    text = body.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…(已截断)"


def http_post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout_s: int = 30) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        preview = _safe_error_body_preview(body)
        detail = f"：{preview}" if preview else ""
        raise RuntimeError(f"HTTP {e.code} 调用失败{detail}") from e
    except urllib.error.URLError:
        # 避免在错误信息中拼接潜在包含敏感信息的 URL/headers
        raise RuntimeError("网络调用失败")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"响应不是合法 JSON：{e}") from e


def normalize_vector_response(raw: Any) -> Dict[str, Any]:
    """把原始响应标准化为统一结构。"""
    items: List[Dict[str, Any]] = []

    # 样例：{"code":200,"message":"success","result":[...],"requestId":"..."}
    results = None
    if isinstance(raw, dict):
        results = raw.get("result")

    if isinstance(results, list):
        for r in results:
            if not isinstance(r, dict):
                continue

            node_id = r.get("nodeId")
            score = _to_float(r.get("score"), 0.0)
            text = r.get("text")

            metadata_raw = r.get("metadata")
            metadata_obj = _maybe_json_loads(metadata_raw)
            if not isinstance(metadata_obj, dict):
                metadata_obj = {"_raw": metadata_raw}

            # source 字段：优先取 metadata 中 docId/origin_path 等；同时兼容顶层 docId/docName/fileType
            doc_id = metadata_obj.get("docId") or r.get("docId")
            doc_name = r.get("docName") or metadata_obj.get("file_name") or metadata_obj.get("docName")
            file_type = r.get("fileType") or metadata_obj.get("doc_type") or metadata_obj.get("fileType")
            origin_path = (
                metadata_obj.get("origin_path")
                or metadata_obj.get("orign_path")
                or metadata_obj.get("url")
                or r.get("origin_path")
                or r.get("orign_path")
            )

            items.append(
                {
                    "id": node_id,
                    "score": score,
                    "text": text,
                    "metadata": metadata_obj,
                    "source": {
                        "docId": doc_id,
                        "docName": doc_name,
                        "fileType": file_type,
                        "origin_path": origin_path,
                    },
                }
            )

    return {"items": items, "raw": raw}


def retrieve(query: str, topk: int) -> Dict[str, Any]:
    url = _env("VECTOR_API_URL", required=True)
    timeout_s = _to_int(_env("VECTOR_TIMEOUT_S", "30"), 30)

    # Authorization 优先级：若配置了 token endpoint，则先取 access_token；否则回退使用 AUTH_TOKEN。
    authorization = None
    try:
        authorization = _fetch_access_token(timeout_s=timeout_s)
    except Exception as e:
        raise RuntimeError(f"获取 token 失败：{e}") from e

    if not authorization:
        authorization = _env("AUTH_TOKEN")

    headers = _build_headers(authorization=authorization)
    payload = build_request_payload(query=query, topk=topk)

    raw = http_post_json(url=url, headers=headers, payload=payload, timeout_s=timeout_s)
    if isinstance(raw, dict) and raw.get("code") is not None and raw.get("code") != 200:
        msg = raw.get("message") or raw.get("msg") or "上游返回非成功状态"
        raise RuntimeError(f"上游返回失败 code={raw.get('code')} message={msg}")
    return normalize_vector_response(raw)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="向量库检索（HTTPS）并输出标准化 JSON")
    p.add_argument("--query", required=True, help="检索问题/查询文本")
    p.add_argument("--topk", type=int, default=6, help="返回条数")
    p.add_argument("--pretty", action="store_true", help="美化 JSON 输出")
    args = p.parse_args(argv)

    try:
        out = retrieve(query=args.query, topk=args.topk)
        if args.pretty:
            sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0
    except Exception as e:
        # 错误也用 JSON 便于主 skill 统一处理
        err = {"error": str(e)}
        sys.stdout.write(json.dumps(err, ensure_ascii=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
