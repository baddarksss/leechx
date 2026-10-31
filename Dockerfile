# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────
#  LeechX — ربات لیچر تلگرام
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# ffmpeg برای ادغام ویدیو/صدا و تبدیل فرمت ضروری است
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      ca-certificates \
      tzdata \
      curl \
      atomicparsley \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir "pytest>=8,<9" "pytest-asyncio>=0.24,<2"

COPY . .

# کاربر غیر روت
RUN useradd -m -u 10001 leechx \
 && mkdir -p /app/data/files /app/data/tmp /app/data/cookies /home/leechx/.local/bin \
 && chown -R leechx:leechx /app /home/leechx

USER leechx

# نصب‌های pip --user (مثل بروزرسانی yt-dlp از داخل ربات) در همین مسیر می‌نشینند
# و در docker-compose به ./data/pylocal بایند می‌شوند تا بعد از rebuild بمانند.
ENV PYTHONUSERBASE=/home/leechx/.local \
    PATH=/home/leechx/.local/bin:$PATH \
    DATA_DIR=/app/data \
    HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["python", "main.py"]
