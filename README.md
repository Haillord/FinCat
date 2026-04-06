<p align="center">
  <img width="100%" alt="FinCat Banner" src="icon.png">
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/Haillord/FinCat?style=for-the-badge&color=red" alt="license">
  <img src="https://img.shields.io/github/stars/Haillord/FinCat?style=for-the-badge&color=red" alt="stars">
  <img src="https://img.shields.io/github/last-commit/Haillord/FinCat?style=for-the-badge&color=red" alt="last commit">
</p>

<h1 align="center">FinCat</h1>

<p align="center">
  <b>Умный парсер и анализатор банковских выписок.</b><br>
  Автоматическая категоризация транзакций, детальная аналитика и отчёты для всех российских банков.
</p>

---

### ⚡️ Ключевые возможности

*   **✅ Поддержка всех банков** - парсит выписки Сбера, Тинькофф, ВТБ, Альфа, Открытие, Райффайзен и других
*   **🧠 Автоматическая категоризация** - умный алгоритм распределяет все транзакции по категориям
*   **📊 Детальная аналитика** - графики расходов, доходов, статистика по периодам и категориям
*   **📥 Любые форматы** - импорт CSV, TXT, Excel, выписки из интернет банков и мобильных приложений
*   **🔒 Система лицензий** - защита HWID, офлайн активация, отдельный лицензионный сервер
*   **🖥️ Standalone EXE** - компилируется в один исполняемый файл, не требует установки Python
*   **🌐 Веб интерфейс** - удобный современный интерфейс работающий в любом браузере

---

### 🛠 Стек технологий

| Компонент | Технологии |
| :--- | :--- |
| **Backend** | Python 3.11 • Flask |
| **Frontend** | HTML5 • CSS3 • Vanilla JavaScript • Chart.js |
| **Парсеры** • Pandas • OpenPyXL • CSV |
| **Система лицензий** • AES-256 • HWID |
| **Сборка** • PyInstaller • UPX |

---

### 📂 Структура проекта

```text
📜 app.py                # Основное приложение Flask
📜 License_gen.py        # Генератор лицензий
📜 hwid.py               # Модуль получения HWID
📜 build_exe.bat         # Скрипт сборки в EXE
📄 requirements.txt      # Зависимости проекта

📁 templates/            # Веб интерфейс
   📄 index.html         # Главная страница
   📄 activate.html      # Страница активации
   📄 settings.html      # Настройки

📁 license_server/       # Отдельный лицензионный сервер
```

---

### 🚀 Установка и запуск

```bash
# Клонировать репозиторий
git clone https://github.com/Haillord/FinCat.git
cd FinCat

# Установить зависимости
pip install -r requirements.txt

# Запустить приложение
python app.py
```

После запуска открыть в браузере: `http://localhost:5000`

---

### 🔑 Система лицензий

Проект использует офлайн систему защиты:
- Активация по уникальному HWID компьютера
- Лицензии подписаны цифровой подписью
- Нет необходимости в постоянном интернет соединении
- Отдельный сервер для управления лицензиями

---

<p align="center">
  <img src="https://img.shields.io/badge/Made%20with-Python-3776AB?style=for-the-badge&logo=python" alt="python">
  <img src="https://img.shields.io/badge/Developer-Haillord-red?style=for-the-badge&logo=telegram" alt="author">
</p>