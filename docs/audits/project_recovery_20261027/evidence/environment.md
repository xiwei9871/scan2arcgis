# 审计执行环境

- 日期：2026-10-27（Asia/Shanghai）
- 系统：Ubuntu 22.04 隔离虚拟机，4 核 CPU，约 3.9 GB 内存，aarch64
- Python 3.10.12（仓库 `.venv/` 为 Windows 版 Python 3.10 虚拟环境，Dockerfile 声明 Python 3.12）
- 安装：numpy 1.24.3、opencv-contrib-python-headless 4.10.0.84、shapely 2.0.2、fastapi 0.104.1、pydantic 2.5.0、pytest 7.4.3、pytest-asyncio 0.21.1、httpx 0.25.2、scikit-learn、pyproj、matplotlib、pytest-timeout
- 与 requirements.txt 的偏差：rasterio 1.4.4 / geopandas 1.1.4（固定版本在该平台装不上）；未安装 GDAL Python 绑定、PaddleOCR、PaddlePaddle（因此依赖它们的路径未被实际执行）
- 为在 Linux 上收集测试，加了 `msvcrt` 空实现 shim（仅审计用，不入库代码）
- 仓库获取：`git clone --mirror`，171 个提交，2 个分支（master、dev），无标签
