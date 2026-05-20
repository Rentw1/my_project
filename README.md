# 🥗 Calorie Tracker Bot

Telegram-бот для анализа калорий по фото с графиками и учётом питания.

## Возможности

- 📸 Распознавание еды по фото (GPT-4o Vision)
- 🔥 Подсчёт калорий, белков, жиров, углеводов
- 📊 График калорий за день (столбчатый)
- 📈 График за 7 дней (линейный)
- 🥗 Круговая диаграмма макронутриентов
- 🎯 Личная цель калорий
- 📜 История приёмов пищи
- 📉 Общая статистика

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и справка |
| `/today` | Итоги дня + график |
| `/week` | График за 7 дней |
| `/macros` | Белки/жиры/углеводы |
| `/history` | Последние 15 приёмов |
| `/goal 1800` | Установить цель калорий |
| `/delete` | Удалить последний приём |
| `/stats` | Общая статистика |

## Деплой на Railway

### 1. Загрузи на GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/calorie-bot.git
git push -u origin main
```

### 2. Создай проект на Railway

1. Зайди на [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo**
3. Выбери репозиторий `calorie-bot`
4. Railway автоматически определит Python и установит зависимости

### 3. Добавь переменные окружения

В Railway → твой проект → **Variables** → добавь:

| Переменная | Значение |
|------------|---------|
| `TELEGRAM_TOKEN` | Токен от @BotFather |
| `PROXYAPI_KEY` | Ключ от proxyapi.ru |

> ⚠️ **Никогда** не вставляй ключи прямо в код!

### 4. Деплой

Railway задеплоит автоматически после добавления переменных.
Статус можно проверить во вкладке **Deployments**.

## Локальный запуск

```bash
# Создай .env файл
echo "TELEGRAM_TOKEN=твой_токен" > .env
echo "PROXYAPI_KEY=твой_ключ" >> .env

# Установи зависимости
pip install -r requirements.txt

# Запусти
python bot.py
```

## Структура проекта

```
calorie-bot/
├── bot.py          # Основной файл бота
├── database.py     # SQLite база данных
├── requirements.txt
├── Procfile        # Для Railway
├── railway.toml    # Конфиг Railway
└── .gitignore
```
