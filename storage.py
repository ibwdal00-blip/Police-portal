import json
import os
import threading


class Storage:
    """يحفظ بيانات كل سيرفر في ملف JSON على القرص.
    كل سيرفر ممكن يكون فيه أكثر من عداد مستقل (مثل: سحب، مراقبة)."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    self.data = json.load(f)
                except json.JSONDecodeError:
                    self.data = {}
        else:
            self.data = {}
            self.save()

    def get_guild(self, guild_id) -> dict:
        key = str(guild_id)
        if key not in self.data:
            self.data[key] = {
                "support_role_id": None,
                "report_channel_id": None,
                "log_channel_id": None,
                "last_daily_reset": None,
                "counters": {},
            }
        # توافق مع بيانات قديمة ما فيها "counters"
        self.data[key].setdefault("counters", {})
        return self.data[key]

    def get_counter(self, guild_id, counter_key: str) -> dict:
        guild = self.get_guild(guild_id)
        if counter_key not in guild["counters"]:
            guild["counters"][counter_key] = {
                "daily": 0,
                "weekly": 0,
                "panel_channel_id": None,
                "panel_message_id": None,
            }
        return guild["counters"][counter_key]

    def save(self):
        with self.lock:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
