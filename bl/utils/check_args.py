import logging
import os

from flask import jsonify
import dal.db_query


class CheckArgs:

    @staticmethod
    def check_args_add_photo_person(id_user, id_category, user_name, category, photo_path):
        ret = True
        if id_user is None:
            logging.error(f"User '{user_name}' not found")
            ret = False
        if id_category is None:
            logging.error(f"Category '{category}' not found")
            ret = False
        if photo_path == "":
            logging.error("Photo path is empty")
            ret = False
        return ret

    @staticmethod
    def check_args_add_photo_clothes(id_user, photo_base64, category, subcategory, sub_subcategory):
        """
        id_user — числовой id из JWT (get_jwt_identity() возвращает строку, конвертируем в int)
        """
        ret = {"status": "success"}

        # Конвертируем id_user в число
        try:
            id_user_int = int(id_user)
        except (TypeError, ValueError):
            return {
                "status": "error",
                "error": f"Некорректный id_user: {id_user}"
            }

        # Проверяем существование пользователя по id напрямую
        existing_user = dal.db_query.ManageQuery.get_user_by_id(id_user_int)
        if existing_user is None:
            return {
                "status": "error",
                "error": f"Пользователь с id {id_user_int} не найден"
            }

        id_category = dal.db_query.ManageQuery.get_id_category_clothes(category)
        id_subcategory = dal.db_query.ManageQuery.get_id_subcategory_clothes(subcategory)
        id_sub_subcategory = dal.db_query.ManageQuery.get_id_sub_subcategory_clothes(sub_subcategory)

        if not photo_base64:
            return {"status": "error", "error": "Отсутствует параметр photo (base64)"}
        if not category:
            return {"status": "error", "error": "Отсутствует параметр category"}
        if not subcategory:
            return {"status": "error", "error": "Отсутствует параметр subcategory"}
        if not sub_subcategory:
            return {"status": "error", "error": "Отсутствует параметр sub_subcategory"}
        if id_category is None:
            return {"status": "error", "error": f"Категория '{category}' не найдена"}
        if id_subcategory is None:
            return {"status": "error", "error": f"Подкатегория '{subcategory}' не найдена"}
        if id_sub_subcategory is None:
            return {"status": "error", "error": f"Под-подкатегория '{sub_subcategory}' не найдена"}

        ret["id_user"] = id_user_int
        ret["id_category"] = id_category
        ret["id_subcategory"] = id_subcategory
        ret["id_sub_subcategory"] = id_sub_subcategory

        return ret

    @staticmethod
    def check_args_recovery_photos(id, user_name):
        ret = {"status": "success"}
        if not id:
            ret = {"status": "error", "error": "Отсутствует параметр id"}
        if not user_name:
            ret = {"status": "error", "error": "Отсутствует параметр user_name"}
        return ret

    @staticmethod
    def check_args_recovery_photos_wardrobe(id_clothes, user_name):
        result = CheckArgs.check_args_recovery_photos(id_clothes, user_name)
        if result["status"] == "error":
            return result

        id_user = dal.db_query.ManageQuery.get_id_user(user_name)
        if id_user is None:
            return {"status": "error", "error": f"user_name '{user_name}' не найден"}

        if not dal.db_query.ManageQuery.is_photo_clothes_deleted(id_clothes):
            return {"status": "error", "error": f"Фото одежды с id {id_clothes} не удалено"}

        return result

    @staticmethod
    def check_args_recovery_photos_human(id_photo, user_name):
        result = CheckArgs.check_args_recovery_photos(id_photo, user_name)
        if result["status"] == "error":
            return result

        id_user = dal.db_query.ManageQuery.get_id_user(user_name)
        if id_user is None:
            return {"status": "error", "error": f"user_name '{user_name}' не найден"}

        if not dal.db_query.ManageQuery.is_photo_user_deleted(id_photo):
            return {"status": "error", "error": f"Фото человека {user_name} с id_фото {id_photo} не удалено"}

        return result

    @staticmethod
    def check_is_admin(id_user):
        admin_list = os.getenv('ADMIN_LIST', '')
        if str(id_user) in admin_list.split(','):
            return {"status": "success", "message": "Пользователь является администратором"}
        else:
            return {"status": "error", "error": "Пользователь не является администратором"}