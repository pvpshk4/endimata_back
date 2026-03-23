from flask import Blueprint, jsonify
from dal.db_query import ManageQuery

categories_routes = Blueprint("categories_routes", __name__)


@categories_routes.route("/categories", methods=["GET"])
def get_categories():
    """
    Возвращает полное дерево категорий одежды.
    Структура: { category: { subcategory: [sub_subcategory, ...] } }
    """
    try:
        # Получаем все категории, подкатегории и под-подкатегории из БД
        categories = ManageQuery.get_all_categories()
        subcategories = ManageQuery.get_all_subcategories()
        sub_subcategories = ManageQuery.get_all_sub_subcategories()

        if not categories or not subcategories or not sub_subcategories:
            return jsonify({"error": "Категории не найдены"}), 404

        # Строим плоский список — Flutter сам знает свою структуру
        return jsonify({
            "status": "success",
            "categories": [c[0] for c in categories],
            "subcategories": [s[0] for s in subcategories],
            "sub_subcategories": [ss[0] for ss in sub_subcategories],
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500