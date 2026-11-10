import SwiftUI
import AppKit

@MainActor private struct ObservedReflectionEditor: View {
    @ObservedObject var model: StudyModel
    var body: some View {
        ReflectionEditor(source: ContentView(model: model).note("我的解释或答案要点"))
    }
}

@MainActor enum ReflectionSaveCheck {
    static func run() {
        do {
            let original = StudyModel()
            let root = URL(fileURLWithPath: original.root)
            let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("reflection-save-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
            for file in try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) where file.pathExtension == "md" {
                try FileManager.default.copyItem(at: file, to: temporary.appendingPathComponent(file.lastPathComponent))
            }
            let model = StudyModel(rootOverride: temporary.path)
            model.select(0, 0, confirm: false)
            let label = "我的解释或答案要点"
            let initial = model.draft!.records[label]!
            let host = NSHostingView(rootView: ObservedReflectionEditor(model: model))
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 500), styleMask: [.titled], backing: .buffered, defer: false)
            window.contentView = host
            func settle() { host.layoutSubtreeIfNeeded(); RunLoop.main.run(until: Date().addingTimeInterval(0.2)) }
            func views(_ view: NSView) -> [NSTextView] { (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(views) }
            func require(_ condition: Bool, _ message: String) {
                if !condition { print("失败：\(message)"); exit(1) }
            }
            settle()
            let editor = views(host).first!
            window.makeFirstResponder(editor)
            var expected = initial
            for text in ["\n\n## 保存验证", "\n中文输入与 `代码`", "\n1. 第一条", "\n2. 第二条"] {
                editor.insertText(text, replacementRange: NSRange(location: (expected as NSString).length, length: 0))
                expected += text
                settle()
                require(editor.string == expected, "输入后界面内容被刷新回旧值")
                require(model.draft!.records[label] == expected, "界面输入没有同步到待保存草稿，期望长度=\(expected.count)，实际长度=\(model.draft!.records[label]!.count)")
            }
            model.save(); settle()
            require(!model.error, "保存报错：\(model.message)")
            require(editor.string == expected, "保存后界面丢失输入")
            require(model.draft!.records[label] == expected, "保存后草稿丢失输入")
            let reopened = StudyModel(rootOverride: temporary.path)
            reopened.select(0, 0, confirm: false)
            require(reopened.draft!.records[label] == expected, "重新读取文件丢失输入")
            for suffix in ["\n保存后继续输入", "，再次输入并立即保存"] {
                editor.insertText(suffix, replacementRange: NSRange(location: (expected as NSString).length, length: 0))
                expected += suffix
                model.save(); settle()
                require(!model.error && editor.string == expected && model.draft!.records[label] == expected, "再次输入并立即保存时内容丢失")
                let check = StudyModel(rootOverride: temporary.path)
                check.select(0, 0, confirm: false)
                require(check.draft!.records[label] == expected, "连续保存后文件内容不一致")
            }
            print("通过：理解与思考持续输入、视图刷新、立即保存、连续保存与重新加载内容一致。")
            exit(0)
        } catch { print("失败：\(error)"); exit(1) }
    }
}
