Put your local Gemma 4 GGUF model file in this folder.

Recommended smaller models for laptops:
- gemma-4-e2b quantized GGUF
- gemma-4-e4b quantized GGUF

GridGemma Pro searches this folder for .gguf files and prefers filenames containing:

- gemma-4
- E2B
- E4B
- Q4
- it

You can also select any compatible .gguf file manually inside GridGemma Pro.

To try the setup downloader, run this from the app folder:

download_model.bat

Large models may be slow or require much more RAM. If no model file is present,
GridGemma Pro still works with its deterministic fallback heuristic engine.
