"""在本地转写音频、分离说话人，并生成可核对的对话稿。"""
from pathlib import Path
import json
import argparse
import time

MODELS = None
ROOT = None
NUM_SPEAKERS = -1
THRESHOLD = 0.5

def save(name, data):
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def transcribe():
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    model = WhisperModel(str(MODELS / "whisper-small"), device="cpu", compute_type="int8", cpu_threads=10)
    pipeline = BatchedInferencePipeline(model=model)
    import soundfile as sf
    audio, sample_rate = sf.read(str(ROOT / "audio.wav"), dtype="float32")
    assert sample_rate == 16000
    segments, info = pipeline.transcribe(audio, batch_size=8, beam_size=5, vad_filter=True, word_timestamps=True)
    print(f"语言：{info.language}，概率：{info.language_probability:.3f}", flush=True)
    save("language.json", {"language": info.language, "probability": info.language_probability})
    with (ROOT / "transcript.jsonl").open("w", encoding="utf-8") as out:
        for s in segments:
            out.write(json.dumps({"start": s.start, "end": s.end, "text": s.text, "avg_logprob": s.avg_logprob, "words": [{"start": w.start, "end": w.end, "text": w.word, "probability": w.probability} for w in s.words or []]}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"转写进度 {s.end / info.duration:.1%}，{s.end:.1f}/{info.duration:.1f} 秒", flush=True)

def diarize():
    import sherpa_onnx as so
    import soundfile as sf
    audio, sr = sf.read(str(ROOT / "audio.wav"), dtype="float32")
    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx")), num_threads=6),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=str(MODELS / "speaker-hf.onnx"), num_threads=6),
        clustering=so.FastClusteringConfig(num_clusters=NUM_SPEAKERS, threshold=THRESHOLD),
        min_duration_on=0.3, min_duration_off=0.5)
    assert config.validate(), "说话人模型配置无效"
    sd = so.OfflineSpeakerDiarization(config)
    assert sr == sd.sample_rate
    last = [0.0]
    def progress(done, total):
        if time.time() - last[0] > 20:
            print(f"说话人分离进度 {done / total:.1%}", flush=True)
            last[0] = time.time()
        return 0
    result = sd.process(audio, callback=progress).sort_by_start_time()
    save("speakers.json", [{"start": r.start, "end": r.end, "speaker": r.speaker} for r in result])
    print(f"说话人分离完成，得到 {len(set(r.speaker for r in result))} 个候选声纹组（需要人工校对）", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地转写或说话人初步分离；工作目录内须有16kHz单声道audio.wav")
    parser.add_argument("action", choices=["transcribe", "diarize"])
    parser.add_argument("--models-dir", required=True, type=Path, help="本地模型目录")
    parser.add_argument("--work-dir", required=True, type=Path, help="本次会议的独立工作目录")
    parser.add_argument("--num-speakers", type=int, default=-1, help="已确认人数，-1表示自动聚类")
    parser.add_argument("--threshold", type=float, default=0.5, help="自动聚类阈值，须按录音校对")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖本步骤已有输出")
    args = parser.parse_args()
    ROOT = args.work_dir.resolve()
    MODELS = args.models_dir.resolve()
    needed = ["whisper-small/model.bin"] if args.action == "transcribe" else ["speaker-hf.onnx", "sherpa-onnx-pyannote-segmentation-3-0/model.onnx"]
    if any(not (MODELS / name).is_file() for name in needed):
        parser.error("模型文件缺失，请检查--models-dir")
    NUM_SPEAKERS, THRESHOLD = args.num_speakers, args.threshold
    if NUM_SPEAKERS != -1 and NUM_SPEAKERS < 1:
        parser.error("人数须为正整数或-1")
    if not (ROOT / "audio.wav").is_file():
        parser.error("工作目录中没有audio.wav，请先用ffmpeg提取16kHz单声道音频")
    outputs = ["language.json", "transcript.jsonl"] if args.action == "transcribe" else ["speakers.json"]
    if not args.overwrite and any((ROOT / name).exists() for name in outputs):
        parser.error("输出已存在，请换工作目录或明确传入--overwrite")
    import soundfile as sf
    info = sf.info(str(ROOT / "audio.wav"))
    if info.samplerate != 16000 or info.channels != 1:
        parser.error("音频必须为16kHz单声道")
    {"transcribe": transcribe, "diarize": diarize}[args.action]()
