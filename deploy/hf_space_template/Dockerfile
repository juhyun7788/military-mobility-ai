# Hugging Face Spaces (Docker) — 지능형 기동지원 군사상황 정보판단 프로그램 공개 시연판
FROM python:3.12-slim

# 영상 처리(OpenCV)와 한글 글꼴(위협 이름표)용 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# Spaces 권장: uid 1000 사용자로 실행
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics \
    PUBLIC_DEMO=1
WORKDIR /home/user/app

# PyTorch는 CPU 전용판으로 (이미지 용량 절약)
COPY --chown=user requirements-space.txt .
RUN pip install --no-cache-dir --user torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --user -r requirements-space.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "7860"]
