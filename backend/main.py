"""
Music Download Web API Server
基于 FastAPI 封装 musicdl 功能，支持 Web 页面下载
"""

import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
import shutil
import re

try:
    from musicdl import musicdl
    from musicdl.modules.utils.data import SongInfo
    MUSICDL_AVAILABLE = True
except ImportError:
    MUSICDL_AVAILABLE = False
    print("警告：musicdl 库未安装，请运行 pip install musicdl")


app = FastAPI(
    title="Music Download Web API",
    description="音乐下载服务 Web API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

TEMP_WORK_DIR = BASE_DIR / ".temp"
TEMP_WORK_DIR.mkdir(exist_ok=True)

SUPPORTED_SOURCES = [
    "NeteaseMusicClient",
    "QQMusicClient", 
    "KugouMusicClient",
    "KuwoMusicClient",
    "MiguMusicClient",
]

_client_cache = {}
_search_cache = {}


def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", str(filename))


def get_music_client(sources: List[str] = None):
    if not MUSICDL_AVAILABLE:
        raise HTTPException(status_code=500, detail="musicdl 库未安装")
    
    sources = sources or ["NeteaseMusicClient"]
    cache_key = tuple(sorted(sources))
    
    if cache_key not in _client_cache:
        cfg = {
            source: {
                "search_size_per_source": 20,
                "work_dir": str(TEMP_WORK_DIR),
            }
            for source in sources
        }
        _client_cache[cache_key] = musicdl.MusicClient(
            music_sources=sources,
            init_music_clients_cfg=cfg
        )
    
    return _client_cache[cache_key]


class SearchRequest(BaseModel):
    keyword: str
    sources: Optional[List[str]] = None


class DownloadRequest(BaseModel):
    identifier: str
    source: str
    song_name: str
    singers: str
    album: Optional[str] = ""
    ext: Optional[str] = "mp3"
    download_url: Optional[str] = None
    cover_url: Optional[str] = None
    duration: Optional[str] = ""
    file_size: Optional[str] = ""


class DownloadTask(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str


download_tasks = {}


@app.get("/")
async def root():
    return {
        "message": "Music Download Web API",
        "version": "1.0.0",
        "musicdl_available": MUSICDL_AVAILABLE
    }


@app.get("/sources")
async def get_sources():
    return {
        "sources": [
            {"id": "NeteaseMusicClient", "name": "网易云音乐", "enabled": True},
            {"id": "QQMusicClient", "name": "QQ音乐", "enabled": True},
            {"id": "KugouMusicClient", "name": "酷狗音乐", "enabled": True},
            {"id": "KuwoMusicClient", "name": "酷我音乐", "enabled": True},
            {"id": "MiguMusicClient", "name": "咪咕音乐", "enabled": True},
        ]
    }


@app.post("/search")
async def search_music(request: SearchRequest):
    if not MUSICDL_AVAILABLE:
        raise HTTPException(status_code=500, detail="musicdl 库未安装")
    
    try:
        sources = request.sources or SUPPORTED_SOURCES
        client = get_music_client(sources)
        
        results = client.search(keyword=request.keyword)
        
        for source_name, songs in results.items():
            if isinstance(songs, list):
                for song in songs:
                    if isinstance(song, dict):
                        key = f"{source_name}:{song.get('identifier', '')}"
                        if key:
                            try:
                                _search_cache[key] = SongInfo.fromdict(song)
                            except:
                                _search_cache[key] = song
                    else:
                        key = f"{source_name}:{getattr(song, 'identifier', '')}"
                        if key:
                            _search_cache[key] = song
        
        formatted_results = []
        for source_name, songs in results.items():
            if isinstance(songs, list):
                for song in songs:
                    formatted_results.append({
                        "song_name": song.get("song_name", "未知"),
                        "singers": song.get("singers", "未知"),
                        "album": song.get("album", "未知专辑"),
                        "source": source_name,
                        "identifier": song.get("identifier", ""),
                        "duration": song.get("duration", "00:00"),
                        "file_size": song.get("file_size", "未知"),
                        "cover_url": song.get("cover_url", ""),
                        "download_url": song.get("download_url", ""),
                        "ext": song.get("ext", "mp3"),
                    })
        
        return {
            "success": True,
            "count": len(formatted_results),
            "results": formatted_results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@app.post("/download")
async def download_music(
    request: DownloadRequest,
    background_tasks: BackgroundTasks
):
    import uuid
    task_id = str(uuid.uuid4())
    
    download_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "message": "等待下载...",
        "file_path": None
    }
    
    background_tasks.add_task(
        perform_download,
        task_id,
        request
    )
    
    return {"success": True, "task_id": task_id}


def get_cached_song(source: str, identifier: str):
    key = f"{source}:{identifier}"
    return _search_cache.get(key)


async def perform_download(task_id: str, request: DownloadRequest):
    temp_file_path = None
    
    try:
        download_tasks[task_id]["status"] = "downloading"
        download_tasks[task_id]["message"] = "正在初始化..."
        
        client = get_music_client([request.source])
        
        song_info = get_cached_song(request.source, request.identifier)
        
        if song_info:
            print(f"使用缓存的歌曲信息: {getattr(song_info, 'song_name', 'unknown')}")
        else:
            print(f"缓存未命中，构造歌曲信息")
            song_info = SongInfo.fromdict({
                "identifier": request.identifier,
                "song_name": request.song_name,
                "singers": request.singers,
                "source": request.source,
                "album": request.album or "",
                "ext": request.ext or "mp3",
                "download_url": request.download_url,
                "cover_url": request.cover_url,
                "duration": request.duration or "",
                "file_size": request.file_size or "",
            })
        
        download_tasks[task_id]["message"] = "正在下载..."
        download_tasks[task_id]["progress"] = 30.0
        
        try:
            downloaded_songs = client.download(song_infos=[song_info])
        except Exception as e:
            print(f"下载调用异常: {e}")
            import traceback
            traceback.print_exc()
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = f"下载调用失败: {str(e)}"
            return
        
        success = False
        print(f"下载返回结果: {downloaded_songs}")
        
        if not downloaded_songs:
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "下载失败：未返回任何结果"
            return
        
        for song in downloaded_songs:
            save_path = song.get("save_path") if isinstance(song, dict) else getattr(song, "save_path", None)
            if not save_path or not os.path.exists(save_path):
                continue
            
            song_name = song.get("song_name", "未知歌曲") if isinstance(song, dict) else getattr(song, "song_name", "未知歌曲")
            singers = song.get("singers", "未知歌手") if isinstance(song, dict) else getattr(song, "singers", "未知歌手")
            if isinstance(singers, list):
                singer = "&".join([str(s) for s in singers])
            else:
                singer = str(singers)
            
            album = song.get("album", "") if isinstance(song, dict) else getattr(song, "album", "")
            identifier = song.get("identifier", "") if isinstance(song, dict) else getattr(song, "identifier", "")
            
            ext = os.path.splitext(save_path)[1].lstrip(".")
            if not ext:
                ext = song.get("ext", "mp3") if isinstance(song, dict) else getattr(song, "ext", "mp3")
            
            parts = [song_name, singer]
            if album:
                parts.append(str(album))
            if identifier:
                parts.append(str(identifier))
            
            base_name = sanitize_filename("-".join(parts))
            new_audio_name = f"{base_name}.{ext}"
            new_audio_path = DOWNLOAD_DIR / new_audio_name
            temp_file_path = save_path
            
            try:
                if new_audio_path.exists():
                    new_audio_path.unlink()
                shutil.move(save_path, new_audio_path)
                
                old_lrc_path = os.path.splitext(save_path)[0] + ".lrc"
                if os.path.exists(old_lrc_path):
                    new_lrc_name = f"{base_name}.lrc"
                    new_lrc_path = DOWNLOAD_DIR / new_lrc_name
                    try:
                        if new_lrc_path.exists():
                            new_lrc_path.unlink()
                        shutil.move(old_lrc_path, new_lrc_path)
                    except Exception as e:
                        print(f"移动歌词文件失败: {e}")
                
                download_tasks[task_id]["status"] = "completed"
                download_tasks[task_id]["progress"] = 100.0
                download_tasks[task_id]["message"] = "下载完成"
                download_tasks[task_id]["file_path"] = str(new_audio_path)
                download_tasks[task_id]["file_name"] = new_audio_name
                success = True
                break
                
            except Exception as e:
                print(f"移动文件失败 {save_path}: {e}")
                continue
        
        if not success:
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "下载失败：未找到文件或移动失败"
    
    except Exception as e:
        download_tasks[task_id]["status"] = "failed"
        download_tasks[task_id]["message"] = f"下载失败: {str(e)}"


@app.get("/download/{task_id}")
async def get_download_status(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return download_tasks[task_id]


@app.get("/download/{task_id}/file")
async def get_download_file(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = download_tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="文件尚未下载完成")
    
    file_path = task.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_name = task.get("file_name", "music.mp3")
    ext = os.path.splitext(file_name)[1].lower()
    
    media_types = {
        '.mp3': 'audio/mpeg',
        '.flac': 'audio/flac',
        '.m4a': 'audio/mp4',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.lrc': 'text/plain',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    def file_iterator():
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
        
        try:
            os.remove(file_path)
            print(f"已删除服务器上的文件: {file_path}")
            
            lrc_path = os.path.splitext(file_path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                os.remove(lrc_path)
                print(f"已删除歌词文件: {lrc_path}")
        except Exception as e:
            print(f"删除文件失败: {e}")
    
    return StreamingResponse(
        file_iterator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{file_name}"
        }
    )


@app.get("/downloads")
async def list_downloads():
    files = []
    for f in DOWNLOAD_DIR.rglob("*"):
        if f.is_file() and f.suffix.lower() in ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.lrc']:
            stat = f.stat()
            files.append({
                "name": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "path": str(f)
            })
    
    return {"files": sorted(files, key=lambda x: x["modified"], reverse=True)}


@app.delete("/downloads/{filename}")
async def delete_download(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if file_path.exists():
        file_path.unlink()
        return {"success": True, "message": "文件已删除"}
    else:
        raise HTTPException(status_code=404, detail="文件不存在")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
