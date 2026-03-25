#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Enable fast HuggingFace downloads
export HF_HUB_ENABLE_HF_TRANSFER=1

# Download models if not already present (first startup only)
echo "Checking for model files..."

download_if_missing() {
    local url="$1"
    local dest="$2"
    local headers="${3:-}"
    if [ ! -f "$dest" ]; then
        echo "Downloading $(basename $dest)..."
        if [ -n "$headers" ]; then
            wget -q --show-progress --header="$headers" "$url" -O "$dest"
        else
            wget -q --show-progress "$url" -O "$dest"
        fi
        echo "Done: $(basename $dest)"
    else
        echo "Found: $(basename $dest)"
    fi
}

# -- Eros checkpoint (CivitAI, requires API key) --
CIVIT_HEADER=""
if [ -n "$CIVIT" ]; then
    CIVIT_HEADER="Authorization: Bearer $CIVIT"
fi
download_if_missing \
    "https://civitai.com/api/download/models/2752410" \
    "/ComfyUI/models/checkpoints/ltx2310eros_beta.safetensors" \
    "$CIVIT_HEADER"

# -- Heretic text encoder (HuggingFace) --
download_if_missing \
    "https://huggingface.co/DreamFast/gemma-3-12b-it-heretic/resolve/main/comfyui/gemma_3_12B_it_heretic_fp8_e4m3fn.safetensors" \
    "/ComfyUI/models/text_encoders/gemma_3_12B_it_heretic_fp8_e4m3fn.safetensors"

# -- Dynamic distilled LoRA (HuggingFace) --
download_if_missing \
    "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors" \
    "/ComfyUI/models/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors"

# -- Spatial upscaler (HuggingFace) --
download_if_missing \
    "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-spatial-upscaler-x2-1.0.safetensors" \
    "/ComfyUI/models/latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors"

echo "All models ready."

# Start ComfyUI in the background
echo "Starting ComfyUI in the background..."
python /ComfyUI/main.py --listen --use-sage-attention &

# Wait for ComfyUI to be ready (longer timeout for first start with large models)
echo "Waiting for ComfyUI to be ready..."
max_wait=600
wait_count=0
while [ $wait_count -lt $max_wait ]; do
    if curl -s http://127.0.0.1:8188/ > /dev/null 2>&1; then
        echo "ComfyUI is ready!"
        break
    fi
    echo "Waiting for ComfyUI... ($wait_count/$max_wait)"
    sleep 2
    wait_count=$((wait_count + 2))
done

if [ $wait_count -ge $max_wait ]; then
    echo "Error: ComfyUI failed to start within $max_wait seconds"
    exit 1
fi

# Start the handler in the foreground
echo "Starting the handler..."
exec python handler.py
