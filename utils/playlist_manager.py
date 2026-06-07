import json
import os
from .config import CONFIG_PATH


class PlaylistManager:
    def __init__(self, config_path=None):
        self.config_path = config_path or CONFIG_PATH
        self.playlists = {}
        self.next_play_queue = []
        self.current_playlist = "默认播放列表"
        self.load_playlists()

    def create_playlist(self, name):
        if name not in self.playlists:
            self.playlists[name] = []
            self.save_playlists()
            return True
        return False

    def delete_playlist(self, name):
        if name in self.playlists and name != "默认播放列表":
            del self.playlists[name]
            if self.current_playlist == name:
                self.current_playlist = "默认播放列表"
            self.save_playlists()
            return True
        return False

    def rename_playlist(self, old_name, new_name):
        if old_name in self.playlists and new_name not in self.playlists:
            self.playlists[new_name] = self.playlists.pop(old_name)
            if self.current_playlist == old_name:
                self.current_playlist = new_name
            self.save_playlists()
            return True
        return False

    def add_to_playlist(self, playlist_name, file_path):
        if playlist_name in self.playlists:
            if file_path not in self.playlists[playlist_name]:
                self.playlists[playlist_name].append(file_path)
                self.save_playlists()
                return True
        return False

    def remove_from_playlist(self, playlist_name, file_path):
        if playlist_name in self.playlists and file_path in self.playlists[playlist_name]:
            self.playlists[playlist_name].remove(file_path)
            self.save_playlists()
            return True
        return False

    def get_playlist(self, name):
        return self.playlists.get(name, [])

    def get_playlist_names(self):
        return list(self.playlists.keys())

    def set_current_playlist(self, name):
        if name in self.playlists:
            self.current_playlist = name
            self.save_playlists()
            return True
        return False

    def add_to_next_play(self, file_path):
        if file_path not in self.next_play_queue:
            self.next_play_queue.append(file_path)

    def get_next_from_queue(self):
        if self.next_play_queue:
            return self.next_play_queue.pop(0)
        return None

    def clear_next_play_queue(self):
        self.next_play_queue = []

    def move_in_playlist(self, playlist_name, old_index, new_index):
        if playlist_name in self.playlists:
            playlist = self.playlists[playlist_name]
            if 0 <= old_index < len(playlist) and 0 <= new_index < len(playlist):
                item = playlist.pop(old_index)
                playlist.insert(new_index, item)
                self.save_playlists()
                return True
        return False

    def load_playlists(self):
        try:
            playlist_file = os.path.join(self.config_path, "playlists.json")
            if os.path.exists(playlist_file):
                with open(playlist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.playlists = data.get("playlists", {})
                    self.current_playlist = data.get("current_playlist", "默认播放列表")

                    for name, playlist in self.playlists.items():
                        if not isinstance(playlist, list):
                            print(f"警告: 播放列表 '{name}' 数据格式错误，重置为空列表")
                            self.playlists[name] = []

                    if "默认播放列表" not in self.playlists:
                        self.playlists["默认播放列表"] = []
            else:
                self.playlists = {"默认播放列表": []}

                old_playlist_file = os.path.join(self.config_path, "playlist.json")
                if os.path.exists(old_playlist_file):
                    try:
                        with open(old_playlist_file, 'r', encoding='utf-8') as f:
                            old_playlist = json.load(f)
                            if isinstance(old_playlist, list):
                                self.playlists["默认播放列表"] = old_playlist
                            else:
                                print("警告: 旧播放列表格式错误，使用空列表")
                                self.playlists["默认播放列表"] = []
                    except (json.JSONDecodeError, FileNotFoundError):
                        pass

        except (json.JSONDecodeError, FileNotFoundError):
            self.playlists = {"默认播放列表": []}
            self.current_playlist = "默认播放列表"

    def save_playlists(self):
        if hasattr(self, '_saving_playlists') and self._saving_playlists:
            return

        self._saving_playlists = True

        try:
            playlist_file = os.path.join(self.config_path, "playlists.json")

            clean_playlists = {}
            for name, playlist in self.playlists.items():
                if isinstance(playlist, list):
                    clean_list = []
                    for item in playlist:
                        if isinstance(item, str) and item.strip():
                            clean_list.append(item.strip())
                    clean_playlists[str(name)] = clean_list
                else:
                    clean_playlists[str(name)] = []

            current_playlist = str(self.current_playlist) if self.current_playlist else "默认播放列表"

            data = {
                "playlists": clean_playlists,
                "current_playlist": current_playlist
            }

            try:
                json.dumps(data, ensure_ascii=False)
            except (TypeError, ValueError):
                data = {
                    "playlists": {"默认播放列表": []},
                    "current_playlist": "默认播放列表"
                }

            with open(playlist_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception:
            try:
                with open(os.path.join(self.config_path, "playlists_backup.json"), 'w', encoding='utf-8') as f:
                    json.dump({"playlists": {"默认播放列表": []}, "current_playlist": "默认播放列表"}, f)
            except:
                pass
        finally:
            self._saving_playlists = False
