import requests
import base64

# Читаем тестовые изображения
with open(r'D:\путь\к\фото_человека.jpg', 'rb') as f:
    person_b64 = base64.b64encode(f.read()).decode()

with open(r'D:\путь\к\фото_одежды.jpg', 'rb') as f:
    cloth_b64 = base64.b64encode(f.read()).decode()

# Сначала получаем JWT токен
auth = requests.post('http://localhost:5000/auth/login/firebase', json={
    'firebase_token': 'твой_firebase_token'
})
jwt_token = auth.json()['access_token']

# Запускаем примерку
response = requests.post(
    'http://localhost:5000/tryon/start',
    json={
        'person_image': person_b64,
        'cloth_image': cloth_b64,
        'cloth_type': 'upper'
    },
    headers={'Authorization': f'Bearer {jwt_token}'}
)
print(response.json())