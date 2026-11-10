import SwiftUI
import AppKit

@MainActor enum DirtyStateCheck {
    static func run() {
        let model = StudyModel()
        model.select(0, 0, confirm: false)
        let original = model.draft!.records
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 500), styleMask: [.titled], backing: .buffered, defer: false)
        func settle() { RunLoop.main.run(until: Date().addingTimeInterval(0.15)) }
        func assertClean(_ stage: String) {
            if model.dirty {
                print("失败：\(stage) 未输入任何文字，却被标记为有修改；记录内容相同：\(model.draft!.records == original)")
                exit(1)
            }
        }
        func views(_ view: NSView) -> [NSTextView] { (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(views) }
        for label in model.snapshot!.recordLabels {
            let host = NSHostingView(rootView: ContentView(model: model).editor(label, weekly: false))
            window.contentView = host; host.layoutSubtreeIfNeeded(); settle()
            assertClean("加载「\(label)」")
            for text in views(host) where text.isEditable {
                window.makeFirstResponder(text); settle()
                window.makeFirstResponder(nil); settle()
                assertClean("进入并离开「\(label)」")
            }
        }
        // AppKit 的结束编辑/同步通知可重复提交原值，必须视为无内容变化。
        let binding = ContentView(model: model).note("我的解释或答案要点")
        binding.wrappedValue = binding.wrappedValue
        assertClean("编辑绑定回传原值")
        let view = ContentView(model: model)
        let reviewLabel = model.snapshot!.reviewLabels[0]
        let review = view.note(reviewLabel, weekly: true)
        review.wrappedValue = review.wrappedValue
        view.field(\.status).wrappedValue = model.draft!.status
        model.changeHours(model.hours)
        assertClean("周复盘、状态和时长回传原值")
        let old = binding.wrappedValue
        binding.wrappedValue = old + "\n临时修改"
        precondition(model.dirty)
        binding.wrappedValue = old
        assertClean("撤回全部修改")
        let oldReview = review.wrappedValue
        review.wrappedValue = oldReview + "临时修改"
        precondition(model.dirty)
        review.wrappedValue = oldReview
        assertClean("还原周复盘")
        let oldHours = model.hours
        model.changeHours("无效时长")
        precondition(model.dirty)
        model.changeHours(oldHours)
        assertClean("还原时长")
        // 原生编辑器中的实际输入与撤销，而非仅测试绑定。
        let host = NSHostingView(rootView: ReflectionEditor(source: binding))
        window.contentView = host; host.layoutSubtreeIfNeeded(); settle()
        assertClean("加载原生原文编辑器")
        let editor = views(host).first!
        window.makeFirstResponder(editor)
        editor.insertText("实际编辑", replacementRange: NSRange(location: 0, length: 0))
        settle(); precondition(model.dirty)
        editor.doCommand(by: NSSelectorFromString("undo:"))
        settle(); assertClean("原生撤销")
        editor.doCommand(by: NSSelectorFromString("redo:"))
        settle(); precondition(model.dirty)
        editor.doCommand(by: NSSelectorFromString("undo:"))
        settle(); assertClean("重做后再次撤销")
        model.select(0, 1, confirm: false)
        settle()
        precondition(!model.dirty)
        model.select(0, 0, confirm: false)
        settle(); assertClean("切换学习日并返回")
        print("通过：加载、焦点、原值回传、真实编辑与撤销、周复盘、时长及切日的修改状态检查。")
        exit(0)
    }
}
