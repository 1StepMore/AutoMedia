# 旁白 TTS（Azure）

本项目旁白用 Azure TTS（逐段合成，便于时间轴对齐）。示例（Azure Speech REST / CLI 封装均可）：
- 音色：`zh-CN-YunjianNeural`（男声有力），或 `zh-CN-YunyangNeural`（正式）。
- 格式：`audio-24khz-48kbitrate-mono-mp3`。
- 每段一个文件 → `ffprobe` 量时长 → 拼接 → `narration_full.mp3`。

**规则**：TTS 文案里「AI」一律写「人工智能」（口播念法）。
**注意**：`edge-tts` 免费端点在多数环境 403，别依赖它；用 Azure 或本地 piper。
