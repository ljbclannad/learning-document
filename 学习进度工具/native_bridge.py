"""原生应用通过标准输入输出调用文档存储，不启动 HTTP 服务。"""
import json
import sys
from pathlib import Path
from server import Store

try:
    request = json.load(sys.stdin)
    store = Store(Path(request["root"]))
    result = store.save(request["data"]) if request["action"] == "save" else store.snapshot()
    print(json.dumps(result, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"error": str(exc)}, ensure_ascii=False))
    sys.exit(1)
