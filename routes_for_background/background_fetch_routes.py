from flask import Blueprint, request, jsonify
from dal.db_query import ManageQuery
from bl.utils.base64_utils import Base64Utils

get_photos = Blueprint("get_photos", __name__)


@get_photos.route("/user_photos/<user_name>", methods=["GET"])
def get_user_photos(user_name):
    """
    Получает фото пользователя.
    user_name может быть:
      - числом (id_user напрямую) — новый способ из Flutter
      - строкой (name в таблице users) — старый способ
    """
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=20, type=int)

    if page < 1 or limit < 1:
        return jsonify({"error": "page and limit must be >= 1"}), 400

    try:
        # Пробуем распознать как числовой id
        id_user = None
        try:
            id_user = int(user_name)
            # Проверяем что такой пользователь существует
            if not ManageQuery.get_user_by_id(id_user):
                return jsonify({"error": f"User with id {id_user} not found"}), 404
        except ValueError:
            # Не число — ищем по имени
            id_user = ManageQuery.get_id_user(user_name)
            if not id_user:
                return jsonify({"error": f"User '{user_name}' not found"}), 404

        photos = ManageQuery.get_user_photos_paginated(
            id_user=id_user,
            limit=limit,
            offset=(page - 1) * limit
        )

        photos_with_base64 = []
        if photos:
            photos_with_base64 = [
                {
                    "id": photo[0],
                    "image_base64": Base64Utils.encode_to_base64(photo[1])
                }
                for photo in photos
            ]

        return jsonify({
            "page": page,
            "limit": limit,
            "total_photos": ManageQuery.count_user_photos(id_user),
            "photos": photos_with_base64
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500