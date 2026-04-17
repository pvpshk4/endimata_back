import sys
import threading
import uuid
import base64
import os
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

# Путь к CatVTON проекту
CATVTON_PATH = r'D:\Projects\CatVTON'
CATVTON_VENV_PATH = r'D:\Projects\CatVTON\venv\Lib\site-packages'

tryon_blueprint = Blueprint('tryon', __name__)

# ──────────────────────────────────────────────────────────────
# Хранилище задач в памяти
# {task_id: {status, result_base64, error, created_at}}
# ──────────────────────────────────────────────────────────────
_tasks = {}
_tasks_lock = threading.Lock()

# Флаг что модель загружена
_pipeline = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    """Ленивая загрузка модели — только при первом запросе."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline

        try:
            # Добавляем пути CatVTON
            if CATVTON_PATH not in sys.path:
                sys.path.insert(0, CATVTON_PATH)
            if CATVTON_VENV_PATH not in sys.path:
                sys.path.insert(0, CATVTON_VENV_PATH)

            import torch
            from model.pipeline import CatVTONPipeline
            from diffusers import AutoencoderKL

            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            dtype = torch.bfloat16

            base_ckpt = 'booksforcharlie/stable-diffusion-inpainting'
            attn_ckpt = 'zhengchong/CatVTON'
            attn_ckpt_version = 'mix'

            _pipeline = CatVTONPipeline(
                base_ckpt=base_ckpt,
                attn_ckpt=attn_ckpt,
                attn_ckpt_version=attn_ckpt_version,
                weight_dtype=dtype,
                skip_safety_check=True,
                device=device,
            )

            logging.info(f'CatVTON pipeline loaded on {device}')
            return _pipeline

        except Exception as e:
            logging.error(f'Failed to load CatVTON pipeline: {e}')
            raise


def _paste_on_white(img, size=(768, 1024)):
    """Вставляет RGBA изображение на белый фон."""
    from PIL import Image
    img = img.resize(size)
    if img.mode == 'RGBA':
        background = Image.new('RGB', size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    return img.convert('RGB')

def _run_tryon(task_id: str, person_bytes: bytes, cloth_bytes: bytes, cloth_type: str):
    try:
        import torch
        import numpy as np
        from PIL import Image
        import io

        with _tasks_lock:
            _tasks[task_id]['status'] = 'processing'

        # Добавляем пути CatVTON
        if CATVTON_PATH not in sys.path:
            sys.path.insert(0, CATVTON_PATH)
        if CATVTON_VENV_PATH not in sys.path:
            sys.path.insert(0, CATVTON_VENV_PATH)

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cloth_masker", 
            f"{CATVTON_PATH}/model/cloth_masker.py"
        )
        mask_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mask_module)
        AutoMasker = mask_module.AutoMasker

        pipeline = _get_pipeline()

        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        # Загружаем и вставляем на белый фон
        person_img = _paste_on_white(Image.open(io.BytesIO(person_bytes)), (768, 1024))
        cloth_img = _paste_on_white(Image.open(io.BytesIO(cloth_bytes)), (768, 1024))

        # Генерируем умную маску через AutoMasker
        automasker = AutoMasker(
        densepose_ckpt=f'{CATVTON_PATH}/model/CatVTON/DensePose',
        schp_ckpt=f'{CATVTON_PATH}/model/CatVTON/SCHP',
        device=device,
        )
        mask_result = automasker(person_img, mask_type=cloth_type)
        mask = mask_result['mask']

        # Запуск примерки
        generator = torch.Generator(device).manual_seed(42)
        with torch.no_grad():
            result = pipeline(
                image=person_img,
                condition_image=cloth_img,
                mask=mask,
                num_inference_steps=20,
                guidance_scale=2.5,
                generator=generator,
            )[0]

        # Конвертируем результат в base64
        buffer = io.BytesIO()
        result.save(buffer, format='PNG')
        result_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        with _tasks_lock:
            _tasks[task_id]['status'] = 'done'
            _tasks[task_id]['result_base64'] = result_base64

        logging.info(f'Task {task_id} completed successfully')

    except Exception as e:
        logging.error(f'Task {task_id} failed: {e}')
        with _tasks_lock:
            _tasks[task_id]['status'] = 'error'
            _tasks[task_id]['error'] = str(e)


# ──────────────────────────────────────────────────────────────
# ЭНДПОИНТЫ
# ──────────────────────────────────────────────────────────────

@tryon_blueprint.route('/start', methods=['POST'])
#@jwt_required()
def start_tryon():
    """
    Запускает примерку асинхронно.
    Body JSON:
      person_image: base64 строка фото человека
      cloth_image:  base64 строка фото одежды
      cloth_type:   'upper' | 'lower' | 'overall' (опционально, default='upper')
    Возвращает:
      task_id: строка для polling статуса
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400

    person_b64 = data.get('person_image')
    cloth_b64 = data.get('cloth_image')
    cloth_type = data.get('cloth_type', 'upper')

    if not person_b64 or not cloth_b64:
        return jsonify({'status': 'error', 'message': 'person_image and cloth_image required'}), 400

    try:
        # Декодируем base64
        person_b64_clean = person_b64.split(',')[-1] if ',' in person_b64 else person_b64
        cloth_b64_clean = cloth_b64.split(',')[-1] if ',' in cloth_b64 else cloth_b64

        person_bytes = base64.b64decode(person_b64_clean)
        cloth_bytes = base64.b64decode(cloth_b64_clean)
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Invalid base64: {e}'}), 400

    # Создаём задачу
    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _tasks[task_id] = {
            'status': 'queued',
            'result_base64': None,
            'error': None,
            'created_at': datetime.now().isoformat(),
        }

    # Запускаем в отдельном потоке
    thread = threading.Thread(
        target=_run_tryon,
        args=(task_id, person_bytes, cloth_bytes, cloth_type),
        daemon=True,
    )
    thread.start()

    return jsonify({
        'status': 'success',
        'task_id': task_id,
        'message': 'Try-on started. Poll /tryon/status/{task_id} for result.',
    }), 202


@tryon_blueprint.route('/status/<task_id>', methods=['GET'])
#@jwt_required()
def get_tryon_status(task_id: str):
    """
    Возвращает статус задачи примерки.
    Статусы: queued | processing | done | error
    Когда done — возвращает result_base64.
    """
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        return jsonify({'status': 'error', 'message': 'Task not found'}), 404

    response = {
        'status': task['status'],
        'created_at': task['created_at'],
    }

    if task['status'] == 'done':
        response['result_base64'] = task['result_base64']
        # Очищаем задачу после получения результата
        with _tasks_lock:
            del _tasks[task_id]

    elif task['status'] == 'error':
        response['message'] = task.get('error', 'Unknown error')
        with _tasks_lock:
            del _tasks[task_id]

    return jsonify(response)


@tryon_blueprint.route('/health', methods=['GET'])
def health():
    """Проверка доступности сервиса примерки."""
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else 'CPU only'
    except Exception:
        gpu_available = False
        gpu_name = 'Unknown'

    return jsonify({
        'status': 'ok',
        'gpu_available': gpu_available,
        'gpu_name': gpu_name,
        'active_tasks': len(_tasks),
    })