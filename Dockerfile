# --- 基础镜像 ---
# 选择一个官方的、轻量的 Python 镜像作为基础。
# python:3.9-slim 是一个不错的选择，因为它体积小，安全性高。
FROM python:3.11.2

# --- 设置工作目录 ---
# 在容器内创建一个 /app 目录，并将它设置为后续命令的执行目录。
# 这样做可以保持容器文件系统的整洁。
WORKDIR /app

# --- 安装依赖 ---
# 首先只复制 requirements.txt 文件，并安装依赖。
# Docker 会缓存这一层，如果 requirements.txt 没有变化，下次构建时会直接使用缓存，加快构建速度。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- 复制项目文件 ---
# 将项目中的所有文件复制到容器的 /app 目录中。
COPY . .

# --- 暴露端口 ---
# 声明容器将要监听的端口。这主要是一个文档性质的声明，
# 真正的端口映射是在 docker run 或 docker-compose.yml 中完成的。
EXPOSE 8443

# --- 启动命令 ---
# 定义容器启动时要执行的命令。
# 这里我们使用 python -u main.py，-u 参数可以确保 Python 的输出（比如 print 语句）
# 不会被缓冲，直接显示在 Docker 日志中，方便调试。
CMD ["python", "-u", "main.py"]
