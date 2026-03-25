# Slim LTX 2.3 image — models downloaded at first startup
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

# NO model downloads — they are fetched at first startup by entrypoint.sh
# This keeps the image ~5GB instead of 45GB

# Create model directories
RUN mkdir -p /ComfyUI/models/checkpoints \
             /ComfyUI/models/text_encoders \
             /ComfyUI/models/loras \
             /ComfyUI/models/latent_upscale_models

COPY . .
RUN mkdir -p /ComfyUI/user/default/ComfyUI-Manager
COPY config.ini /ComfyUI/user/default/ComfyUI-Manager/config.ini
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]