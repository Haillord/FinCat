import os
import sys
import logging
import json
import csv
import re
import tempfile
import uuid
import hmac
import hashlib
import base64
import sqlite3
from datetime import datetime
from pathlib import Path
from io import StringIO, BytesIO

import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, g
from flask_cors import CORS
from flask_session import Session
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

# Импорт улучшенного HWID
from hwid import get_hwid

# -------------------- Конфигурация --------------------
load_dotenv()

# Основные секреты теперь берутся из окружения (обязательно!)
FERNET_SECRET = os.getenv("FERNET_SECRET")          # если нет – сгенерируем при первом запуске
LICENSE_SECRET = os.getenv("LICENSE_SECRET")        # обязательно должен быть одинаковым на сервере и клиенте
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())

if not LICENSE_SECRET:
    raise RuntimeError("LICENSE_SECRET не задан в переменных окружения!")

# Пути для данных
APPDATA_DIR = Path(os.getenv("APPDATA", Path.home())) / "AIExpenseCategorizer"
APPDATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APPDATA_DIR / "config.enc"
API_CONFIG_PATH = APPDATA_DIR / "api_config.enc"
MASTER_KEY_PATH = APPDATA_DIR / "master.key"   # для хранения Fernet-ключа
LOGS_DIR = APPDATA_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# -------------------- Логирование --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler(LOGS_DIR / "error.log", encoding="utf-8")
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(file_handler)

# -------------------- Flask --------------------
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
CORS(app)

# Настройки сессии (файловые, чтобы избежать переполнения cookie)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = str(APPDATA_DIR / 'flask_sessions')
app.config['SESSION_FILE_THRESHOLD'] = 500
app.config['SESSION_PERMANENT'] = False
Session(app)

# Ограничения на загрузку
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# -------------------- Управление Fernet-ключом --------------------
def get_fernet():
    """Возвращает объект Fernet. Ключ либо читается из master.key, либо генерируется."""
    if MASTER_KEY_PATH.exists():
        key = MASTER_KEY_PATH.read_bytes()
    else:
        # Генерируем случайный ключ и сохраняем
        key = Fernet.generate_key()
        MASTER_KEY_PATH.write_bytes(key)
        # На Windows ставим скрытый атрибут (опционально)
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(MASTER_KEY_PATH), 2)  # FILE_ATTRIBUTE_HIDDEN
        except:
            pass
    return Fernet(key)

# -------------------- API конфиг --------------------
def load_api_config():
    if not API_CONFIG_PATH.exists():
        return None
    try:
        data = get_fernet().decrypt(API_CONFIG_PATH.read_bytes())
        return json.loads(data.decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError) as err:
        logger.error(f"Не удалось расшифровать api_config.enc: {err}")
        return None

def save_api_config(api_key: str, api_url: str, model: str = None):
    payload = {"api_key": api_key, "api_url": api_url, "model": model or "gpt-4o-mini"}
    token = get_fernet().encrypt(json.dumps(payload).encode("utf-8"))
    API_CONFIG_PATH.write_bytes(token)

def get_api_config():
    cfg = load_api_config() or {}
    return {
        "api_key": cfg.get("api_key"),
        "base_url": cfg.get("api_url") or "https://api.openai.com/v1",
        "model": cfg.get("model") or "gpt-4o-mini"
    }

# -------------------- Лицензия (офлайн) --------------------
def load_license_config():
    if not CONFIG_PATH.exists():
        return None
    try:
        decrypted = get_fernet().decrypt(CONFIG_PATH.read_bytes())
        return json.loads(decrypted.decode('utf-8'))
    except (InvalidToken, json.JSONDecodeError):
        logger.error("Не удалось расшифровать config.enc")
        return None

def save_license_config(data: dict):
    token = get_fernet().encrypt(json.dumps(data).encode('utf-8'))
    CONFIG_PATH.write_bytes(token)

