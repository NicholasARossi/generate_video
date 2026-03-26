# LTX 2.3 Eros — models baked into image for RunPod FlashBoot compatibility
FROM wlsdml1114/engui_genai-base_blackwell:1.1 AS runtime

RUN pip install -U "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client boto3

WORKDIR /

RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd /ComfyUI && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Comfy-Org/ComfyUI-Manager.git && \
    cd ComfyUI-Manager && \
    pip install -r requirements.txt

# Install LTX-Video custom nodes (LTXVImgToVideoInplace, LTXAVTextEncoderLoader, etc.)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git && \
    cd ComfyUI-LTXVideo && \
    pip install -r requirements.txt

# Create model directories
RUN mkdir -p /ComfyUI/models/checkpoints \
             /ComfyUI/models/text_encoders \
             /ComfyUI/models/loras \
             /ComfyUI/models/latent_upscale_models

# Download Eros checkpoint from CivitAI (23.4 GB, requires API key)
ARG CIVIT_KEY
RUN wget -q --show-progress \
    --header="Authorization: Bearer ${CIVIT_KEY}" \
    "https://civitai.com/api/download/models/2752410" \
    -O /ComfyUI/models/checkpoints/ltx2310eros_beta.safetensors

# Download Heretic text encoder from HuggingFace (12.8 GB)
RUN wget -q --show-progress \
    "https://huggingface.co/DreamFast/gemma-3-12b-it-heretic/resolve/main/comfyui/gemma_3_12B_it_heretic_fp8_e4m3fn.safetensors" \
    -O /ComfyUI/models/text_encoders/gemma_3_12B_it_heretic_fp8_e4m3fn.safetensors

# Download dynamic distilled LoRA from HuggingFace (2.6 GB)
RUN wget -q --show-progress \
    "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors" \
    -O /ComfyUI/models/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors

# Download spatial upscaler from HuggingFace
RUN wget -q --show-progress \
    "https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-spatial-upscaler-x2-1.0.safetensors" \
    -O /ComfyUI/models/latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors

COPY . .
RUN mkdir -p /ComfyUI/user/default/ComfyUI-Manager
COPY config.ini /ComfyUI/user/default/ComfyUI-Manager/config.ini
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
