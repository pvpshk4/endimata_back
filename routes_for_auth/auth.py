import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from dal.auth_dal import Authenticate
from dal.users_dal import UsersDAL
import os
import logging

auth_blueprint = Blueprint('auth', __name__)

# Инициализация Firebase Admin SDK (один раз при старте)
_firebase_initialized = False

def _init_firebase():
    global _firebase_initialized
    if not _firebase_initialized:
        cred_path = os.getenv('FIREBASE_CREDENTIALS', 'serviceAccountKey.json')
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
        else:
            logging.warning(f"Firebase credentials file not found: {cred_path}")

_init_firebase()


@auth_blueprint.route('/login/firebase', methods=['POST'])
def firebase_login():
    """
    Авторизация через Firebase.
    Flutter отправляет: { "firebase_token": "<idToken из Firebase>" }
    Сервер верифицирует токен, находит или создаёт пользователя, возвращает JWT.
    """
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400

    firebase_token = data.get('firebase_token')
    if not firebase_token:
        return jsonify({'status': 'error', 'message': 'firebase_token is required'}), 400

    if not _firebase_initialized:
        return jsonify({'status': 'error', 'message': 'Firebase not configured on server'}), 500

    try:
        # Верифицируем токен через Firebase Admin SDK
        decoded_token = firebase_auth.verify_id_token(firebase_token)
        firebase_uid = decoded_token['uid']
        email = decoded_token.get('email', '')
        name = decoded_token.get('name', email or firebase_uid)

    except firebase_admin.exceptions.FirebaseError as e:
        logging.error(f"Firebase token verification failed: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Invalid Firebase token'}), 401
    except Exception as e:
        logging.error(f"Unexpected error during Firebase verification: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Token verification failed'}), 500

    try:
        # Ищем пользователя по firebase_uid в нашей БД
        result = Authenticate.authenticate_or_register_by_firebase_uid(
            firebase_uid=firebase_uid,
            name=name,
            email=email
        )

        if result['status'] == 'error':
            return jsonify(result), 500

        id_user = result['id_user']

        # Создаём наш JWT токен
        access_token = create_access_token(identity=str(id_user))
        refresh_token = create_refresh_token(identity=str(id_user))

        return jsonify({
            'status': 'success',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'id_user': id_user
        }), 200

    except Exception as e:
        logging.error(f"Error during Firebase login: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500


@auth_blueprint.route('/login', methods=['POST'])
def standard_login():
    """Авторизация по логину и паролю"""
    data = request.get_json()
    username = data.get('name')
    password = data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Name and password required'}), 400

    result = Authenticate.authenticate_user_by_name_password(username, password)
    if result is None or result["status"] == "error":
        return jsonify(result), 401

    access_token = create_access_token(identity=str(result["id_user"]))
    refresh_token = create_refresh_token(identity=result["id_user"])

    return jsonify({
        'status': 'success',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'id_user': result["id_user"]
    })


@auth_blueprint.route('/login/telegram', methods=['POST'])
def telegram_login():
    """Авторизация через Telegram"""
    data = request.get_json()
    tg_id = data.get('tg_id')

    if not tg_id:
        return jsonify({'status': 'error', 'message': 'Telegram ID required'}), 400

    result = Authenticate.authenticate_user_by_tg_id(tg_id)
    if result["status"] == "error":
        return jsonify(result), 500

    access_token = create_access_token(identity=str(result["id_user"]))

    return jsonify({
        'status': 'success',
        'access_token': access_token,
        'id_user': result["id_user"]
    })


@auth_blueprint.route('/link-account', methods=['POST'])
@jwt_required()
def link_telegram_account():
    """Привязка Telegram ID к существующему аккаунту"""
    id_user = get_jwt_identity()
    tg_id = request.json.get('tg_id')

    if not tg_id:
        return jsonify({'status': 'error', 'message': 'Telegram ID required'}), 400

    if Authenticate.check_tg_id_exists(tg_id):
        return jsonify({'status': 'error', 'message': 'Telegram ID already linked'}), 400

    result = Authenticate.link_telegram_account_db(tg_id, id_user)
    if result["status"] == "error":
        return jsonify(result), 500

    return jsonify(result)


@auth_blueprint.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Обновление access token"""
    current_user = get_jwt_identity()
    new_token = create_access_token(identity=current_user)
    return jsonify({'access_token': new_token})


@auth_blueprint.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Получить информацию о текущем пользователе по JWT токену"""
    id_user = get_jwt_identity()
    return jsonify({
        'status': 'success',
        'id_user': id_user
    })