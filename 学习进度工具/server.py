"""本地学习进度编辑器。Markdown 是唯一业务数据源，无第三方依赖。"""

import argparse
import hashlib
import json
import math
import re
import secrets
import shutil
import tempfile
import threading
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent
DEFAULT_ROOT = APP.parent / "00-索引与面试/AI应用后端三个月复习"
STATUSES = ["未开始", "学习中", "待复习", "已完成"]
LEVELS = ["未评估", "需提示", "可独立解释", "可动手验证", "可应对追问"]
RECORDS = ["实际完成内容", "我的解释或答案要点", "代码、图、实验或问答证据", "反馈与需要修正的理解", "未解决问题及核实方式", "未完成任务与顺延原因", "下次具体起点", "复测时间与结果"]
REVIEWS = ["实际完成学习日与总时长", "能独立解释的内容及证据", "仍需提示或实现未核实的内容", "本周错题与复测结果", "项目事实或能力边界的新发现", "下周保留、减少或顺延的任务及原因"]
DAY_RE = re.compile(r"^## 第 ([1-5]) 天 ([^\n]+)\n(.*?)(?=^## |\Z)", re.M | re.S)
META_RE = re.compile(r"实际日期：(.*?)。实际时长：(.*?)。状态：(.*?)。掌握程度：(.*?)。")


class Conflict(Exception):
    pass


def empty(value):
    return "" if value.strip() in ("待填写", "待记录。", "待记录", "尚未开始") else value


def field_pattern(label):
    return re.compile(r"^- " + re.escape(label) + r"：(.*(?:\n[ \t]+[^\n]*)*)", re.M)


def read_field(text, label):
    match = field_pattern(label).search(text)
    if not match:
        raise ValueError(f"找不到记录字段：{label}；请检查文档格式。")
    return empty(re.sub(r"\n  ", "\n", match.group(1)))


def write_field(text, label, value):
    rendered = value.replace("\n", "\n  ") if value else "待记录。"
    text, count = field_pattern(label).subn(lambda _: f"- {label}：{rendered}", text, count=1)
    if count != 1:
        raise ValueError(f"找不到记录字段：{label}")
    return text


def hours_value(value):
    if value == "待填写":
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*小时", value)
    if not match:
        raise ValueError(f"无法识别实际时长“{value}”，请改为数字加“小时”。")
    return float(match.group(1))


def parse_week(path, text):
    days = []
    for match in DAY_RE.finditer(text):
        meta = META_RE.search(match.group(3))
        if not meta:
            raise ValueError(f"{path.name} 第 {match.group(1)} 天的状态行格式已改变。")
        actual_date, hours, status, level = meta.groups()
        if status not in STATUSES or level not in LEVELS:
            raise ValueError(f"{path.name} 包含不支持的状态或掌握程度，请先核对文档。")
        tasks = re.findall(r"^- \[([ xX])\] (.+)$", match.group(3), re.M)
        days.append(dict(number=int(match.group(1)), title=match.group(2), date=empty(actual_date), hours=hours_value(hours), status=status, level=level,
                         tasks=[dict(done=t[0].lower() == "x", text=t[1]) for t in tasks],
                         records={label: read_field(match.group(3), label) for label in RECORDS}))
    if [d["number"] for d in days] != [1, 2, 3, 4, 5]:
        raise ValueError(f"{path.name} 必须包含第 1～5 天，且不能重复。")
    review = text.split("## 周复盘\n", 1)
    if len(review) != 2:
        raise ValueError(f"{path.name} 缺少周复盘。")
    refs = text.split("## 阅读入口\n", 1)[-1].split("## 本周五天安排", 1)[0]
    return dict(id=path.name, title=text.splitlines()[0].lstrip("# "), days=days,
                references=re.findall(r"\[\[([^\]]+)\]\]", refs),
                review={label: read_field(review[1], label) for label in REVIEWS})


def aggregate(days):
    done = sum(d["status"] == "已完成" for d in days)
    touched = any(d["status"] != "未开始" or d["date"] or d["hours"] is not None or any(t["done"] for t in d["tasks"]) or any(d["records"].values()) for d in days)
    status = "已完成" if done == len(days) else "待复习" if any(d["status"] == "待复习" for d in days) else "学习中" if touched else "未开始"
    return dict(status=status, completed=done, hours=sum(d["hours"] or 0 for d in days))


def replace_table_value(text, label, value):
    # 派生的表格单元格保持单行，原始多行记录保留在周文档。
    value = str(value).replace("|", "／").replace("\n", "；")
    pattern = re.compile(r"^\| " + re.escape(label) + r" \| .*? \|$", re.M)
    updated, count = pattern.subn(lambda _: f"| {label} | {value} |", text, count=1)
    if count != 1:
        raise ValueError(f"进度记录缺少汇总字段：{label}")
    return updated


