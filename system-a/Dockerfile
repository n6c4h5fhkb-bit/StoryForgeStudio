FROM python:3.13-slim
WORKDIR /opt/studio
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY tools ./tools
ENV STUDIO_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8787"]
