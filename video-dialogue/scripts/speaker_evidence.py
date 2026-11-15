"""生成供说话人复核使用的声学证据和试听，不自动推断身份。"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audio', required=True, type=Path)
    p.add_argument('--segments', required=True, type=Path)
    p.add_argument('--model', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--threads', type=int, default=3)
    a = p.parse_args()
    import numpy as np
    import soundfile as sf
    import sherpa_onnx as so

    for path in [a.audio, a.segments, a.model]:
        if not path.is_file():
            p.error(f'输入文件不存在：{path}')
    rows = json.loads(a.segments.read_text(encoding='utf-8-sig'))
    if not isinstance(rows, list) or not 1 <= len(rows) <= 400:
        p.error('片段列表须有1至400项；大任务分批选择代表片段')
    info = sf.info(str(a.audio))
    if info.samplerate != 16000 or info.channels != 1:
        p.error('音频须为16kHz单声道')
    ids = set()
    for row in rows:
        key = row.get('id')
        if not isinstance(key, str) or not key.strip() or key in ids:
            p.error('片段id须为不重复的非空字符串')
        ids.add(key)
        if not isinstance(row.get('speaker'), str):
            p.error(f'{key} 缺少speaker标签')
        try:
            start, end = float(row['start']), float(row['end'])
        except (KeyError, TypeError, ValueError):
            p.error(f'{key} 时间无效')
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= info.duration + 0.001):
            p.error(f'{key} 时间超出音频范围')
        if end - start > 20:
            p.error(f'{key} 超过20秒，请拆成适合声纹比较的短窗口')
        row['start'], row['end'] = start, end
    if a.threads < 1:
        p.error('threads必须为正整数')
    if a.out.exists() and (not a.out.is_dir() or any(a.out.iterdir())):
        p.error('输出目录非空，请使用新的证据目录')
    a.out.mkdir(parents=True, exist_ok=True)
    clips = a.out / 'clips'
    clips.mkdir()
    config = so.SpeakerEmbeddingExtractorConfig(model=str(a.model.resolve()), num_threads=a.threads)
    if not config.validate():
        p.error('声纹模型配置无效')
    extractor = so.SpeakerEmbeddingExtractor(config)
    vectors, enriched = [], []
    for i, row in enumerate(rows):
        samples, sr = sf.read(str(a.audio), start=round(row['start']*16000),
                              stop=round(row['end']*16000), dtype='float32')
        filename = f'{i+1:04}.wav'
        sf.write(str(clips / filename), samples, sr, subtype='PCM_16')
        item = dict(row, clip=f'clips/{filename}', vector_index=None, quality='too_short')
        if len(samples) >= 24000:
            stream = extractor.create_stream()
            stream.accept_waveform(sample_rate=sr, waveform=samples)
            stream.input_finished()
            if extractor.is_ready(stream):
                v = np.asarray(extractor.compute(stream), dtype=np.float32)
                length = float(np.linalg.norm(v))
                if np.isfinite(v).all() and length > 1e-9:
                    item.update(vector_index=len(vectors), quality='not_manually_checked')
                    vectors.append(v / length)
        enriched.append(item)
        print(f'声纹证据 {i+1}/{len(rows)}', flush=True)
    matrix = np.stack(vectors) if vectors else np.empty((0, 0), dtype=np.float32)
    pairs = []
    for i, left in enumerate(enriched):
        for right in enriched[i+1:]:
            li, ri = left['vector_index'], right['vector_index']
            score = float(matrix[li] @ matrix[ri]) if li is not None and ri is not None else None
            pairs.append({'left_id': left['id'], 'right_id': right['id'], 'similarity': score,
                          'overlap_seconds': max(0, min(left['end'],right['end'])-max(left['start'],right['start']))})
    bundle = {'schema_version': 1,
              'audio': {'path': str(a.audio.resolve()), 'sha256': digest(a.audio), 'duration': info.duration},
              'model': {'path': str(a.model.resolve()), 'sha256': digest(a.model)},
              'segments_sha256': digest(a.segments), 'segments': enriched, 'pairs': pairs,
              'note': '相似度不是正确率；本工具未判断身份或性别，短片段可能无向量。'}
    np.savez_compressed(a.out/'vectors.npz', vectors=matrix)
    (a.out/'evidence.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
    print(a.out/'evidence.json')


if __name__ == '__main__':
    main()
