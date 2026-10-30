"""编译并运行 Java 17 教学实验，另行确认非法泛型用法被编译器拒绝。"""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
INVALID_SOURCES = {
    "Invariant": """import java.util.List;
class Invariant { List<Number> convert(List<Integer> values) { return values; } }
""",
    "ErasureClash": """import java.util.List;
class ErasureClash { void handle(List<String> values) {} void handle(List<Integer> values) {} }
""",
    "GenericArray": """import java.util.List;
class GenericArray { Object values = new List<String>[1]; }
""",
    "UnsafeWrite": """import java.util.List;
class UnsafeWrite { void add(List<? extends Number> values) { values.add(1); } }
""",
}


def main():
    subprocess.run(["javac", "-version"], check=True)
    subprocess.run(["java", "-version"], check=True)
    # 只清理本脚本创建的临时编译产物，不写入或清理知识库文件。
    with tempfile.TemporaryDirectory(prefix="java-basics-lab-") as directory:
        output = Path(directory)
        subprocess.run([
            "javac", "--release", "17", "-encoding", "UTF-8",
            "-Xlint:all", "-Werror", "-d", directory, str(ROOT / "JavaBasicsLab.java"),
        ], check=True)
        subprocess.run(["java", "-cp", directory, "JavaBasicsLab"], check=True)
        for name, source in INVALID_SOURCES.items():
            path = output / (name + ".java")
            path.write_text(source, encoding="utf-8")
            result = subprocess.run([
                "javac", "-J-Duser.language=en", "--release", "17", "-encoding", "UTF-8",
                "-d", directory, str(path),
            ], capture_output=True, text=True)
            if result.returncode == 0 or "error:" not in result.stderr:
                raise AssertionError(f"未按预期出现编译错误：{name}\n{result.stderr}")
            print(f"编译拒绝验证通过：{name}", flush=True)
    print("全部验证完成；4 个编译失败用例均被拒绝。", flush=True)


if __name__ == "__main__":
    main()
