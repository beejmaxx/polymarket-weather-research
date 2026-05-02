FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PWMK_DB_PATH=/data/pwmk.sqlite

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8000

CMD ["pwmk", "serve", "--host", "0.0.0.0", "--port", "8000"]

