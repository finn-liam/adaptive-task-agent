# uv 与 Python 项目环境管理

uv 是 Python 的项目管理工具，负责三件事：装包（uv add）、运行（uv run）、锁版本（uv.lock）。

pyproject.toml 是项目的"身份证"：记录项目名、要求的 Python 版本、依赖清单。
它是行业标准格式，取代了旧的 requirements.txt + setup.py 双文件时代。

虚拟环境 .venv 是每个项目独立的依赖文件夹，互不污染。删掉也能用 uv sync 一条命令重建，
所以 .venv 永远不进 Git、不上传 GitHub。

依赖分两类：普通依赖（程序运行必需，如 langgraph、pydantic）和开发工具（uv add --dev，
如 pytest、ruff）——用户运行你的程序不需要测试工具，所以分开记录。

uv add 一条命令做三件事：写进 pyproject.toml、下载安装到 .venv、把精确版本锁进 uv.lock。
uv.lock 必须提交，别人 uv sync 就能还原出一模一样的环境。

Windows 的坑：裸敲 python 命令可能指向老版本（比如 3.7），一律用 uv run python 保证用项目环境。
ruff 是代码检查器：I001 管导入排序（标准库、第三方库、本项目模块三段式），
F401 管未使用的导入，--fix 能自动修机械问题，# noqa: 规则号 用于豁免刻意的设计。
