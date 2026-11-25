FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TOXIFRUIT_CHECKPOINT=/app/outputs/food_fraud_toxifruit_vegetable_grouped_letterbox_v2/best_model.pt
WORKDIR /app
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch==2.6.0 torchvision==0.21.0
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY main.py predictor.py /app/
RUN useradd --system --user-group --home-dir /app app
USER app
EXPOSE 8101
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8101"]
