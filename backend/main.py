"""
Music Download Web API Server
基于 FastAPI 封装 musicdl 功能，支持 Web 页面下载
"""

import sys
import io
import os
import logging

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from urllib.parse import quote
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
import shutil
import re
import requests
import threading

try:
    from musicdl import musicdl
    from musicdl.modules.utils.data import SongInfo
    MUSICDL_AVAILABLE = True
    logger.info("musicdl 模块加载成功")
except ImportError as e:
    MUSICDL_AVAILABLE = False
    logger.error(f"musicdl 模块加载失败: {e}")


BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

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

STATIC_DIR = PROJECT_ROOT / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"静态文件目录已挂载: {STATIC_DIR}")

TEMP_WORK_DIR = BASE_DIR / ".temp"
TEMP_WORK_DIR.mkdir(exist_ok=True)

SUPPORTED_SOURCES = [
    {"id": "AppleMusicClient", "name": "苹果音乐"},
    {"id": "DeezerMusicClient", "name": "Deezer"},
    {"id": "FiveSingMusicClient", "name": "5sing"},
    {"id": "JamendoMusicClient", "name": "Jamendo"},
    {"id": "JooxMusicClient", "name": "Joox"},
    {"id": "KuwoMusicClient", "name": "酷我音乐"},
    {"id": "KugouMusicClient", "name": "酷狗音乐"},
    {"id": "MiguMusicClient", "name": "咪咕音乐"},
    {"id": "NeteaseMusicClient", "name": "网易云音乐"},
    {"id": "QQMusicClient", "name": "QQ音乐"},
    {"id": "QianqianMusicClient", "name": "千千音乐"},
    {"id": "QobuzMusicClient", "name": "Qobuz"},
    {"id": "SoundCloudMusicClient", "name": "SoundCloud"},
    {"id": "StreetVoiceMusicClient", "name": "StreetVoice"},
    {"id": "SodaMusicClient", "name": "汽水音乐"},
    {"id": "SpotifyMusicClient", "name": "Spotify"},
    {"id": "TIDALMusicClient", "name": "TIDAL"},
]

ENABLED_SOURCES = [s["id"] for s in SUPPORTED_SOURCES]

_search_cache = {}
_music_client_cache = {}


def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", str(filename))


def get_music_client(sources: List[str], search_size: int = 10):
    if not MUSICDL_AVAILABLE:
        logger.error("musicdl 不可用")
        raise HTTPException(status_code=500, detail="musicdl 库未安装")
    
    if not sources or len(sources) == 0:
        logger.error("[get_music_client] sources 为空")
        raise HTTPException(status_code=400, detail="请至少选择一个音乐源")
    
    cache_key = f"{sorted(sources)}:{search_size}"
    if cache_key in _music_client_cache:
        logger.info(f"使用缓存的 musicdl 客户端: {sources}")
        return _music_client_cache[cache_key]
    
    logger.info(f"创建 musicdl 客户端: {sources}, search_size: {search_size}")
    
    cfg = {}
    for source in sources:
        cfg[source] = {
            "search_size_per_source": search_size,
            "work_dir": str(TEMP_WORK_DIR),
            "maintain_session": True,  # 保持 session 连接复用，提高下载速度
            "max_retries": 3,  # 最大重试次数
        }
    
    try:
        client = musicdl.MusicClient(
            music_sources=list(sources),
            init_music_clients_cfg=cfg
        )
        logger.info(f"musicdl 客户端创建成功")
        _music_client_cache[cache_key] = client
        return client
    except Exception as e:
        logger.error(f"创建 musicdl 客户端失败: {e}")
        import traceback
        traceback.print_exc()
        raise


class SearchRequest(BaseModel):
    keyword: str
    sources: Optional[List[str]] = None
    search_size: Optional[int] = 10


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
    index_path = PROJECT_ROOT / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Music Download Web API", "version": "1.0.0"}


@app.get("/sources")
async def get_sources():
    return {"sources": SUPPORTED_SOURCES}


