import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive'
]

if not os.path.exists('credentials.json'):
    print("Ошибка: файл credentials.json не найден.")
    print("Скачай его из Google Cloud Console → APIs & Services → Credentials")
    print("и положи в корень проекта рядом с этим скриптом.")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

with open('token.json', 'w') as f:
    f.write(creds.to_json())

print("Авторизация успешна! Файл token.json создан.")
