import subprocess
from abc import ABC, abstractmethod

class Process(ABC):
    @abstractmethod
    def execute(self, *args, **kwargs) -> None:
        pass

class SpiderProcess(Process):
    def execute(self, spider_name: str, dir: str, args: str) -> None:
        import sys
        process = subprocess.Popen(
            [sys.executable, "-m", "scrapy", "crawl", spider_name] + args.split(),
            cwd=dir,
        )
        process.wait()