def get_file_format(song_info):
    """与原项目相同的格式获取逻辑（支持字典和对象）"""
    # 安全获取字段值
    def get_safe(obj, field, default=""):
        if isinstance(obj, dict):
            return obj.get(field, default)
        try:
            return getattr(obj, field, default)
        except:
            return default
    
    for field in ["format", "ext", "file_format", "type"]:
        value = get_safe(song_info, field)
        if value:
            return str(value).upper()
    
    url = str(get_safe(song_info, "download_url", "")).lower()
    for ext in ["mp3", "flac", "wav", "m4a", "aac"]:
        if f".{ext}" in url:
            return ext.upper()
    return "未知"


def get_album_image_url(song_info):
    """与原项目相同的封面获取逻辑（支持字典和对象）"""
    # 安全获取字段值
    def get_safe(obj, field, default=""):
        if isinstance(obj, dict):
            return obj.get(field, default)
        try:
            return getattr(obj, field, default)
        except:
            return default
    
    for field in [
        "cover",
        "album_cover",
        "pic",
        "picture",
        "img",
        "image",
        "album_img",
        "album_pic",
        "cover_url",
        "pic_url",
    ]:
        url = str(get_safe(song_info, field, ""))
        if url.startswith("http"):
            return url
    return ""


@app.post("/search")
async def search_music(request: SearchRequest):
    if not MUSICDL_AVAILABLE:
        logger.error("搜索失败: musicdl 不可用")
        raise HTTPException(status_code=500, detail="musicdl 库未安装")
    
    try:
        search_size = request.search_size if request.search_size else 10
        logger.info(f"[POST /search] keyword: {request.keyword}, sources: {request.sources}, search_size: {search_size}")
        
        sources = request.sources
        if sources is None or len(sources) == 0:
            sources = ENABLED_SOURCES
            logger.warning("[POST /search] sources 为空，使用 ENABLED_SOURCES")
        
        client = get_music_client(sources, search_size=search_size)
        
        logger.info(f"[POST /search] 调用 client.search()...")
        results = client.search(keyword=request.keyword)
        
        logger.info(f"[POST /search] 搜索完成，返回的源: {list(results.keys())}")
        
        formatted_results = []
        source_count = {}
        
        for source_name, songs in results.items():
            if isinstance(songs, list):
                source_count[source_name] = len(songs)
                for song in songs:
                    # 与原项目完全相同：直接使用 song 对象本身
                    
                    # 安全获取字段值的辅助函数
                    def get_field(obj, field, default=""):
                        if isinstance(obj, dict):
                            return obj.get(field, default)
                        try:
                            return getattr(obj, field, default)
                        except:
                            return default
                    
                    # 添加调试日志，打印出 song 对象的所有可用属性
                    if isinstance(song, dict):
                        logger.debug(f"[调试] 歌曲字典键: {list(song.keys())}")
                        if 'raw_data' in song:
                            logger.debug(f"[调试] raw_data 内容: {song['raw_data']}")
                    else:
                        try:
                            logger.debug(f"[调试] 歌曲对象属性: {dir(song)}")
                            if hasattr(song, 'raw_data'):
                                logger.debug(f"[调试] raw_data 内容: {song.raw_data}")
                        except:
                            pass
                    
                    # 获取字段值（与原项目相同的逻辑）
                    song_name = str(get_field(song, "song_name", ""))
                    singers = get_field(song, "singers", "")
                    if isinstance(singers, list):
                        singers = '&'.join([str(s) for s in singers])
                    singers = str(singers)
                    album = str(get_field(song, "album", ""))
                    duration = str(get_field(song, "duration", ""))
                    download_url = str(get_field(song, "download_url", ""))
                    identifier = str(get_field(song, "identifier", ""))
                    
                    # 与原项目完全相同的逻辑：直接从 SongInfo 对象获取字段
                    file_size = str(get_field(song, "file_size", ""))
                    ext = get_file_format(song)
                    cover_url = ""
                    
                    # 调试日志
                    logger.debug(f"[调试] 歌曲名: {song_name}, file_size={file_size}, ext={ext}")
                    
                    # 从MINFO解析FLAC版本的大小（与原项目一致）
                    raw_data = get_field(song, "raw_data", {})
                    if raw_data and isinstance(raw_data, dict):
                        search_data = raw_data.get("search", {})
                        if search_data and isinstance(search_data, dict):
                            minfo = search_data.get("MINFO", "")
                            if minfo and isinstance(minfo, str):
                                # 解析MINFO，找到FLAC版本的大小
                                # 格式: level:ff,bitrate:2000,format:flac,size:52.83Mb;...
                                for segment in minfo.split(";"):
                                    if "format:flac" in segment and "size:" in segment:
                                        for part in segment.split(","):
                                            if part.startswith("size:"):
                                                flac_size = part.replace("size:", "").strip()
                                                if flac_size:
                                                    file_size = flac_size
                                                    break
                                        if file_size and "Mb" in file_size:
                                            break
                    
                    # 封面：优先从 raw_data 中获取（酷我源有更好的封面）
                    if raw_data and isinstance(raw_data, dict):
                        search_data = raw_data.get("search", {})
                        if search_data and isinstance(search_data, dict):
                            web_albumpic = search_data.get("web_albumpic_short", "")
                            if web_albumpic:
                                cover_url = f"https://img1.kuwo.cn/star/albumcover/{web_albumpic}"
                            if not cover_url:
                                hts_mvpic = search_data.get("hts_MVPIC", "")
                                if hts_mvpic:
                                    cover_url = hts_mvpic
                            if not cover_url:
                                mvpic = search_data.get("MVPIC", "")
                                if mvpic:
                                    cover_url = f"https://img2.kuwo.cn/wmvpic/{mvpic}"
                    
                    # 如果 raw_data 没有封面，用原项目的逻辑
                    if not cover_url:
                        cover_url = get_album_image_url(song)
                    
                    # 对于酷我音乐，如果 download_url 是 jymaster 级别，尝试获取 ff 级别的 URL
                    # 这样下载的文件大小会与搜索显示的一致
                    if source_name == 'KuwoMusicClient' and download_url and 'level=jymaster' in download_url:
                        logger.info(f"[搜索] 检测到 jymaster URL，尝试获取 ff 级别 URL: {song_name}")
                        try:
                            # 获取 KuwoMusicClient 实例
                            kuwo_client = None
                            if hasattr(client, 'music_clients') and 'KuwoMusicClient' in client.music_clients:
                                kuwo_client = client.music_clients['KuwoMusicClient']
                            
                            if kuwo_client and raw_data and isinstance(raw_data, dict):
                                search_result = raw_data.get('search', {})
                                if search_result:
                                    # 尝试使用 nxinxz 解析器（它支持 lossless 级别）
                                    try:
                                        song_info_nxinxz = kuwo_client._parsewithnxinxzapi(search_result)
                                        if song_info_nxinxz and getattr(song_info_nxinxz, 'with_valid_download_url', False):
                                            nxinxz_url = getattr(song_info_nxinxz, 'download_url', '')
                                            nxinxz_size = getattr(song_info_nxinxz, 'file_size', '')
                                            nxinxz_ext = getattr(song_info_nxinxz, 'ext', 'mp3')
                                            
                                            # 检查文件大小是否接近搜索显示的 ff 级别大小
                                            # 如果 nxinxz 返回的大小接近 ff 级别，使用它
                                            if nxinxz_url:
                                                logger.info(f"[搜索] nxinxz 解析器成功: size={nxinxz_size}, url={nxinxz_url[:80]}...")
                                                download_url = nxinxz_url
                                                ext = nxinxz_ext
                                                # 更新 song 对象的 download_url
                                                if isinstance(song, SongInfo):
                                                    song.download_url = nxinxz_url
                                                    song.ext = nxinxz_ext
                                                elif isinstance(song, dict):
                                                    song['download_url'] = nxinxz_url
                                                    song['ext'] = nxinxz_ext
                                    except Exception as e:
                                        logger.warning(f"[搜索] nxinxz 解析器失败: {e}")
                        except Exception as e:
                            logger.warning(f"[搜索] 尝试获取 ff 级别 URL 失败: {e}")
                    
                    formatted_results.append({
                        "song_name": song_name,
                        "singers": singers,
                        "album": album,
                        "source": source_name,
                        "identifier": identifier,
                        "duration": duration,
                        "file_size": file_size,
                        "cover_url": cover_url,
                        "download_url": download_url,
                        "ext": ext,
                    })
                    
                    key = f"{source_name}:{identifier}"
                    if key:
                        try:
                            if isinstance(song, dict):
                                _search_cache[key] = SongInfo.fromdict(song)
                            else:
                                _search_cache[key] = song
                        except:
                            if isinstance(song, dict):
                                _search_cache[key] = song
        
        logger.info(f"[POST /search] 各源歌曲数量: {source_count}")
        logger.info(f"[POST /search] 返回 {len(formatted_results)} 个搜索结果")
        
        return {
            "success": True,
            "count": len(formatted_results),
            "source_count": source_count,
            "results": formatted_results
        }
    
    except Exception as e:
        logger.error(f"[POST /search] 搜索失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@app.post("/download")
async def download_music(
    request: DownloadRequest,
    background_tasks: BackgroundTasks
):
    import uuid
    task_id = str(uuid.uuid4())
    
    logger.info(f"[POST /download] task_id: {task_id}, song: {request.song_name}, source: {request.source}")
    
    download_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "message": "等待下载...",
        "file_path": None,
        "file_name": None,
        "request": request.dict()
    }
    
    background_tasks.add_task(
        perform_download,
        task_id,
        request
    )
    
    return {"success": True, "task_id": task_id}


