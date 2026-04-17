__all__ = ("tryon_blueprint",)

from flask import Blueprint
from .tryon_routes import tryon_blueprint as tryon

tryon_blueprint = Blueprint("tryon_main", __name__, url_prefix='/tryon')
tryon_blueprint.register_blueprint(tryon)