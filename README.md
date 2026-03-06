---

# MBSPP Local Cloud

Это локальный файловый сервер с REST API, построенный на Flask. Проект обеспечивает безопасное хранение, управление и скачивание файлов с использованием строгой ролевой модели доступа на базе TOTP (Google Authenticator) и токенов.

## Документация: Как это работает

Сервер предоставляет эндпоинты для просмотра директорий, получения метаданных, загрузки, скачивания, удаления и экспорта папок в виде ZIP-архивов. Безопасность обеспечивается многоуровневой системой токенов, а защита от случайной потери данных — механизмом «мягкого удаления» (корзиной).

### Используемые библиотеки

* 
**Flask (3.0.3):** Основной веб-фреймворк для создания REST API и маршрутизации.


* 
**pyotp (2.9.0):** Библиотека для генерации и проверки одноразовых паролей (TOTP).



### Структура проекта

* 
`run.py`: Точка входа, регистрирующая маршруты и запускающая сервер на порту 48240.


* 
`server/__init__.py`: Инициализация приложения, создание директорий и генерация файлов с секретами при их отсутствии.


* 
`server/auth.py`: Логика проверки TOTP, валидация прав администратора и выдача токенов.


* 
`server/tokens.py`: Генерация криптографически стойких токенов (разной длины в зависимости от уровня), контроль времени жизни и сохранение их в `tokens.json`.


* 
`server/files.py`: Основная логика работы с файловой системой, проверка лимитов для Pro-пользователей и механизм перемещения удаленных файлов в корзину.


* 
`open_file.ps1`: Клиентский PowerShell-скрипт для умного скачивания файлов на компьютер (в `Documents\mbspp_cli`) с проверкой даты изменения и последующим открытием.



### Ролевая модель доступа

| Уровень | Описание | Срок действия токена | Ограничения и особенности |
| --- | --- | --- | --- |
| **1 (User)** | Только чтение и скачивание файлов.

 | 1 день.

 | Использует код из `totp_secret.txt`.

 |
| **2 (Pro)** | Чтение, скачивание и загрузка новых файлов.

 | 12 часов.

 | Лимит: загрузка не более 10 уникальных файлов за 10 минут. Блокировка при превышении. Использует код из `totp_secret_pro.txt`.

 |
| **3 (Admin)** | Полный доступ, включая удаление файлов.

 | Бессрочно (пока не отозван).

 | Максимум 2 активные сессии. Требует заголовок `X-Admin-Code` (из файла `admin/adminadmin`). При удалении требует подтверждения операции через TOTP код в теле запроса.

 |

### Механизм удаления (local_del)

При перезаписи или удалении файлов они не стираются физически. Сервер перемещает их в скрытую директорию `local_del`, добавляя к имени временную метку `_<YYYYMMDDTHHMMSSZ>`. Сервер автоматически очищает файлы старше 14 дней при запуске.

---

## Запуск проекта

Убедитесь, что у вас установлен Python 3. Накатите зависимости и запустите сервер:

```bash
pip install -r requirements.txt
python run.py

```

Сервер запустится по адресу `http://127.0.0.1:48240`. При первом запуске автоматически сгенерируются файлы `totp_secret.txt`, `totp_secret_pro.txt` и `admin/adminadmin`.

---

## Руководство по API (Команды терминала)

Ниже приведены команды для взаимодействия с сервером. Замените `<CODE>` на текущий код из Google Authenticator, а пути файлов на свои.

### 1. Аутентификация (Получение токена)

**Windows (CMD):**

```cmd
:: Получение токена User (Level 1)
curl -X POST -H "Content-Type: application/json" -d "{\"code\":\"<CODE>\"}" http://127.0.0.1:48240/api/auth/verify

:: Получение токена Admin (Level 3) - требуется X-Admin-Code
set /p ADMIN_SECRET=<admin\adminadmin
curl -X POST -H "Content-Type: application/json" -H "X-Admin-Code: %ADMIN_SECRET%" -d "{\"code\":\"<CODE>\"}" http://127.0.0.1:48240/api/auth/verify

:: Сохранение токена в переменную для следующих запросов
set TOKEN=твой_полученный_токен

```

**Linux (Terminal):**

```bash
# Получение токена User (Level 1)
curl -X POST -H "Content-Type: application/json" -d '{"code":"<CODE>"}' http://127.0.0.1:48240/api/auth/verify

# Получение токена Admin (Level 3)
ADMIN_SECRET=$(head -n 1 admin/adminadmin)
curl -X POST -H "Content-Type: application/json" -H "X-Admin-Code: $ADMIN_SECRET" -d "{\"code\":\"<CODE>\"}" http://127.0.0.1:48240/api/auth/verify

# Сохранение токена
export TOKEN="твой_полученный_токен"

```

### 2. Просмотр файлов (Level 1+)

**Windows (CMD):**

```cmd
curl -H "Authorization: Bearer %TOKEN%" "http://127.0.0.1:48240/api/list?path=/"

```

**Linux (Terminal):**

```bash
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:48240/api/list?path=/"

```

### 3. Скачивание файла (Level 1+)

**Windows (CMD):**

```cmd
curl -H "Authorization: Bearer %TOKEN%" -o my_file.txt "http://127.0.0.1:48240/api/download/my_file.txt"

```

**Linux (Terminal):**

```bash
curl -H "Authorization: Bearer $TOKEN" -o my_file.txt "http://127.0.0.1:48240/api/download/my_file.txt"

```

### 4. Экспорт папки в ZIP (Level 1+)

**Windows (CMD):**

```cmd
curl -X POST -H "Authorization: Bearer %TOKEN%" -H "Content-Type: application/json" -d "{\"path\":\"/my_folder\"}" --output folder.zip http://127.0.0.1:48240/api/export

```

**Linux (Terminal):**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"path":"/my_folder"}' --output folder.zip http://127.0.0.1:48240/api/export

```

### 5. Загрузка файла (Level 2+)

**Windows (CMD):**

```cmd
curl -X POST -H "Authorization: Bearer %TOKEN%" -F "file=@C:\path\to\local_file.txt" -F "path=remote_folder/file.txt" http://127.0.0.1:48240/api/file/upload

```

**Linux (Terminal):**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -F "file=@/path/to/local_file.txt" -F "path=remote_folder/file.txt" http://127.0.0.1:48240/api/file/upload

```

### 6. Удаление файла (Только Level 3)

Внимание: для удаления требуется передать актуальный TOTP код от `totp_secret_pro.txt` в теле запроса и секрет администратора в заголовке.

**Windows (CMD):**

```cmd
curl -X POST -H "Authorization: Bearer %TOKEN%" -H "X-Admin-Code: %ADMIN_SECRET%" -H "Content-Type: application/json" -d "{\"path\":\"remote_folder/file.txt\", \"code\":\"<CODE>\"}" http://127.0.0.1:48240/api/file/delete

```

**Linux (Terminal):**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "X-Admin-Code: $ADMIN_SECRET" -H "Content-Type: application/json" -d "{\"path\":\"remote_folder/file.txt\", \"code\":\"<CODE>\"}" http://127.0.0.1:48240/api/file/delete

```

---

## Использование клиентского скрипта open_file.ps1

Скрипт предназначен для удобной работы пользователей на Windows. Он скачивает файл, только если локальная версия устарела, и сразу открывает его в программе по умолчанию.

Запуск в PowerShell:

```powershell
.\open_file.ps1 -Server "http://127.0.0.1:48240" -Token "ТВОЙ_ТОКЕН" -Path "remote_folder/file.txt"

```

---
