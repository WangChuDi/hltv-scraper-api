import subprocess
from abc import ABC, abstractmethod

class Process(ABC):
    @abstractmethod
    def execute(self, *args, **kwargs) -> None:
        pass

class SpiderProcess(Process):
    def _build_command(self, spider_name: str, args: str) -> list[str]:
        import sys

        return [sys.executable, "-m", "scrapy", "crawl", spider_name] + args.split()

    def spawn(self, spider_name: str, dir: str, args: str) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            self._build_command(spider_name, args),
            cwd=dir,
            start_new_session=True,
        )

    def execute(self, spider_name: str, dir: str, args: str) -> None:
        process = self.spawn(spider_name, dir, args)
        process.wait()
