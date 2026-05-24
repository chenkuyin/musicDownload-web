# 🎵 音乐下载器 Web版

基于 FastAPI 和 musicdl 的多源音乐搜索与下载服务。

## 功能特点

- 🔍 支持多个音乐源搜索（网易云、QQ音乐、酷狗、酷我、咪咕）
- ⬇️ 一键下载音乐到本地
- 🗑️ 下载后自动删除服务器文件，保护隐私
- 📱 响应式设计，支持移动端访问
- 🚀 支持 Docker 部署和 Fly.io 云部署

## 快速开始

### 本地运行

1. 安装依赖：
```bash
cd backend
pip install -r requirements.txt
```

2. 启动服务：
```bash
python main.py
```

3. 访问 http://localhost:8000

### Docker 部署

```bash
docker build -t music-download-web .
docker run -p 8000:8000 music-download-web
```

### Fly.io 部署

1. 安装 flyctl：
```bash
curl -L https://fly.io/install.sh | sh
```

2. 登录并部署：
```bash
fly auth login
fly launch
fly deploy
```

## 项目结构

```
musicDownload-web/
├── backend/
│   ├── main.py          # FastAPI 主程序
│   └── requirements.txt  # Python 依赖
├── static/
│   ├── style.css        # 样式文件
│   └── app.js          # 前端逻辑
├── index.html           # 主页面
├── Dockerfile          # Docker 配置
├── fly.toml            # Fly.io 配置
└── README.md
```

## 使用说明

1. 选择要搜索的音乐源
2. 输入歌曲名或关键词
3. 点击搜索按钮
4. 选择要下载的歌曲
5. 点击下载按钮
6. 文件会自动下载到本地，服务器上的文件会被删除

## 技术栈

- **后端**: FastAPI + Python
- **前端**: Vanilla JavaScript + CSS3
- **音乐源**: musicdl
- **部署**: Docker + Fly.io

## 注意事项

- 请勿将本工具用于商业用途
- 下载的音乐仅供个人学习使用
- 部分音乐可能因版权原因无法下载
