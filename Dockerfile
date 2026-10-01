FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv==0.12.13 \
    && uv pip install --system --no-cache -r pyproject.toml

COPY manage.py ./
COPY config ./config
COPY apps ./apps
COPY helpers ./helpers

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# В референсе контейнер запускал runserver; для продакшена — gunicorn.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
