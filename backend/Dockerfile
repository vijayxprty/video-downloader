# Hugging Face Spaces — Docker SDK (free CPU).
# To deploy later: push the CONTENTS of backend/ as the root of a new
# Docker Space repo. Do not put secrets or tokens in this image.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
ENV HOST=0.0.0.0 PORT=7860
EXPOSE 7860
CMD ["python", "server.py"]
