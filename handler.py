import runpod
from runpod.serverless.utils import rp_upload
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import binascii # Base64 에러 처리를 위해 import
import subprocess
import time
import boto3
from botocore.exceptions import NoCredentialsError

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())

def upload_to_r2(video_data, file_name):
    """
    비디오 데이터를 Cloudflare R2에 업로드하고 URL을 반환합니다.
    환경변수 R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME이 필요합니다.
    """
    try:
        account_id = os.environ.get('R2_ACCOUNT_ID')
        access_key = os.environ.get('R2_ACCESS_KEY_ID')
        secret_key = os.environ.get('R2_SECRET_ACCESS_KEY')
        bucket_name = os.environ.get('R2_BUCKET_NAME')
        custom_domain = os.environ.get('R2_CUSTOM_DOMAIN')

        if not all([account_id, access_key, secret_key, bucket_name]):
            logger.error("R2 업로드를 위한 환경변수가 설정되지 않았습니다.")
            return None

        s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )

        # Base64 디코딩
        if isinstance(video_data, str):
            try:
                video_bytes = base64.b64decode(video_data)
            except binascii.Error:
                video_bytes = video_data.encode('utf-8')
        else:
            video_bytes = video_data

        s3_client.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=video_bytes,
            ContentType='video/mp4'
        )
        
        if custom_domain:
            url = f"{custom_domain}/{file_name}"
            # http/https prefix check
            if not url.startswith("http"):
                 url = f"https://{url}"
            logger.info(f"✅ R2 업로드 성공 (Public URL): {url}")
            return url
        else:
            # Custom Domain이 없는 경우 Presigned URL 생성 (1시간 유효)
            try:
                url = s3_client.generate_presigned_url(
                    ClientMethod='get_object',
                    Params={'Bucket': bucket_name, 'Key': file_name},
                    ExpiresIn=3600
                )
                logger.info(f"✅ R2 업로드 성공 (Presigned URL): {url}")
                return url
            except Exception as e:
                logger.error(f"❌ Presigned URL 생성 실패: {e}")
                return None

    except Exception as e:
        logger.error(f"❌ R2 업로드 중 오류 발생: {e}")
        return None

def to_nearest_multiple_of_16(value):
    """주어진 값을 가장 가까운 16의 배수로 보정, 최소 16 보장"""
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"width/height 값이 숫자가 아닙니다: {value}")
    adjusted = int(round(numeric_value / 16.0) * 16)
    if adjusted < 16:
        adjusted = 16
    return adjusted
def process_input(input_data, temp_dir, output_filename, input_type):
    """입력 데이터를 처리하여 파일 경로를 반환하는 함수"""
    if input_type == "path":
        # 경로인 경우 그대로 반환
        logger.info(f"📁 경로 입력 처리: {input_data}")
        return input_data
    elif input_type == "url":
        # URL인 경우 다운로드
        logger.info(f"🌐 URL 입력 처리: {input_data}")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        # Base64인 경우 디코딩하여 저장
        logger.info(f"🔢 Base64 입력 처리")
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"지원하지 않는 입력 타입: {input_type}")

        
def download_file_from_url(url, output_path):
    """URL에서 파일을 다운로드하는 함수"""
    try:
        # wget을 사용하여 파일 다운로드
        result = subprocess.run([
            'wget', '-O', output_path, '--no-verbose', url
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ URL에서 파일을 성공적으로 다운로드했습니다: {url} -> {output_path}")
            return output_path
        else:
            logger.error(f"❌ wget 다운로드 실패: {result.stderr}")
            raise Exception(f"URL 다운로드 실패: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ 다운로드 시간 초과")
        raise Exception("다운로드 시간 초과")
    except Exception as e:
        logger.error(f"❌ 다운로드 중 오류 발생: {e}")
        raise Exception(f"다운로드 중 오류 발생: {e}")


def save_base64_to_file(base64_data, temp_dir, output_filename):
    """Base64 데이터를 파일로 저장하는 함수"""
    try:
        # Base64 문자열 디코딩
        decoded_data = base64.b64decode(base64_data)
        
        # 디렉토리가 존재하지 않으면 생성
        os.makedirs(temp_dir, exist_ok=True)
        
        # 파일로 저장
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        with open(file_path, 'wb') as f:
            f.write(decoded_data)
        
        logger.info(f"✅ Base64 입력을 '{file_path}' 파일로 저장했습니다.")
        return file_path
    except (binascii.Error, ValueError) as e:
        logger.error(f"❌ Base64 디코딩 실패: {e}")
        raise Exception(f"Base64 디코딩 실패: {e}")
    
def queue_prompt(prompt):
    url = f"http://{server_address}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_image(filename, subfolder, folder_type):
    url = f"http://{server_address}:8188/view"
    logger.info(f"Getting image from: {url}")
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"{url}?{url_values}") as response:
        return response.read()

def find_generated_video(ws, prompt, filename_prefix):
    prompt_id = queue_prompt(prompt)['prompt_id']
    
    # 웹소켓으로 실행 완료 대기
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
        else:
            continue
            
    # 실행 완료 후 파일 검색
    output_dir = "/ComfyUI/output"
    logger.info(f"Searching for video with prefix '{filename_prefix}' in {output_dir}")
    
    # 5초간 재시도 (파일 시스템 동기화 지연 대비)
    for _ in range(5):
        if not os.path.exists(output_dir):
            time.sleep(1)
            continue
            
        for file in os.listdir(output_dir):
            if file.startswith(filename_prefix) and (file.endswith(".mp4") or file.endswith(".mov")):
                file_path = os.path.join(output_dir, file)
                logger.info(f"Found video file: {file_path}")
                
                 # 파일 읽기 및 Base64 인코딩
                with open(file_path, 'rb') as f:
                    video_data = base64.b64encode(f.read()).decode('utf-8')
                
                # (선택 사항) 파일 삭제 - 서버리스 환경에서는 자동 정리되지만 명시적으로 삭제
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted temporary file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}")
                    
                return video_data
        
        time.sleep(1)
    
    return None

