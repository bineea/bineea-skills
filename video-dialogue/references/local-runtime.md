# 本地运行环境

当前共享目录：`E:\document\联想跨级任务\Tiger\资料\字幕处理`。

- Python：`.venv\Scripts\python.exe`，Python 3.13。
- 转写模型：`whisper-small/`。
- 分段模型：`sherpa-onnx-pyannote-segmentation-3-0/model.onnx`。
- 声纹模型：`speaker-hf.onnx`。不要使用归档中不完整的 `speaker.onnx` 下载文件。
- 依赖：faster-whisper、ctranslate2、sherpa-onnx、soundfile、numpy、opencc-python-reimplemented；参考共享目录 `requirements.txt`。ffmpeg/ffprobe 应在 PATH。

以上是本机配置，使用前检查；换机器须配置实际路径。环境缺失时使用项目虚拟环境和明确 Python 版本，不用全局 pip。不为每场会议重复安装或复制模型。

## 基础命令

替换输入和工作路径。工作目录应独立，不包含其他任务的产物。

```powershell
$modelDir = 'E:\document\联想跨级任务\Tiger\资料\字幕处理'
$runtime = Join-Path $modelDir '.venv\Scripts\python.exe'
$skillDir = 'C:\Users\guowb1\.codex\skills\video-dialogue'
$mediaPath = '此处替换为视频或音频完整路径'
$jobDir = '此处替换为本次会议处理目录'
New-Item -ItemType Directory -Path $jobDir -Force | Out-Null
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 $mediaPath
ffmpeg -hide_banner -loglevel error -n -i $mediaPath -vn -ac 1 -ar 16000 (Join-Path $jobDir 'audio.wav')
if ($LASTEXITCODE -ne 0) { throw '音频提取失败，请检查后再继续' }
& $runtime "$skillDir\scripts\process_audio.py" transcribe --models-dir $modelDir --work-dir $jobDir
if ($LASTEXITCODE -ne 0) { throw '转写未完成，请检查日志' }
& $runtime "$skillDir\scripts\process_audio.py" diarize --models-dir $modelDir --work-dir $jobDir
if ($LASTEXITCODE -ne 0) { throw '分离未完成，请检查日志' }
```

脚本默认拒绝覆盖输出，不支持自动续传。中断后检查完整性，必要时用新尝试目录重跑并保留日志；不要以文件存在判定成功。音频通过 soundfile 读入数组，避免当前 PyAV 解码接口不兼容。仅模型加载成功不代表完整会议已验证。
