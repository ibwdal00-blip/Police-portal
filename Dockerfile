FROM python:3.12-slim

WORKDIR /app

# تثبيت المكتبات أولًا (طبقة منفصلة تستفيد من الكاش)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات البوت
COPY . .

CMD ["python", "bot.py"]
