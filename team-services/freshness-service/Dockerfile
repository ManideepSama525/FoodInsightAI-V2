FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FRESHNESS_CHECKPOINT=/app/outputs/freshness_v1/best_model.pt \
    FRESHNESS_DEVICE=cpu
WORKDIR /app
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.6.0 torchvision==0.21.0
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY freshness_service/ /app/freshness_service/
COPY training/ /app/training/
RUN useradd --system --user-group --home-dir /app app
USER app
EXPOSE 8100
CMD ["uvicorn","freshness_service.main:app","--host","0.0.0.0","--port","8100"]
