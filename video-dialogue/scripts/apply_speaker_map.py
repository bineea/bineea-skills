"""按明确的逐段复核决策统一标签，保留原文、时间和映射审计。"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def apply_decisions(rows, decisions, evidence=None):
    if not isinstance(rows, list) or not isinstance(decisions, list):
        raise ValueError('segments和decisions必须是数组')
    original = {}
    for row in rows:
        key = row.get('id')
        if not isinstance(key, str) or not key.strip() or key in original:
            raise ValueError('片段id必须唯一且非空')
        if not isinstance(row.get('speaker'), str):
            raise ValueError(f'{key}缺少speaker')
        if not all(isinstance(row.get(k),(int,float)) and math.isfinite(row[k]) for k in ['start','end']):
            raise ValueError(f'{key}时间无效')
        if not 0 <= row['start'] < row['end']:
            raise ValueError(f'{key}时间区间无效')
        original[key] = row
    out = copy.deepcopy(rows)
    updated = {r['id']:r for r in out}
    evidence_rows = {r['id']:r for r in (evidence or {}).get('segments',[])}
    pairs = {(p['left_id'],p['right_id']):p for p in (evidence or {}).get('pairs',[])}
    seen, audit = set(), []
    for decision in decisions:
        ids = decision.get('segment_ids')
        target = decision.get('target_speaker')
        status, basis = decision.get('status'), decision.get('basis')
        reason = decision.get('reason')
        refs = decision.get('evidence_ids',[])
        if not isinstance(ids,list) or not ids or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):
            raise ValueError('每条决策必须显式列出不重复的segment_ids')
        if not isinstance(target,str) or not target.strip() or not isinstance(reason,str) or not reason.strip():
            raise ValueError('统一标签和修改依据不能为空')
        if status not in {'user_confirmed','acoustic_match','uncertain'}:
            raise ValueError('复核状态无效')
        if basis not in {'user_confirmation','acoustic','text_only'}:
            raise ValueError('依据类型无效')
        if (status=='user_confirmed' and basis!='user_confirmation') or (status=='acoustic_match' and basis!='acoustic'):
            raise ValueError('复核状态与依据不一致')
        if basis=='text_only' and status!='uncertain':
            raise ValueError('纯文本依据不能确定合并身份')
        if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs):
            raise ValueError('evidence_ids必须是字符串数组')
        if any(r not in evidence_rows for r in refs):
            raise ValueError('引用了不存在的声纹证据id')
        label = target.strip()
        if status=='uncertain' and '待确认' not in label:
            label += '（待确认）'
        for key in ids:
            if key not in original or key in seen:
                raise ValueError(f'未知或重复修改的片段：{key}')
            if status=='acoustic_match':
                if key not in refs:
                    raise ValueError(f'{key}未引用本段声纹证据')
                item=evidence_rows[key]
                if any(item.get(k)!=original[key].get(k) for k in ['start','end','text']):
                    raise ValueError(f'{key}声纹证据与待修改片段不一致')
                supports=[]
                for ref in refs:
                    if ref==key:
                        continue
                    pair=pairs.get((key,ref),pairs.get((ref,key)))
                    if pair and isinstance(pair.get('similarity'),(int,float)) and math.isfinite(pair['similarity']):
                        # 重叠窗口可能只是同一份音频，不能当成独立声纹支持。
                        if pair.get('overlap_seconds',0)==0:
                            supports.append(pair)
                if not supports:
                    raise ValueError(f'{key}没有独立、不重叠的声纹比较证据')
            seen.add(key)
            row=updated[key]
            row.setdefault('original_speaker',original[key]['speaker'])
            row['speaker']=label
            row['speaker_review_status']=status
            audit.append({'segment_id':key,'before':original[key]['speaker'],'after':label,
                          'status':status,'basis':basis,'evidence_ids':refs,'reason':reason})
    for old,new in zip(rows,out):
        if any(old.get(k)!=new.get(k) for k in ['id','start','end','text']):
            raise AssertionError('正文或时间被意外修改')
    return out,audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--segments',required=True,type=Path)
    p.add_argument('--decisions',required=True,type=Path)
    p.add_argument('--evidence',type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    try:
        data=load(a.decisions)
        out,audit=apply_decisions(load(a.segments),data['decisions'],load(a.evidence) if a.evidence else None)
        names=['segments-reviewed.json','speaker-map-audit.json']
        if any((a.out/name).exists() for name in names):
            p.error('输出已存在，请使用新的复核目录')
        a.out.mkdir(parents=True,exist_ok=True)
        (a.out/names[0]).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'source_sha256':hashlib.sha256(a.segments.read_bytes()).hexdigest(),
                'decisions_sha256':hashlib.sha256(a.decisions.read_bytes()).hexdigest(),
                'evidence_sha256':hashlib.sha256(a.evidence.read_bytes()).hexdigest() if a.evidence else None,
                'modified_segments':len(audit),'text_and_times_preserved':True,'changes':audit}
        (a.out/names[1]).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'已统一{len(audit)}个片段，正文和时间保持不变：{a.out}')
    except (ValueError,KeyError,TypeError,OSError) as exc:
        p.error(str(exc))


if __name__=='__main__':
    main()
