#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Models are baked into the Docker image — no downloads needed.
echo "All models ready (baked into image)."

# Start ComfyUI in the background
# COMFY_EXTRA_FLAGS can be set via RunPod template env vars to add flags like
# --use-sage-attention, --force-fp32, --bf16-unet, etc.
COMFY_FLAGS="--listen --use-sage-attention ${COMFY_EXTRA_FLAGS:-}"
echo "Starting ComfyUI with flags: $COMFY_FLAGS"
python /ComfyUI/main.py $COMFY_FLAGS &

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
