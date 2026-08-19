"""
ملف اختياري: يشغّل سيرفر ويب بسيط جدًا
تحتاجه فقط إذا رفعت البوت على Render كـ "Web Service" (وليس Background Worker)
لأن خطة الويب المجانية تتطلب أن يستقبل التطبيق طلبات HTTP حتى لا "ينام".

طريقة الاستخدام:
1. في أعلى bot.py أضف: from keep_alive import keep_alive
2. قبل bot.run(TOKEN) أضف سطر: keep_alive()
3. استخدم خدمة مثل UptimeRobot لعمل بينغ على رابط الموقع كل 5 دقائق
"""

from flask import Flask
from threading import Thread

app = Flask(__name__)


@app.route("/")
def home():
    return "✅ البوت شغّال"


def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