def validate_license_offline(license_key: str):
    """Проверяет офлайн-ключ. Формат: base64url(JSON).HMAC-SHA256(первые 16 символов)."""
    try:
        token, sig = license_key.rsplit('.', 1)
        data = base64.urlsafe_b64decode(token.encode() + b'==').decode()
        expected_sig = hmac.new(LICENSE_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return {"valid": False, "error": "Недействительная подпись"}

        payload = json.loads(data)

        # Проверка HWID, если указан
        current_hwid = get_hwid()
        key_hwid = payload.get("hwid", "")
        if key_hwid and key_hwid != current_hwid:
            return {"valid": False, "error": "Ключ привязан к другому устройству"}

        # Проверка срока
        expires_at = payload.get("expires_at")
        if expires_at:
            exp = datetime.fromisoformat(expires_at)
            if datetime.utcnow() > exp:
                return {"valid": False, "error": "Срок действия истёк"}

        return {
            "valid": True,
            "is_trial": payload.get("is_trial", False),
            "expires_at": expires_at
        }
    except Exception as e:
        logger.error(f"License parse error: {e}")
        return {"valid": False, "error": "Неверный формат ключа"}

@app.before_request
def ensure_license():
    if request.path.startswith(('/activate', '/settings', '/settings/test', '/static')):
        return None

    config = load_license_config()
    if not config:
        return redirect(url_for('activate', error='Для работы необходимо активировать лицензию'))

    validation = validate_license_offline(config['key'])
    if not validation.get('valid'):
        err = validation.get('error', 'Лицензия недействительна')
        return redirect(url_for('activate', error=err))

    g.license_info = {
        'is_trial': validation.get('is_trial'),
        'expires_at': validation.get('expires_at')
    }

# -------------------- Категории и банки --------------------
COMMON_CATEGORIES = [
    "Зарплата", "Аренда", "Коммунальные услуги", "Транспорт", "Питание",
    "Развлечения", "Медицина", "Образование", "Покупки", "Налоги",
    "Маркетинг", "Реклама", "Оборудование", "Офисные расходы", "Банковские комиссии",
    "Интернет", "Телефон", "Страхование", "Подарки", "Прочее"
]

def get_bank_columns(bank):
    bank = (bank or 'auto').lower()
    common_dates = ['date', 'дата', 'transaction_date', 'date_transaction']
    common_desc = ['description', 'описание', 'description_transaction', 'transaction_description',
                   'назначение', 'описание операции']
    common_amount = ['amount', 'сумма', 'sum', 'transaction_amount', 'amount_transaction']

    presets = {
        'сбер': (
            ['дата операции', 'дата'],
            ['описание', 'назначение платежа', 'описание операции'],
            ['сумма', 'сумма в валюте операции', 'сумма операции']
        ),
        'тинькофф': (
            ['дата операции', 'date'],
            ['категория', 'описание', 'description'],
            ['сумма операции', 'amount']
        ),
        'альфа': (
            ['дата', 'дата операции'],
            ['назначение платежа', 'описание'],
            ['сумма', 'сумма операции']
        )
    }

    if bank in presets:
        d, desc, amt = presets[bank]
        return (d + common_dates, desc + common_desc, amt + common_amount)
    return (common_dates, common_desc, common_amount)

def clean_description(description):
    if not description or str(description).lower() in ('nan', ''):
        return ""
    desc = str(description).lower().strip()
    noise_patterns = [
        r'\b\d{4}\b',
        r'\b\d{2}\.\d{2}\.\d{4}\b',
        r'\b\d{2}\.\d{2}\b',
        r'\b\d{12,}\b',
        r'\b[а-я]{2}\d{6,}\b',
        r'[^\w\sа-яё\-]',
        r'\s+',
    ]
    for pattern in noise_patterns:
        desc = re.sub(pattern, ' ', desc)
    desc = ' '.join(desc.split())
    return desc.title() if desc else ""

def compute_summary(results):
    total = len(results)
    categorized = len([r for r in results if r.get('category') and r['category'] != 'Не определено'])
    return {
        'total_transactions': total,
        'categorized': categorized,
        'uncategorized': total - categorized
    }

# -------------------- AI категоризация --------------------
def categorize_transactions_chunk(transactions_data, categories):
    if not transactions_data:
        return []

    config = get_api_config()
    api_key = config.get("api_key")
    base_url = config.get("base_url")
    model = config.get("model")

    if not api_key:
        raise ValueError("API ключ не найден. Перейдите в Настройки и сохраните ключ.")

    # Очищаем ключ от возможного попадания в логи
    safe_url = base_url.replace(api_key, "[FILTERED]") if api_key else base_url

    prompt = f"""
Проанализируй следующие банковские транзакции и распредели их по категориям.

Категории для использования: {', '.join(categories)}

Для каждой транзакции определи:
1. Категорию (выбери из предложенных)
2. Очищенное описание (убери все служебные данные, оставь только суть)

Формат ответа (JSON):
[
  {{
    "original_description": "Оригинальное описание",
    "cleaned_description": "Очищенное описание",
    "category": "Категория",
    "amount": "Сумма"
  }}
]

Транзакции:
{json.dumps(transactions_data, ensure_ascii=False, indent=2)}
"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Ты эксперт по финансам и бухгалтерии. Твоя задача — категоризировать банковские транзакции."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4000
        }
        resp = requests.post(f"{base_url.rstrip('/')}/chat/completions",
                             headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result_text = resp.json()["choices"][0]["message"]["content"]

        json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            logger.error(f"Не удалось извлечь JSON из ответа: {result_text[:200]}")
            return []
    except requests.exceptions.HTTPError as e:
        # Не логируем детали, которые могут содержать ключ
        logger.error(f"HTTP ошибка при вызове AI API: {e.response.status_code}")
        raise
    except Exception as e:
        logger.error(f"Ошибка при вызове AI API: {type(e).__name__}")
        raise

# -------------------- Обработка файлов --------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls', 'csv'}

def process_file(file_path):
    """Парсит файл и возвращает список транзакций [{'date':..., 'description':..., 'amount':...}]"""
    bank = session.get('bank', 'auto')
    ext = file_path.suffix.lower() if isinstance(file_path, Path) else os.path.splitext(file_path)[1].lower()

    if ext == '.csv':
        return _process_csv(file_path, bank)
    elif ext in ('.xlsx', '.xls'):
        return _process_excel(file_path, bank)
    else:
        raise ValueError("Неподдерживаемый формат файла")

def _process_csv(file_path, bank):
    """Обработка CSV с автоопределением разделителя."""
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
        except:
            delimiter = ','   # fallback

        reader = csv.reader(f, delimiter=delimiter)
        headers = [h.lower().strip() for h in next(reader)]
        date_cols, desc_cols, amount_cols = get_bank_columns(bank)

        date_idx = desc_idx = amount_idx = None
        for i, h in enumerate(headers):
            if h in date_cols:
                date_idx = i
            elif h in desc_cols:
                desc_idx = i
            elif h in amount_cols:
                amount_idx = i

        if not all([date_idx is not None, desc_idx is not None, amount_idx is not None]):
            raise ValueError("Не найдены нужные колонки (дата, описание, сумма)")

        data = []
        for row in reader:
            if len(row) <= max(date_idx, desc_idx, amount_idx):
                continue
            try:
                amount = float(str(row[amount_idx]).replace(',', '.'))
                data.append({
                    'date': row[date_idx],
                    'description': row[desc_idx],
                    'amount': amount
                })
            except (ValueError, IndexError):
                continue
        return data

def _process_excel(file_path, bank):
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("Для работы с Excel установите pandas: pip install pandas openpyxl xlrd")

    df = pd.read_excel(file_path)
    df.columns = [str(col).lower() for col in df.columns]

    date_cols, desc_cols, amount_cols = get_bank_columns(bank)
    date_col = next((c for c in date_cols if c in df.columns), None)
    desc_col = next((c for c in desc_cols if c in df.columns), None)
    amount_col = next((c for c in amount_cols if c in df.columns), None)

    if not all([date_col, desc_col, amount_col]):
        raise ValueError("Не найдены нужные колонки (дата, описание, сумма)")

    df = df[[date_col, desc_col, amount_col]].copy()
    df.columns = ['date', 'description', 'amount']
    df = df.dropna(subset=['description', 'amount'])
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df = df.dropna(subset=['amount'])

    return [
        {'date': str(row['date']), 'description': str(row['description']), 'amount': float(row['amount'])}
        for _, row in df.iterrows()
    ]

# -------------------- Маршруты --------------------
@app.route('/')
def index():
    if not session.get('has_api_key'):
        saved = get_api_config().get("api_key")
        if not saved:
            return redirect(url_for('settings'))
        session['has_api_key'] = True
    license_info = g.get('license_info')
    cfg = get_api_config()
    return render_template('index.html',
                           categories=COMMON_CATEGORIES,
                           license_info=license_info,
                           api_model=cfg.get("model"))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    status = None
    message = None

    if request.method == 'POST':
        api_key = request.form.get('api_key', '').strip()
        api_url = request.form.get('api_url', '').strip() or "https://api.openai.com/v1"
        api_model = request.form.get('api_model', '').strip() or "gpt-4o-mini"
        if not api_key:
            status = 'error'
            message = 'Введите API ключ'
        else:
            try:
                save_api_config(api_key, api_url, api_model)
                session['has_api_key'] = True
                status = 'success'
                message = 'Настройки сохранены ✅'
            except Exception as err:
                status = 'error'
                message = f'Не удалось сохранить настройки: {err}'

    cfg = get_api_config()
    has_key = cfg.get("api_key") is not None
    current_api_url = cfg.get("base_url")
    current_model = cfg.get("model")
    return render_template('settings.html',
                           has_key=has_key,
                           status=status,
                           message=message,
                           api_url=current_api_url,
                           api_model=current_model)

@app.route('/settings/test', methods=['POST'])
def test_settings_key():
    cfg = get_api_config()
    api_key = cfg.get("api_key")
    api_url = cfg.get("base_url")
    if not api_key:
        return jsonify({'success': False, 'message': 'Ключ не найден. Сохраните настройки сначала.'}), 400

    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": cfg.get("model"),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }
        resp = requests.post(f"{api_url.rstrip('/')}/chat/completions",
                             headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return jsonify({'success': True, 'message': 'Подключение успешно ✅'})
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Не удалось подключиться. Проверьте API URL и интернет.'}), 400
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else '?'
        if code == 401:
            return jsonify({'success': False, 'message': 'Ключ недействителен (401). Проверьте API ключ.'}), 400
        return jsonify({'success': False, 'message': f'Ошибка {code}. Проверьте настройки.'}), 400
    except Exception as e:
        logger.error(f"API key test failed: {e}")
        return jsonify({'success': False, 'message': f'Ошибка: {e}'}), 400

@app.route('/activate', methods=['GET', 'POST'])
def activate():
    message = None
    success = False
    error = request.args.get('error')
    hwid = get_hwid()

    if request.method == 'POST':
        license_key = request.form.get('license_key', '').strip()
        if not license_key:
            message = 'Введите лицензионный ключ'
        else:
            validation = validate_license_offline(license_key)
            if validation.get('valid'):
                save_license_config({'key': license_key})
                success = True
                message = 'Лицензия активирована! Сейчас откроется главная страница...'
            else:
                message = validation.get('error', 'Ключ недействителен')

    return render_template('activate.html', message=message or error, success=success, hwid=hwid)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Неверный формат файла. Загрузите Excel (.xlsx, .xls) или CSV (.csv)'}), 400

    try:
        bank = request.form.get('bank', 'auto')
        session['bank'] = bank

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        transactions = process_file(file_path)

        if not transactions:
            return jsonify({'error': 'Не удалось прочитать файл. Проверьте формат.'}), 400

        for t in transactions:
            t['cleaned_description'] = clean_description(t['description'])

        # AI обработка
        categorized_results = []
        chunk_size = 50
        for i in range(0, len(transactions), chunk_size):
            chunk = transactions[i:i+chunk_size]
            chunk_results = categorize_transactions_chunk(chunk, COMMON_CATEGORIES)
            categorized_results.extend(chunk_results)

        results = []
        for transaction in transactions:
            matching = next(
                (r for r in categorized_results if r['original_description'] == transaction['description']),
                None
            )
            if matching:
                results.append({
                    'date': str(transaction['date']),
                    'original_description': transaction['description'],
                    'cleaned_description': matching['cleaned_description'],
                    'amount': str(transaction['amount']),
                    'category': matching['category']
                })
            else:
                results.append({
                    'date': str(transaction['date']),
                    'original_description': transaction['description'],
                    'cleaned_description': transaction['cleaned_description'],
                    'amount': str(transaction['amount']),
                    'category': 'Не определено'
                })

        os.remove(file_path)
        session['last_results'] = results  # файловая сессия выдержит

        return jsonify({
            'success': True,
            'data': results,
            'summary': compute_summary(results)
        })

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return jsonify({'error': 'Произошла ошибка при обработке. Проверьте логи.'}), 500

@app.route('/export', methods=['GET'])
def export_results():
    results = session.get('last_results')
    if not results:
        return jsonify({'error': 'Нет данных для экспорта'}), 400

    fmt = request.args.get('format', 'csv').lower()
    base_name = f"kategorii_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if fmt == 'csv':
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=['date', 'original_description', 'cleaned_description', 'amount', 'category'])
        writer.writeheader()
        writer.writerows(results)
        mem = BytesIO()
        mem.write(output.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=f'{base_name}.csv')

    if fmt in ('xlsx', 'xls'):
        try:
            import pandas as pd
        except ImportError:
            return jsonify({'error': 'Для экспорта в Excel установите pandas'}), 400
        df = pd.DataFrame(results)
        mem = BytesIO()
        with pd.ExcelWriter(mem, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        mem.seek(0)
        return send_file(mem,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=f'{base_name}.xlsx')

    return jsonify({'error': 'Неподдерживаемый формат'}), 400

@app.route('/update-category', methods=['POST'])
def update_category():
    data = request.get_json(silent=True) or {}
    idx = data.get('index')
    new_cat = data.get('category')

    results = session.get('last_results')
    if results is None:
        return jsonify({'error': 'Нет данных'}), 400

    try:
        idx = int(idx)
    except:
        return jsonify({'error': 'Неверный индекс'}), 400

    if not (0 <= idx < len(results)):
        return jsonify({'error': 'Индекс вне диапазона'}), 400

    if new_cat not in COMMON_CATEGORIES and new_cat != 'Не определено':
        return jsonify({'error': 'Недопустимая категория'}), 400

    results[idx]['category'] = new_cat
    session['last_results'] = results
    return jsonify({'success': True, 'summary': compute_summary(results)})

@app.errorhandler(500)
def handle_500(e):
    logger.error(f"Unhandled error: {e}", exc_info=True)
    return render_template('error.html', message='Внутренняя ошибка сервера. Подробности в логах.'), 500

# -------------------- Запуск (pywebview) --------------------
import threading
import webview

if __name__ == '__main__':
    def run_flask():
        app.run(debug=False, host='127.0.0.1', port=5000)

    threading.Thread(target=run_flask, daemon=True).start()
    webview.create_window('ФинКат', 'http://127.0.0.1:5000', width=1200, height=800)
    webview.start()