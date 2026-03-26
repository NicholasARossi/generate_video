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
    if [ ! -f "$dest" ]; then
        echo "Downloading $(basename $dest)..."
        wget -q --show-progress "$url" -O "$dest"
        echo "Done: $(basename $dest)"
    else
        echo "Found: $(basename $dest)"
    fi
}

download_if_missing \
    "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-dev-fp8.safetensors" \
    "/ComfyUI/models/checkpoints/ltx-2-19b-dev-fp8.safetensors"

download_if_missing \
    "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" \
    "/ComfyUI/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"

download_if_missing \
    "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-19b-distilled-lora-384.safetensors" \
    "/ComfyUI/models/loras/ltx-2-19b-distilled-lora-384.safetensors"

download_if_missing \
    "https://huggingface.co/Lightricks/LTX-2-19b-LoRA-Camera-Control-Dolly-Left/resolve/main/ltx-2-19b-lora-camera-control-dolly-left.safetensors" \
    "/ComfyUI/models/loras/ltx-2-19b-lora-camera-control-dolly-left.safetensors"

download_if_missing \
    "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-spatial-upscaler-x2-1.0.safetensors" \
    "/ComfyUI/models/latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors"

echo "All models ready."

# Start ComfyUI in the background
echo "Starting ComfyUI in the background..."
python /ComfyUI/main.py --listen --use-sage-attention &

# Wait for ComfyUI to be ready
echo "Waiting for ComfyUI to be ready..."
max_wait=300
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
