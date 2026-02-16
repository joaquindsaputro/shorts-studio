FROM python:3.12-slim

# Instal FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Siapkan folder kerja
WORKDIR /app
COPY . /app

# Instal pustaka Python
RUN pip install Flask ffmpeg-python werkzeug

# Buka port dan jalankan aplikasi
EXPOSE 8080
CMD ["python", "main.py"]