def load_workflow(workflow_path):
    # 현재 파일의 디렉토리를 기준으로 절대 경로 생성
    current_dir = os.path.dirname(os.path.abspath(__file__))
    absolute_path = os.path.join(current_dir, workflow_path)
    with open(absolute_path, 'r') as file:
        return json.load(file)


def inject_loras(workflow, lora_pairs, lora_stage="both"):
    """Inject custom LoRA loader nodes into the ComfyUI workflow.

    Chains LoraLoaderModelOnly nodes between the checkpoint (92:1) and the
    model consumers (92:47 CFGGuider for first stage, 92:68 distilled LoRA
    for second stage).

    Args:
        workflow: The ComfyUI workflow dict (modified in-place).
        lora_pairs: List of dicts. Accepted formats:
            - {"high": "file.safetensors", "high_weight": 1.0}  (RunPod client format)
            - {"name": "file.safetensors", "strength": 1.0}     (simple format)
        lora_stage: Which stage(s) to apply LoRAs to.
            - "both": Apply to stage 1 (92:47) and stage 2 (92:68). Default.
            - "stage2": Apply only to stage 2 (92:68 distilled LoRA chain).
            - "stage1": Apply only to stage 1 (92:47 CFGGuider).
    """
    last_model_node = "92:1"
    last_model_output = 0

    for i, lora_pair in enumerate(lora_pairs):
        node_id = f"custom_lora_{i}"
        lora_name = lora_pair.get("high", lora_pair.get("name", ""))
        strength = float(lora_pair.get("high_weight", lora_pair.get("strength", 1.0)))

        if not lora_name:
            logger.warning(f"Skipping LoRA pair {i}: no filename provided")
            continue

        workflow[node_id] = {
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength,
                "model": [last_model_node, last_model_output]
            },
            "class_type": "LoraLoaderModelOnly",
            "_meta": {"title": f"Custom LoRA {i}: {lora_name}"}
        }

        last_model_node = node_id
        last_model_output = 0
        logger.info(f"Injected LoRA node '{node_id}': {lora_name} (strength={strength})")

    # Repoint model consumers to the last LoRA in the chain instead of 92:1
    if last_model_node != "92:1":
        # First stage CFGGuider
        if lora_stage in ("both", "stage1") and "92:47" in workflow:
            workflow["92:47"]["inputs"]["model"] = [last_model_node, 0]
            logger.info(f"Repointed 92:47 (CFGGuider stage 1) model -> {last_model_node}")
        # Distilled LoRA loader (feeds into second stage CFGGuider 92:82)
        if lora_stage in ("both", "stage2") and "92:68" in workflow:
            workflow["92:68"]["inputs"]["model"] = [last_model_node, 0]
            logger.info(f"Repointed 92:68 (distilled LoRA) model -> {last_model_node}")
        logger.info(f"LoRA stage mode: {lora_stage}")


