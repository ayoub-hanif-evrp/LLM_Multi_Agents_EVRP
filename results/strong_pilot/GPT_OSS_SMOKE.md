# gpt-oss:20b smoke (Ollama 0.33.3, num_ctx=8192)

- Installed: yes (13 GB, id f38aa0c53da5)
- Simple Python generation: OK (with num_predict>=256)
- Code-repair task: OK
- JSON/structured output: UNRELIABLE (format=json and free-form JSON prompts produced non-JSON / truncated chatter)

Decision for pilot: include in model registry but if Architect/Critic JSON repeatedly fails during seed 11, record SKIPPED_UNRELIABLE and continue with Devstral + Qwen3 only. Do not use cloud substitutes.
