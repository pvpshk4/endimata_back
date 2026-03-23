from flask import Blueprint, request, jsonify
import os
from bl.utils.base64_utils import Base64Utils
from bl.background_bl.background_bl import remove_background
from bl.utils.create_folders import create_folders_for_background
from bl.utils.hash import calculate_hash
from config import PROCESSED_FOLDER_BACKGROUND
from dal.db_query import ManageQuery

add_photos = Blueprint("add_photos", __name__)

create_folders_for_background()


@add_photos.route("/process", methods=["POST"])
def upload_file():
    """
    Принимает изображение в формате base64, удаляет фон и возвращает Base64-изображение без фона.
    Поддерживает два режима:
      - user_name (строка) — старый способ, ищет по name в таблице users
      - user_id (число) — новый способ из Flutter, ищет напрямую по id_user
    """
    data = request.json
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    photo_base64 = data.get("image")
    if not photo_base64:
        return jsonify({"error": "Отсутствует параметр image (base64)"}), 400

    # Определяем id_user — поддерживаем оба способа передачи
    id_user = None

    user_id = data.get("user_id")       # числовой id напрямую
    user_name = data.get("user_name")   # строковое имя (старый способ)

    if user_id is not None:
        # Flutter отправляет числовой id
        try:
            id_user = int(user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "user_id должен быть числом"}), 400

        # Проверяем что пользователь существует
        if not ManageQuery.get_user_by_id(id_user):
            return jsonify({"error": f"Пользователь с id {id_user} не найден"}), 400

    elif user_name is not None:
        # Старый способ — ищем по имени
        id_user = ManageQuery.get_id_user(user_name)
        if not id_user:
            return jsonify({"error": f"Пользователь с именем {user_name} не найден"}), 400
    else:
        return jsonify({"error": "Необходим параметр user_id или user_name"}), 400

    try:
        # Декодируем base64
        decode_image = Base64Utils.decode_base64_in_image(photo_base64)

        # Проверяем уникальность по хэшу
        file_hash = calculate_hash(decode_image)
        if not ManageQuery.is_photo_users_unique(file_hash, id_user):
            return jsonify({"error": "Photo already exists"}), 400

        # Если фото есть среди удалённых — восстанавливаем
        id_photo = ManageQuery.is_photo_user_among_deleted(file_hash, id_user)
        if id_photo:
            result = ManageQuery.recovery_photos_human_db(id_photo, id_user)
            if result['status'] == 'error':
                return jsonify(result), 500
            else:
                return jsonify(result), 200

        # Сохраняем исходное изображение
        try:
            input_path = Base64Utils.writing_file_background(photo_base64)
        except Exception as e:
            return jsonify({"error": f"Failed to save image: {str(e)}"}), 500

        # Удаляем фон
        output_filename = remove_background(input_path)

        # Удаляем необработанное фото
        if os.path.exists(input_path):
            os.remove(input_path)

        if output_filename:
            processed_path = os.path.join(PROCESSED_FOLDER_BACKGROUND, output_filename)

            try:
                # Используем id_user напрямую
                id_photo = _add_photo_user_by_id(
                    id_user=id_user,
                    photo_path=processed_path,
                    category="full",
                    is_cut=True
                )

                if id_photo:
                    ManageQuery.add_hash_photos_users(id_photo, file_hash)
                    encode_image = Base64Utils.encode_to_base64(processed_path)

                    return jsonify({
                        "status": "success",
                        "message": "Фон успешно удален",
                        "image_base64": f"data:image/png;base64,{encode_image}"
                    })
                else:
                    return jsonify({"error": "Ошибка сохранения данных в БД"}), 500
            except Exception as db_error:
                return jsonify({"error": f"Ошибка при работе с БД: {str(db_error)}"}), 500
        else:
            return jsonify({"error": "Ошибка обработки изображения"}), 500

    except Exception as error:
        return jsonify({"error": f"Ошибка обработки запроса: {str(error)}"}), 500


def _add_photo_user_by_id(id_user, photo_path, category="full", is_cut=True):
    """Добавляет фото пользователя по id_user напрямую (без поиска по name)"""
    from dal.db_connection import DBConnection
    from psycopg2 import Error
    import logging

    try:
        id_category = ManageQuery.get_id_category_photos(category)
        if not id_user or not id_category or not photo_path:
            logging.error("Invalid id_user, id_category or photo_path")
            return False

        query = """
            INSERT INTO photo_users (id_user, photo_path, id_category, is_cut)
            VALUES (%s, %s, %s, %s) RETURNING id_photo
        """
        result = ManageQuery._execute_query(
            query, (id_user, photo_path, id_category, is_cut), fetch_insert=True
        )
        return result
    except Error as e:
        logging.error(f"Error _add_photo_user_by_id: {str(e)}")
        return False