# Containerized VoxForge backend (TRD §13). Linux image uses Piper since `say`
# is macOS-only — run ./setup.sh during build to fetch the binary + model.
FROM python:3.12-slim

# ffmpeg enables MP3 export; omit it and the server returns WAV.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x setup.sh && ./setup.sh

ENV VOXFORGE_ENGINE=piper
# Lock CORS to your real origin in production (comma-separated). NOT "*".
ENV VOXFORGE_ALLOWED_ORIGIN=https://your-domain.example
# Behind TLS: send the session cookie only over HTTPS.
ENV VOXFORGE_SECURE_COOKIE=1
EXPOSE 8000

# Run as an unprivileged user (least privilege).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
