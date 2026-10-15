"""统一日志配置。"""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # 降噪：第三方库统一抬到 WARNING
    for noisy in (
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
        "openai",
        "botocore",
        "urllib3",
        "asyncio",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
