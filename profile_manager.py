import os
import json

PROFILES_DIR = "profiles"

class ProfileManager:
    def __init__(self, username="default"):
        os.makedirs(PROFILES_DIR, exist_ok=True)
        self.set_user(username)

    def set_user(self, username):
        """Switch to a different user's profile."""
        self.username = username
        self.filepath = os.path.join(PROFILES_DIR, f"{username}.json")
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4, ensure_ascii=False)

    @staticmethod
    def list_users():
        """Return a list of existing usernames (derived from filenames in profiles/)."""
        os.makedirs(PROFILES_DIR, exist_ok=True)
        users = []
        for f in sorted(os.listdir(PROFILES_DIR)):
            if f.endswith(".json"):
                users.append(f[:-5])  # Strip .json extension
        return users

    def read_profile(self):
        with open(self.filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"Uncategorized Notes": content}

    def update_profile(self, new_content):
        if isinstance(new_content, str):
            try:
                parsed = json.loads(new_content)
                write_data = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError:
                write_data = json.dumps({"Uncategorized Notes": new_content}, indent=4, ensure_ascii=False)
        else:
            write_data = json.dumps(new_content, indent=4, ensure_ascii=False)

        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(write_data)
