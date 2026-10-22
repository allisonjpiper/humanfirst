# Hugging Face Spaces (Docker SDK) image for Human First.
# Secrets PORTKEY_API_KEY and ADMIN_PASSWORD are set in the Space's settings, never in this repo.
FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HUMANFIRST_HOST=0.0.0.0 \
    HUMANFIRST_PORT=7860 \
    HUMANFIRST_DB=/home/user/app/data/humanfirst.db \
    PYDANTIC_AI_NO_BANNER=1 \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user backend backend
COPY --chown=user extension extension
RUN mkdir -p data

EXPOSE 7860
CMD ["python", "backend/app.py"]
