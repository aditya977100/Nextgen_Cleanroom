FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir fastapi uvicorn httpx cryptography
WORKDIR /app
COPY core /app/core
COPY gateway /app/gateway
CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