class Store:
    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()

    def files(self):
        paths = sorted(self.root.glob("第[0-9][0-9]周-*.md"))
        if len(paths) != 12:
            raise ValueError("未找到完整的 12 份周计划，请检查文档目录。")
        return paths + [self.root / "学习进度记录.md"]

    def read(self):
        return {p: p.read_text(encoding="utf-8") for p in self.files()}

    @staticmethod
    def revision(docs):
        return hashlib.sha256(json.dumps({p.name: s for p, s in docs.items()}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def snapshot(self):
        docs = self.read()
        weeks = [parse_week(p, text) for p, text in docs.items() if p.name != "学习进度记录.md"]
        for week in weeks:
            week["summary"] = aggregate(week["days"])
        return dict(revision=self.revision(docs), weeks=weeks, summary=aggregate([d for w in weeks for d in w["days"]]),
                    statuses=STATUSES, levels=LEVELS, recordLabels=RECORDS, reviewLabels=REVIEWS, root=str(self.root))

    def save(self, data):
        with self.lock:
            docs = self.read()
            if data.get("revision") != self.revision(docs):
                raise Conflict("文档已被其他窗口、Obsidian 或会话修改。本次未保存，请先复制未保存记录，再重新加载。")
            targets = [p for p in docs if p.name == data.get("week") and p.name != "学习进度记录.md"]
            if len(targets) != 1:
                raise ValueError("无效的周计划。")
            target = targets[0]
            original = docs[target]
            week = parse_week(target, original)
            number = data.get("day")
            if type(number) is not int or not 1 <= number <= 5:
                raise ValueError("无效的学习日。")
            day = week["days"][number - 1]
            if data.get("status") not in STATUSES or data.get("level") not in LEVELS:
                raise ValueError("无效的状态或掌握程度。")
            actual_date = data.get("date", "")
            if not isinstance(actual_date, str):
                raise ValueError("日期格式不正确。")
            if actual_date:
                date.fromisoformat(actual_date)
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", actual_date):
                    raise ValueError("日期需使用 YYYY-MM-DD。")
            hours = data.get("hours")
            if hours is not None and (type(hours) not in (int, float) or not math.isfinite(hours) or not 0 <= hours <= 24):
                raise ValueError("每日实际时长应为 0～24 小时，也可留空。")
            checks = data.get("checks")
            if not isinstance(checks, list) or len(checks) != len(day["tasks"]) or any(type(x) is not bool for x in checks):
                raise ValueError("任务勾选数据不完整。")
            for key, labels in [("records", RECORDS), ("review", REVIEWS)]:
                if not isinstance(data.get(key), dict) or set(data[key]) != set(labels):
                    raise ValueError("学习记录字段不完整。")
                if any(not isinstance(v, str) or len(v) > 20000 or "\r" in v or "\x00" in v for v in data[key].values()):
                    raise ValueError("记录必须为文本，单项不超过 20000 字符。")
            match = list(DAY_RE.finditer(original))[number - 1]
            block = match.group(0)
            meta = f"实际日期：{actual_date or '待填写'}。实际时长：{format(hours, 'g') + ' 小时' if hours is not None else '待填写'}。状态：{data['status']}。掌握程度：{data['level']}。"
            block = META_RE.sub(lambda _: meta, block, count=1)
            checked = iter(checks)
            block = re.sub(r"^- \[[ xX]\] ", lambda _: "- [x] " if next(checked) else "- [ ] ", block, flags=re.M)
            for label in RECORDS:
                block = write_field(block, label, data["records"][label])
            changed = original[:match.start()] + block + original[match.end():]
            before_review, review = changed.split("## 周复盘\n", 1)
            for label in REVIEWS:
                review = write_field(review, label, data["review"][label])
            changed = before_review + "## 周复盘\n" + review
            updated_week = parse_week(target, changed)
            summary = aggregate(updated_week["days"])
            dates = sorted(d["date"] for d in updated_week["days"] if d["date"])
            span = f"{dates[0]} 至 {dates[-1]}" if dates else "待填写"
            changed, count = re.subn(r"^状态：.*?。实际日期范围：.*?。计划投入：", lambda _: f"状态：{summary['status']}。实际日期范围：{span}。计划投入：", changed, count=1, flags=re.M)
            if count != 1:
                raise ValueError("周计划头部格式已改变，未保存。")
            for d in updated_week["days"]:
                changed, count = re.subn(r"^\| 第 " + str(d["number"]) + r" 天 \| (.*?) \| .*? \|$", lambda m: f"| 第 {d['number']} 天 | {m.group(1)} | {d['status']} |", changed, count=1, flags=re.M)
                if count != 1:
                    raise ValueError("周计划每日汇总表格式已改变，未保存。")
            planned = dict(docs)
            planned[target] = changed
            weeks = [parse_week(p, s) for p, s in planned.items() if p.name != "学习进度记录.md"]
            all_days = [d for w in weeks for d in w["days"]]
            total = aggregate(all_days)
            tracker_path = self.root / "学习进度记录.md"
            tracker = docs[tracker_path]
            # 全局统计根据文档现状重算；接续位置优先使用本次保存的下次起点。
            current = next((w, d) for w in weeks for d in w["days"] if w["id"] == target.name and d["number"] == number)
            next_item = current if current[1]["status"] != "已完成" else next(((w, d) for w in weeks for d in w["days"] if d["status"] != "已完成"), current)
            nw, nd = next_item
            week_num = int(nw["id"][1:3])
            next_step = data["records"]["下次具体起点"] or ("全部学习日已完成，可安排综合复测。" if total["completed"] == 60 else f"第 {week_num:02d} 周第 {nd['number']} 天：{nd['title']}")
            values = {"总体状态": total["status"], "已完成学习日": f"{total['completed']} / 60", "累计实际时长": f"{total['hours']:g} 小时", "当前周次与学习日": f"第 {week_num:02d} 周，第 {nd['number']} 天", "当前主题": nd["title"], "上次完成内容": data["records"]["实际完成内容"] or "本次更新未填写实际完成内容", "下次具体起点": next_step, "当前掌握程度": nd["level"]}
            for key, value in values.items():
                tracker = replace_table_value(tracker, key, value)
            prefix = "00-索引与面试/AI应用后端三个月复习/"
            tracker = re.sub(r"^下次学习：.*$", lambda _: f"下次学习：[[{prefix}{Path(nw['id']).stem}]]。", tracker, count=1, flags=re.M)
            known_dates = sorted(d["date"] for d in all_days if d["date"])
            tracker = re.sub(r"最近实际学习日期：.*?。", lambda _: f"最近实际学习日期：{known_dates[-1] if known_dates else '尚未开始'}。", tracker, count=1)
            for w in weeks:
                sm = aggregate(w["days"])
                pat = re.compile(r"^\| (\[\[[^\n]*?/" + re.escape(Path(w["id"]).stem) + r"\]\]) \| .*? \| .*? \| .*? \| (.*?) \|$", re.M)
                tracker, count = pat.subn(lambda m: f"| {m.group(1)} | {sm['status']} | {sm['completed']} / 5 | {sm['hours']:g} | {m.group(2)} |", tracker, count=1)
                if count != 1:
                    raise ValueError("进度记录中的周汇总表格式已改变，未保存。")
            # 保留会话日志、跨日疑点、调整记录等手工维护段落，避免推断或重复生成。
            writes = {target: changed, tracker_path: tracker}
            backup = self.root / ".学习进度备份" / (datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4))
            backup.mkdir(parents=True, exist_ok=False)
            for p in writes:
                (backup / p.name).write_text(docs[p], encoding="utf-8")
            if self.revision(self.read()) != self.revision(docs):
                raise Conflict("保存前检测到文档变化，本次未保存，请重新加载。")
            committed = []
            try:
                for p, text in writes.items():
                    self.atomic_write(p, text)
                    committed.append(p)
            except OSError:
                for p in committed:
                    self.atomic_write(p, docs[p])
                raise
            return dict(backup=str(backup), **self.snapshot())

    @staticmethod
    def atomic_write(path, text):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".学习进度暂存-", delete=False) as f:
            f.write(text)
            temp = Path(f.name)
        shutil.copymode(path, temp)
        temp.replace(path)


