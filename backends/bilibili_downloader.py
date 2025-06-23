import requests
import json
import re
import os
from urllib.parse import urlparse, parse_qs
import subprocess
import tempfile
import time
import sys

class BilibiliDownloader:
    def __init__(self, download_path=None):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # 设置默认下载路径
        if download_path is None:
            self.download_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "downloads")
        else:
            self.download_path = download_path
        
        # 确保下载目录存在
        os.makedirs(self.download_path, exist_ok=True)
    
    def set_download_path(self, path):
        """设置下载路径"""
        self.download_path = path
        os.makedirs(self.download_path, exist_ok=True)
        
    def get_bvid_from_url(self, url):
        """从URL中提取BVID"""
        parsed_url = urlparse(url)
        if 'bilibili.com' not in parsed_url.netloc:
            raise ValueError("不是有效的B站视频链接")
            
        # 尝试从路径中提取BVID
        path = parsed_url.path
        bvid_match = re.search(r'/video/(BV\w+)', path)
        if bvid_match:
            return bvid_match.group(1)
            
        # 尝试从查询参数中提取
        query_params = parse_qs(parsed_url.query)
        if 'bvid' in query_params:
            return query_params['bvid'][0]
            
        raise ValueError("无法从URL中提取BVID")
        
    def get_video_info(self, bvid):
        """获取视频信息"""
        url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
        response = requests.get(url, headers=self.headers)
        data = response.json()
        
        if data['code'] != 0:
            raise Exception(f"获取视频信息失败: {data['message']}")
            
        return data['data']
        
    def get_audio_url(self, bvid):
        """获取音频URL"""
        url = f'https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={self.get_video_info(bvid)["cid"]}&qn=0&fnval=16&fourk=1'
        response = requests.get(url, headers=self.headers)
        data = response.json()
        
        if data['code'] != 0:
            raise Exception(f"获取音频URL失败: {data['message']}")
            
        return data['data']['dash']['audio'][0]['baseUrl']
        
    def download_audio(self, url, output_path):
        """下载音频并转换为MP3格式"""
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as temp_file:
                temp_path = temp_file.name
                
            # 下载音频，添加Referer头
            headers = self.headers.copy()
            headers['Referer'] = 'https://www.bilibili.com/'
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        
            # 使用ffmpeg转换为MP3
            # 针对Windows平台，隐藏FFmpeg终端窗口
            startupinfo = None
            creation_flags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creation_flags = subprocess.CREATE_NO_WINDOW

            subprocess.run([
                'ffmpeg', '-i', temp_path,
                '-vn', '-acodec', 'libmp3lame',
                '-q:a', '2', output_path, "-y"
            ], check=True, startupinfo=startupinfo, creationflags=creation_flags)
            
            # 清理临时文件
            os.unlink(temp_path)
            
            return output_path
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise Exception(f"下载或转换音频失败: {str(e)}")
            
    def download_from_url(self, url, output_path=None):
        bvid = self.get_bvid_from_url(url)
        video_info = self.get_video_info(bvid)
        title = video_info.get('title', f'bilibili_{int(time.time())}')
        # 清理标题中的非法文件名字符
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        if output_path is None:
            # 使用实例的下载路径
            output_path = os.path.join(self.download_path, f"{safe_title}.mp3")
        audio_url = self.get_audio_url(bvid)
        return self.download_audio(audio_url, output_path) 