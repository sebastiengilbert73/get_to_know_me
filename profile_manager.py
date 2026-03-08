import os
import json

PROFILE_FILE = "user_profile.txt"

class ProfileManager:
    def __init__(self, filepath=PROFILE_FILE):
        self.filepath = filepath
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4, ensure_ascii=False)
    
    def read_profile(self):
        with open(self.filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            # Try to parse as JSON. If it fails, assume it's the old text format and wrap it.
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"Uncategorized Notes": content}

    def update_profile(self, new_content):
        # new_content could be a dict or a string representing JSON or raw text
        if isinstance(new_content, str):
            try:
                # Try parsing it to ensure it is valid JSON before writing, if intended as JSON
                parsed = json.loads(new_content)
                # Dump it back to ensure uniform formatting and proper unicode characters
                write_data = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError:
                # If they try to write raw string that isn't JSON, bundle it up
                write_data = json.dumps({"Uncategorized Notes": new_content}, indent=4, ensure_ascii=False)
        else:
            # It's a dict
            write_data = json.dumps(new_content, indent=4, ensure_ascii=False)

        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(write_data)