def make_server(root, port):
    store = Store(root)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def send(self, status, body, mime="application/json; charset=utf-8"):
            raw = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "仅支持本机地址访问。"})
            try:
                if self.path == "/api/state":
                    return self.send(200, dict(token=token, **store.snapshot()))
                assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
                if self.path in assets:
                    name, mime = assets[self.path]
                    return self.send(200, (APP / name).read_bytes(), mime)
                self.send(404, {"error": "页面不存在。"})
            except (ValueError, OSError) as exc:
                self.send(400, {"error": str(exc)})

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.valid_host() or self.headers.get("X-Study-Token") != token or (origin and origin != expected_origin):
                return self.send(403, {"error": "请求来源校验失败，请在本机页面操作。"})
            if self.path != "/api/save":
                return self.send(404, {"error": "接口不存在。"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 500000:
                    raise ValueError("保存内容过大或为空。")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("请求格式不正确。")
                self.send(200, store.save(data))
            except Conflict as exc:
                self.send(409, {"error": str(exc)})
            except (ValueError, TypeError, OSError) as exc:
                self.send(400, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地学习进度工具")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = parser.parse_args()
    Store(args.root).snapshot()
    server = make_server(args.root, args.port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"学习进度工具已启动：{url}\n关闭此终端或按 Ctrl+C 停止。", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
