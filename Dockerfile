# Використовуємо Python 3.11-slim (легкий образ)
FROM python:3.11-slim

# Встановлюємо часовий пояс UTC — єдине джерело правди для всіх сервісів
ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/UTC /etc/localtime && \
    echo "UTC" > /etc/timezone

# Встановлюємо робочу директорію всередині контейнера
WORKDIR /app

# Копіюємо файл з залежностями
COPY requirements.txt .

# Встановлюємо Python-залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь код проєкту в контейнер
COPY . .

# За замовчуванням запускається бот, але в docker-compose ми перевизначаємо команду для воркера
CMD ["python", "-m", "app.main"]
