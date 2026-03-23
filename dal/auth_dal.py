from psycopg2 import Error
import logging

from dal.db_connection import DBConnection


class Authenticate:
    @staticmethod
    def _execute_query(query, params=None, fetch=False, fetch_insert=False):
        with DBConnection.get_con() as con:
            with con.cursor() as cursor:
                try:
                    if params and isinstance(params, list):
                        cursor.executemany(query, params)
                    else:
                        if not isinstance(params, tuple):
                            params = (params,)
                        cursor.execute(query, params or ())

                    result = None
                    if fetch:
                        result = cursor.fetchall()
                    elif fetch_insert:
                        result = cursor.fetchone()

                    con.commit()
                    return result
                except Error:
                    con.rollback()
                    raise

    @staticmethod
    def authenticate_or_register_by_firebase_uid(firebase_uid: str, name: str = '', email: str = ''):
        """
        Ищет пользователя по firebase_uid.
        Если не найден — создаёт нового.
        Возвращает {'status': 'success', 'id_user': int}
        """
        try:
            # Ищем существующего пользователя
            query = """
                SELECT id_user FROM users
                WHERE firebase_uid = %s
            """
            result = Authenticate._execute_query(query, (firebase_uid,), fetch=True)

            if result:
                return {
                    'status': 'success',
                    'id_user': result[0][0]
                }

            # Пользователь не найден — регистрируем
            # name берём из Firebase профиля, если пустой — используем часть email
            display_name = name or (email.split('@')[0] if email else firebase_uid[:12])

            insert_query = """
                INSERT INTO users (name, firebase_uid, email)
                VALUES (%s, %s, %s)
                RETURNING id_user
            """
            new_user = Authenticate._execute_query(
                insert_query,
                (display_name, firebase_uid, email),
                fetch_insert=True
            )

            if not new_user:
                return {
                    'status': 'error',
                    'message': 'Failed to create user'
                }

            return {
                'status': 'success',
                'id_user': new_user[0]
            }

        except Error as e:
            logging.error(f"Error in authenticate_or_register_by_firebase_uid: {str(e)}")
            return {
                'status': 'error',
                'message': f'Database error: {str(e)}'
            }

    @staticmethod
    def authenticate_user_by_name_password(username, password):
        """Проверяет учётные данные пользователя по name и password"""
        try:
            query = """
                SELECT id_user FROM users 
                WHERE name = %s AND password = crypt(%s, password)
            """
            result = Authenticate._execute_query(query, (username, password), fetch=True)
            if not result:
                return {
                    'status': 'error',
                    'message': f'Пользователь {username} не найден'
                }
            return {
                'status': 'success',
                'id_user': result[0][0]
            }
        except Error as e:
            logging.error(f"Error authenticating user: {str(e)}")
            return {'status': 'error', 'message': 'Database error'}

    @staticmethod
    def register_user_by_tg_id_if_not_exists(tg_id):
        try:
            query = """
                INSERT INTO users(tg_id)
                VALUES (%s) RETURNING id_user
            """
            id_user = Authenticate._execute_query(query, tg_id, fetch_insert=True)
            if not id_user:
                return {'status': 'error', 'message': f'Не удалось добавить пользователя с tg_id {tg_id}'}
            return {'status': 'success', 'id_user': id_user[0]}
        except Error:
            raise

    @staticmethod
    def authenticate_user_by_tg_id(tg_id):
        try:
            query = """
                SELECT id_user FROM users 
                WHERE tg_id = %s
            """
            result = Authenticate._execute_query(query, tg_id, fetch=True)
            if not result:
                result = Authenticate.register_user_by_tg_id_if_not_exists(tg_id)
            else:
                result = {'status': 'success', 'id_user': result[0][0]}
            return result
        except Error as e:
            logging.error(f"Error authenticating user: {str(e)}")
            return None

    @staticmethod
    def check_tg_id_exists(tg_id):
        query = """
            SELECT id_user FROM users
            WHERE tg_id = %s
        """
        result = Authenticate._execute_query(query, (tg_id,), fetch=True)
        return bool(result)

    @staticmethod
    def link_telegram_account_db(tg_id, id_user):
        query = """
            UPDATE Users SET tg_id = %s
            WHERE id_user = %s RETURNING id_user
        """
        id_user = Authenticate._execute_query(query, (tg_id, id_user), fetch_insert=True)
        if not id_user:
            return {'status': 'error', 'message': 'Не удалось добавить tg id к существующему аккаунту'}
        return {
            'status': 'success',
            'message': 'Telegram account linked successfully',
            'id_user': id_user
        }