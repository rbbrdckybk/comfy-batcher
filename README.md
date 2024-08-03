# ComfyUI Flux Batch Prompter
A simple command-line, API-driven, batch-prompter for ComfyUI with a workflow for [FLUX.1 dev](https://huggingface.co/black-forest-labs/FLUX.1-dev).

# Features

 * Simple command-line interface allows you to quickly queue up hundreds/thousands of prompts from a plain text file and send them to ComfyUI via the API (currently only the included Flux.1 dev workflow is supported, though support for other workflows should be trivial to add).
 * Control over all of the major Flux workflow variables: output image resolution, sampler/scheduler, steps, guidance, etc.
 * Automatic authentication via [ComfyUI-Login](https://github.com/liusida/ComfyUI-Login) is supported.

# Requirements

A working, up-to-date ComfyUI installation that can run a FLUX.1-dev workflow. If you need help getting your ComfyUI set up properly, [this is a good guide](https://www.reddit.com/r/StableDiffusion/comments/1ehv1mh/running_flow1_dev_on_12gb_vram_observation_on/).

# Setup

**[1]** Navigate to wherever you want ComfyUI Batcher to live, then clone this repository and switch to its directory:
```
git clone https://github.com/rbbrdckybk/comfy-batcher
cd comfy-batcher
```

Assuming you're running in the same virtual environment as ComfyUI, you shouldn't need to install anything else.

# Usage

Make sure your ComfyUI installation is currently running. You can then run the following to send a couple test prompts:
```
python comfy-batcher.py --workflow_file flux_workflow_api.json --prompt_file example-prompts.txt
```
Or simply run the ```go.bat``` file if you're on Windows.

ComfyUI should start working on the prompts immediately, and you should see the results in your ComfyUI output folder in a few seconds/minutes (depending on your GPU hardware).
