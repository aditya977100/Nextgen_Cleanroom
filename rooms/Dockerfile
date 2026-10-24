FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN mkdir -p /data /shared && chmod 1777 /data /shared
WORKDIR /app
COPY rooms /app
CMD ["python", "/app/server.py"]