@app.post("/download/{task_id}/retry")
async def retry_download(
    task_id: str,
    background_tasks: BackgroundTasks
):
    logger.info(f"[POST /download/{task_id}/retry] 重新下载任务")
    
    if task_id not in download_tasks:
        logger.warning(f"任务不存在: {task_id}")
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = download_tasks[task_id]
    request_data = task.get("request")
    
    if not request_data:
        logger.warning(f"任务没有保存请求信息: {task_id}")
        raise HTTPException(status_code=400, detail="任务没有保存请求信息，无法重新下载")
    
    # 重置任务状态
    download_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "message": "等待重新下载...",
        "file_path": None,
        "file_name": None,
        "request": request_data
    }
    
    # 重新创建 DownloadRequest 对象
    request = DownloadRequest(**request_data)
    
    background_tasks.add_task(
        perform_download,
        task_id,
        request
    )
    
    logger.info(f"[{task_id}] 重新下载任务已创建")
    return {"success": True, "task_id": task_id}


def get_cached_song(source: str, identifier: str):
    key = f"{source}:{identifier}"
    result = _search_cache.get(key)
    logger.debug(f"[get_cached_song] key={key}, 命中={result is not None}")
    return result


async def perform_download(task_id: str, request: DownloadRequest):
    
    def _get_val(obj, key, default=""):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default) if hasattr(obj, key) else default
    
    try:
        logger.info(f"[{task_id}] 开始下载任务")
        download_tasks[task_id]["status"] = "downloading"
        download_tasks[task_id]["message"] = "正在初始化..."
        
        if not MUSICDL_AVAILABLE:
            logger.error(f"[{task_id}] musicdl 不可用")
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "musicdl 库未安装"
            return
        
        client = get_music_client([request.source])
        
        song_info = get_cached_song(request.source, request.identifier)
        
        if song_info:
            logger.info(f"[{task_id}] 使用缓存的歌曲信息: {_get_val(song_info, 'song_name', 'unknown')}")
        else:
            logger.info(f"[{task_id}] 缓存未命中，构造歌曲信息")
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
        
        download_tasks[task_id]["message"] = "正在获取下载链接..."
        download_tasks[task_id]["progress"] = 10.0
        
        # 获取下载URL
        download_url = _get_val(song_info, "download_url", "")
        
        # 对于酷我音乐，如果缓存的 URL 是 jymaster 级别，尝试改为 ff 级别
        # 这样下载的文件大小会与搜索显示的一致
        if request.source == 'KuwoMusicClient' and download_url and 'level=jymaster' in download_url:
            identifier = _get_val(song_info, "identifier", "")
            if identifier:
                ff_url = f"http://kw.006lp.ccwu.cc:7119/api/song?id={identifier}&level=ff&stream=1"
                logger.info(f"[{task_id}] 将 jymaster URL 替换为 ff URL: {ff_url}")
                # 修改 song_info 的 download_url，这样 client.download() 会使用新的 URL
                if isinstance(song_info, SongInfo):
                    song_info.download_url = ff_url
                elif isinstance(song_info, dict):
                    song_info['download_url'] = ff_url
                download_url = ff_url
        
        if not download_url:
            logger.error(f"[{task_id}] 下载URL为空")
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "下载链接无效"
            return
        
        logger.info(f"[{task_id}] 下载URL: {download_url[:100]}...")
        
        # 构建保存路径
        song_name = _get_val(song_info, "song_name", "未知歌曲")
        singers = _get_val(song_info, "singers", "未知歌手")
        if isinstance(singers, list):
            singer = "&".join([str(s) for s in singers])
        else:
            singer = str(singers)
        
        album = _get_val(song_info, "album", "")
        identifier = _get_val(song_info, "identifier", "")
        ext = _get_val(song_info, "ext", "mp3")
        
        parts = [song_name, singer]
        if album:
            parts.append(str(album))
        if identifier:
            parts.append(str(identifier))
        
        base_name = sanitize_filename("-".join(parts))
        file_name = f"{base_name}.{ext}"
        save_path = str(TEMP_WORK_DIR / file_name)
        
        logger.info(f"[{task_id}] 保存路径: {save_path}")
        
        # 使用 musicdl 的 download 方法下载（与原项目完全一致）
        downloaded_songs = []
        try:
            logger.info(f"[{task_id}] 使用 musicdl download 下载...")
            
            download_tasks[task_id]["message"] = "正在下载文件..."
            
            # 确保 song_info 是 SongInfo 对象且有正确的 work_dir
            if isinstance(song_info, SongInfo):
                song_info.work_dir = str(TEMP_WORK_DIR)
            
            # 使用 client.download 方法（与原项目一致）
            downloaded_songs = client.download(song_infos=[song_info])
            
            logger.info(f"[{task_id}] musicdl download 返回: {len(downloaded_songs)} 个结果")
            
        except Exception as e:
            logger.warning(f"[{task_id}] musicdl download 失败: {e}")
        
        # 如果 musicdl download 失败或返回空，尝试直接下载缓存的 URL
        if not downloaded_songs:
            try:
                logger.info(f"[{task_id}] musicdl download 返回空，尝试直接下载...")
                download_tasks[task_id]["message"] = "正在直接下载..."
                
                # 获取缓存的 download_url
                direct_url = _get_val(song_info, 'download_url', '')
                if direct_url:
                    resp = requests.get(direct_url, stream=True, timeout=120)
                    resp.raise_for_status()
                    
                    actual_size = int(resp.headers.get('Content-Length', 0))
                    logger.info(f"[{task_id}] HTTP 响应大小: {actual_size} bytes ({actual_size / 1024 / 1024:.2f} MB)")
                    
                    downloaded_size = 0
                    with open(save_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                    
                    logger.info(f"[{task_id}] 直接下载完成: {downloaded_size} bytes ({downloaded_size / 1024 / 1024:.2f} MB)")
                    
                    downloaded_songs = [{
                        'save_path': save_path,
                        'song_name': song_name,
                        'singers': singers,
                        'album': album,
                        'identifier': identifier,
                        'ext': ext
                    }]
                
            except Exception as e:
                logger.error(f"[{task_id}] 直接下载也失败了: {e}")
        
        if not downloaded_songs:
            logger.error(f"[{task_id}] 所有下载方法都失败了")
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "下载失败：所有下载源都不可用"
            return
        
        download_tasks[task_id]["progress"] = 95.0
        download_tasks[task_id]["message"] = "正在处理文件..."
        
        success_count = 0
        final_file_path = None
        final_file_name = None
        
        if not downloaded_songs:
            logger.warning(f"[{task_id}] 下载失败：未返回任何结果")
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "下载失败：未返回任何结果"
            return
        
        for song in downloaded_songs:
            save_path = _get_val(song, "save_path")
            if not save_path or not os.path.exists(save_path):
                logger.warning(f"[{task_id}] 文件不存在: {save_path}")
                continue
            
            song_name = _get_val(song, "song_name", "未知歌曲")
            singers = _get_val(song, "singers", "未知歌手")
            if isinstance(singers, list):
                singer = "&".join([str(s) for s in singers])
            else:
                singer = str(singers)
            
            album = _get_val(song, "album", "")
            identifier = _get_val(song, "identifier", "")
            
            ext = os.path.splitext(save_path)[1].lstrip(".")
            if not ext:
                ext = _get_val(song, "ext", "mp3")
            
            parts = [song_name, singer]
            if album:
                parts.append(str(album))
            if identifier:
                parts.append(str(identifier))
            
            base_name = sanitize_filename("-".join(parts))
            file_name = f"{base_name}.{ext}"
            final_file_path = save_path
            final_file_name = file_name
            success_count += 1
            
            logger.info(f"[{task_id}] 文件下载成功: {final_file_path}")
        
        if success_count > 0:
            download_tasks[task_id]["status"] = "completed"
            download_tasks[task_id]["progress"] = 100.0
            download_tasks[task_id]["message"] = "下载完成"
            download_tasks[task_id]["file_path"] = final_file_path
            download_tasks[task_id]["file_name"] = final_file_name
            logger.info(f"[{task_id}] 下载任务完成，文件路径: {final_file_path}")
        else:
            logger.error(f"[{task_id}] 下载失败：未找到文件")
            download_tasks[task_id]["status"] = "failed"
            download_tasks[task_id]["message"] = "下载失败：未找到文件"
    
    except Exception as e:
        logger.error(f"[{task_id}] 下载任务异常: {e}")
        import traceback
        traceback.print_exc()
        download_tasks[task_id]["status"] = "failed"
        download_tasks[task_id]["message"] = f"下载失败: {str(e)}"


@app.get("/download/{task_id}")
async def get_download_status(task_id: str):
    logger.debug(f"[GET /download/{task_id}] 查询任务状态")
    if task_id not in download_tasks:
        logger.warning(f"任务不存在: {task_id}")
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return download_tasks[task_id]


@app.get("/download/{task_id}/file")
async def get_download_file(task_id: str):
    logger.info(f"[GET /download/{task_id}/file] 请求下载文件")
    
    if task_id not in download_tasks:
        logger.warning(f"任务不存在: {task_id}")
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task = download_tasks[task_id]
    if task["status"] != "completed":
        logger.warning(f"文件尚未下载完成: {task_id}, 状态: {task['status']}")
        raise HTTPException(status_code=400, detail="文件尚未下载完成")
    
    file_path = task.get("file_path")
    if not file_path or not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_name = task.get("file_name", "music.mp3")
    ext = os.path.splitext(file_name)[1].lower()
    file_size = os.path.getsize(file_path)
    
    media_types = {
        '.mp3': 'audio/mpeg',
        '.flac': 'audio/flac',
        '.m4a': 'audio/mp4',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.lrc': 'text/plain',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    safe_filename = quote(file_name, safe='')
    
    logger.info(f"[GET /download/{task_id}/file] 文件大小: {file_size} bytes, 文件名: {file_name}")
    
    def file_iterator():
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
        
        try:
            os.remove(file_path)
            logger.info(f"[{task_id}] 已删除服务器上的文件: {file_path}")
            
            lrc_path = os.path.splitext(file_path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                os.remove(lrc_path)
                logger.info(f"[{task_id}] 已删除歌词文件: {lrc_path}")
        except Exception as e:
            logger.error(f"[{task_id}] 删除文件失败: {e}")
    
    logger.info(f"[GET /download/{task_id}/file] 开始流式传输文件: {file_name}")
    return StreamingResponse(
        file_iterator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
            "Content-Length": str(file_size),
        }
    )


@app.get("/downloads")
async def list_downloads():
    files = []
    for f in TEMP_WORK_DIR.rglob("*"):
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
    file_path = TEMP_WORK_DIR / filename
    if file_path.exists():
        file_path.unlink()
        logger.info(f"[DELETE /downloads/{filename}] 文件已删除")
        return {"success": True, "message": "文件已删除"}
    else:
        logger.warning(f"[DELETE /downloads/{filename}] 文件不存在")
        raise HTTPException(status_code=404, detail="文件不存在")


if __name__ == "__main__":
    import uvicorn
    logger.info("="*50)
    logger.info("启动 FastAPI 服务...")
    logger.info("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