def handler(job):
    job_input = job.get("input", {})

    logger.info(f"Received job input: {job_input}")
    task_id = f"task_{uuid.uuid4()}"

    # 이미지 입력 확인 (image_path, image_url, image_base64 중 하나라도 있으면 I2V)
    image_path = None
    has_image = False
    
    if "image_path" in job_input:
        image_path = process_input(job_input["image_path"], task_id, "input_image.jpg", "path")
        has_image = True
    elif "image_url" in job_input:
        image_path = process_input(job_input["image_url"], task_id, "input_image.jpg", "url")
        has_image = True
    elif "image_base64" in job_input:
        image_path = process_input(job_input["image_base64"], task_id, "input_image.jpg", "base64")
        has_image = True
    
    # 워크플로우 파일 선택 (이미지가 있으면 I2V, 없으면 T2V)
    if has_image:
        workflow_file = "workflow/ltx2_i2v.json"
        workflow_type = "I2V"
        logger.info("이미지 입력이 감지되어 I2V (Image-to-Video) 워크플로우를 사용합니다.")
    else:
        workflow_file = "workflow/ltx2_t2v.json"
        workflow_type = "T2V"
        logger.info("이미지 입력이 없어 T2V (Text-to-Video) 워크플로우를 사용합니다.")
    
    logger.info(f"Using {workflow_type} workflow: {workflow_file}")
    
    prompt = load_workflow(workflow_file)
    
    # 프롬프트 필수 확인
    if "prompt" not in job_input or not job_input["prompt"]:
        raise Exception("프롬프트(prompt)는 필수 입력입니다.")
    
    # 기본 파라미터 설정 (워크플로우 기본값과 일치)
    length = job_input.get("length", 129)  # I2V: 161:203, T2V: 92:62 기본값: 129
    steps = job_input.get("steps", 20)  # I2V: 161:106, T2V: 92:9 기본값: 20
    seed = job_input.get("seed", 10)  # I2V: 161:119, T2V: 92:11 기본값: 10
    cfg = job_input.get("cfg", 4.0)  # I2V: 161:140, T2V: 92:47 기본값: 4
    width = job_input.get("width", 1280)  # I2V: 161:148, T2V: 92:89 기본값: 1280
    height = job_input.get("height", 720)  # I2V: 161:148, T2V: 92:89 기본값: 720
    frame_rate = job_input.get("frame_rate", 25.0)  # I2V: 161:174/161:202, T2V: 92:102/92:99 기본값: 25
    positive_prompt = job_input["prompt"]
    negative_prompt = job_input.get("negative_prompt", "blurry, low quality, still frame, frames, watermark, overlay, titles, has blurbox, has subtitles")
    img_compression = job_input.get("img_compression", 33)  # LTXVPreprocess compression (1-100, lower = more compressed)
    lora_stage = job_input.get("lora_stage", "both")  # "both", "stage1", or "stage2"
    skip_stage2 = job_input.get("skip_stage2", False)  # Skip stage 2 refinement/upscale

    # Stage 2 override params (only used when skip_stage2=False)
    stage2_seed_match = job_input.get("stage2_seed_match", False)  # Copy stage 1 seed to stage 2
    stage2_sampler = job_input.get("stage2_sampler", None)  # Override sampler: "euler", "gradient_estimation", etc.
    stage2_cfg = job_input.get("stage2_cfg", None)  # Override stage 2 CFG (default: 1.0)
    stage2_lora_strength = job_input.get("stage2_lora_strength", None)  # Override distilled LoRA strength (default: 0.6)
    stage2_sigmas = job_input.get("stage2_sigmas", None)  # Override manual sigmas string
    stage2_steps = job_input.get("stage2_steps", None)  # Replace ManualSigmas with LTXVScheduler (auto sigmas)

    # 해상도 16배수 보정
    adjusted_width = to_nearest_multiple_of_16(width)
    adjusted_height = to_nearest_multiple_of_16(height)
    if adjusted_width != width:
        logger.info(f"Width adjusted to nearest multiple of 16: {width} -> {adjusted_width}")
    if adjusted_height != height:
        logger.info(f"Height adjusted to nearest multiple of 16: {height} -> {adjusted_height}")
    
    # I2V 전용 설정
    if has_image:
        # 프롬프트 설정 (92:3 - positive, 92:4 - negative)
        if "92:3" in prompt:
            prompt["92:3"]["inputs"]["text"] = positive_prompt
        if "92:4" in prompt:
            prompt["92:4"]["inputs"]["text"] = negative_prompt
        
        # 이미지 로드 (98)
        if "98" in prompt:
            prompt["98"]["inputs"]["image"] = image_path
        
        # 이미지 리사이즈 설정 (102 - ResizeImageMaskNode)
        if "102" in prompt:
            prompt["102"]["inputs"]["resize_type.width"] = adjusted_width
            prompt["102"]["inputs"]["resize_type.height"] = adjusted_height
        
        # Length 설정 (92:62 - PrimitiveInt)
        if "92:62" in prompt:
            prompt["92:62"]["inputs"]["value"] = length
        
        # Seed 설정 (92:11 - RandomNoise)
        if "92:11" in prompt:
            prompt["92:11"]["inputs"]["noise_seed"] = seed
        
        # Steps 설정 (92:9 - LTXVScheduler)
        if "92:9" in prompt:
            prompt["92:9"]["inputs"]["steps"] = steps
        
        # CFG 설정 (92:47 - CFGGuider)
        if "92:47" in prompt:
            prompt["92:47"]["inputs"]["cfg"] = cfg

        # img_compression 설정 (92:99 - LTXVPreprocess)
        if "92:99" in prompt:
            prompt["92:99"]["inputs"]["img_compression"] = img_compression
            logger.info(f"Set img_compression to {img_compression}")

        # Frame rate 설정 (92:51 - LTXVEmptyLatentAudio, 92:22 - LTXVConditioning, 92:97 - CreateVideo)
        if "92:51" in prompt:
            prompt["92:51"]["inputs"]["frame_rate"] = int(frame_rate)
        if "92:22" in prompt:
            prompt["92:22"]["inputs"]["frame_rate"] = int(frame_rate)
        if "92:97" in prompt:
            prompt["92:97"]["inputs"]["fps"] = int(frame_rate)
    else:
        # T2V 전용 설정
        # 프롬프트 설정 (92:3 - positive, 92:4 - negative)
        prompt["92:3"]["inputs"]["text"] = positive_prompt
        prompt["92:4"]["inputs"]["text"] = negative_prompt
        
        # Length 설정 (92:62)
        prompt["92:62"]["inputs"]["value"] = length
        
        # Seed 설정 (92:11)
        prompt["92:11"]["inputs"]["noise_seed"] = seed
        
        # Steps 설정 (92:9 - LTXVScheduler)
        prompt["92:9"]["inputs"]["steps"] = steps
        
        # CFG 설정 (92:47 - CFGGuider)
        prompt["92:47"]["inputs"]["cfg"] = cfg
        
        # EmptyImage 설정 (92:89)
        prompt["92:89"]["inputs"]["width"] = adjusted_width
        prompt["92:89"]["inputs"]["height"] = adjusted_height
        
        # Frame rate 설정 (92:102 - PrimitiveFloat, 92:99 - PrimitiveInt)
        if "92:102" in prompt:
            prompt["92:102"]["inputs"]["value"] = frame_rate
        if "92:99" in prompt and prompt["92:99"]["class_type"] == "PrimitiveInt":
            prompt["92:99"]["inputs"]["value"] = int(frame_rate)

    # Skip stage 2 — rewire VAE decode to read from stage 1 output directly
    if skip_stage2 and has_image:
        logger.info("Skipping stage 2 (refinement/upscale) — VAE decoding stage 1 output directly")
        # Rewire VAEDecode (92:95) to read from stage 1 separator (92:80) instead of stage 2 separator (92:94)
        if "92:95" in prompt:
            prompt["92:95"]["inputs"]["samples"] = ["92:80", 0]
        # Rewire AudioVAEDecode (92:96) to read from stage 1 separator (92:80) instead of stage 2 separator (92:94)
        if "92:96" in prompt:
            prompt["92:96"]["inputs"]["samples"] = ["92:80", 1]
        # Run stage 1 at full resolution (normally 0.5x because stage 2 upscales 2x)
        if "92:90" in prompt:
            prompt["92:90"]["inputs"]["scale_by"] = 1.0
            logger.info("Set stage 1 resolution scale to 1.0x (full resolution)")
        # Stage 2 nodes (92:84, 92:108, 92:83, 92:70, 92:94, 92:82, 92:68, 92:66, 92:67, 92:73, 92:76, 92:81)
        # become orphaned and won't be executed by ComfyUI

    # Stage 2 overrides — apply when stage 2 is NOT skipped
    if not skip_stage2 and has_image:
        # Fix: Match stage 1 seed in stage 2 (default is hardcoded 0)
        if stage2_seed_match and "92:67" in prompt:
            prompt["92:67"]["inputs"]["noise_seed"] = seed
            logger.info(f"Stage 2 seed matched to stage 1: {seed}")

        # Fix: Override stage 2 sampler (default: gradient_estimation)
        if stage2_sampler and "92:66" in prompt:
            prompt["92:66"]["inputs"]["sampler_name"] = stage2_sampler
            logger.info(f"Stage 2 sampler set to: {stage2_sampler}")

        # Fix: Override stage 2 CFG (default: 1.0)
        if stage2_cfg is not None and "92:82" in prompt:
            prompt["92:82"]["inputs"]["cfg"] = float(stage2_cfg)
            logger.info(f"Stage 2 CFG set to: {stage2_cfg}")

        # Fix: Override distilled LoRA strength (default: 0.6)
        if stage2_lora_strength is not None and "92:68" in prompt:
            prompt["92:68"]["inputs"]["strength_model"] = float(stage2_lora_strength)
            logger.info(f"Stage 2 distilled LoRA strength set to: {stage2_lora_strength}")

        # Fix: Override manual sigmas string
        if stage2_sigmas and "92:73" in prompt:
            prompt["92:73"]["inputs"]["sigmas"] = stage2_sigmas
            logger.info(f"Stage 2 sigmas set to: {stage2_sigmas}")

        # Fix: Replace ManualSigmas with LTXVScheduler for auto sigma scheduling
        if stage2_steps and "92:73" in prompt:
            # Remove the ManualSigmas node
            del prompt["92:73"]
            # Add an LTXVScheduler node for stage 2
            prompt["stage2_scheduler"] = {
                "inputs": {
                    "steps": int(stage2_steps),
                    "max_shift": 2.05,
                    "base_shift": 0.95,
                    "stretch": True,
                    "terminal": 0.1,
                    "latent": ["92:83", 0]
                },
                "class_type": "LTXVScheduler",
                "_meta": {"title": "Stage 2 LTXV Scheduler"}
            }
            # Rewire stage 2 sampler to use the new scheduler
            if "92:70" in prompt:
                prompt["92:70"]["inputs"]["sigmas"] = ["stage2_scheduler", 0]
            logger.info(f"Stage 2 using LTXVScheduler with {stage2_steps} steps (replaced ManualSigmas)")

    # LoRA injection — dynamically add LoRA loader nodes to the workflow
    lora_pairs = job_input.get("lora_pairs", [])
    if lora_pairs:
        logger.info(f"Injecting {len(lora_pairs)} custom LoRA(s) into workflow")
        inject_loras(prompt, lora_pairs, lora_stage=lora_stage)

    # Filename Prefix 설정 (75 - SaveVideo)
    if "75" in prompt:
         prompt["75"]["inputs"]["filename_prefix"] = task_id
         
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    logger.info(f"Connecting to WebSocket: {ws_url}")
    
    # 먼저 HTTP 연결이 가능한지 확인
    http_url = f"http://{server_address}:8188/"
    logger.info(f"Checking HTTP connection to: {http_url}")
    
    # HTTP 연결 확인 (최대 1분)
    max_http_attempts = 180
    for http_attempt in range(max_http_attempts):
        try:
            import urllib.request
            response = urllib.request.urlopen(http_url, timeout=5)
            logger.info(f"HTTP 연결 성공 (시도 {http_attempt+1})")
            break
        except Exception as e:
            logger.warning(f"HTTP 연결 실패 (시도 {http_attempt+1}/{max_http_attempts}): {e}")
            if http_attempt == max_http_attempts - 1:
                raise Exception("ComfyUI 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
            time.sleep(1)
    
    ws = websocket.WebSocket()
    # 웹소켓 연결 시도 (최대 3분)
    max_attempts = int(180/5)  # 3분 (1초에 한 번씩 시도)
    for attempt in range(max_attempts):
        import time
        try:
            ws.connect(ws_url)
            logger.info(f"웹소켓 연결 성공 (시도 {attempt+1})")
            break
        except Exception as e:
            logger.warning(f"웹소켓 연결 실패 (시도 {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                raise Exception("웹소켓 연결 시간 초과 (3분)")
            time.sleep(5)
            
    # 비디오 생성 및 검색
    video_base64 = find_generated_video(ws, prompt, task_id)
    ws.close()

    if video_base64:
        if job_input.get("return_url", False):
            # R2 업로드
            file_name = f"{task_id}.mp4"
            video_url = upload_to_r2(video_base64, file_name)
            if video_url:
                return {"video_url": video_url}
            else:
                 logger.warning("R2 업로드 실패, Base64 비디오를 반환합니다.")

        return {"video": video_base64}
    
    return {"error": "비디오를 찾을 수 없습니다."}

runpod.serverless.start({"handler": handler})