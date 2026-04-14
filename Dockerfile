FROM python:3.11-slim

# Вот эта строчка устанавливает ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

COPY . /app
WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
