"""read_file 的行为测试：正常读取 + 三种拒绝"""

import pytest

from app.tools.read_file import read_file


def test_reads_file_inside_root():
    content = read_file("pyproject.toml")
    assert "[project]" in content


def test_rejects_path_escape():
    with pytest.raises(ValueError):
        read_file("../../plan.md")


def test_rejects_missing_file():
    with pytest.raises(FileNotFoundError):
        read_file("不存在.txt")


def test_rejects_absolute_path_outside_root():
    with pytest.raises(ValueError):
        read_file("C:/Windows/win.ini")     # 绝对路径越界同样要拦