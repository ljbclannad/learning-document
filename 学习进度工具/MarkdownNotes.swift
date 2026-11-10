import SwiftUI
import AppKit

/// 阅读排版与原文分离，所有转换只作用于预览。
enum NotesMarkdown {
    static func inline(_ source: String, size: CGFloat, bold: Bool = false) -> NSAttributedString {
        let result = NSMutableAttributedString(string: "")
        guard let parsed = try? AttributedString(markdown: source, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) else {
            return NSAttributedString(string: source, attributes: [.font: NSFont.systemFont(ofSize: size)])
        }
        for run in parsed.runs {
            let intent = run.inlinePresentationIntent ?? []
            let weight: NSFont.Weight = bold || intent.contains(.stronglyEmphasized) ? .semibold : .regular
            var font = intent.contains(.code) ? NSFont.monospacedSystemFont(ofSize: size - 1, weight: weight) : NSFont.systemFont(ofSize: size, weight: weight)
            if intent.contains(.emphasized) { font = NSFontManager.shared.convert(font, toHaveTrait: .italicFontMask) }
            var attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: StudyTheme.text]
            if intent.contains(.code) { attributes[.backgroundColor] = StudyTheme.subtle }
            if intent.contains(.strikethrough) { attributes[.strikethroughStyle] = NSUnderlineStyle.single.rawValue }
            if let link = run.link { attributes[.link] = link }
            result.append(NSAttributedString(string: String(parsed.characters[run.range]), attributes: attributes))
        }
        return result
    }

    static func render(_ source: String, root: String) -> NSAttributedString {
        let result = NSMutableAttributedString(string: "")
        let heading = try! NSRegularExpression(pattern: #"^ {0,3}(#{1,6})\s+(.+?)(?:\s+#+)?$"#)
        let list = try! NSRegularExpression(pattern: #"^([ \t]*)([-+*]|\d+[.)]|[a-zA-Z][.)])[ \t]+(.*)$"#)
        for block in EvidenceRenderer.blocks(source) {
            switch block {
            case .code(let language, let code):
                if !language.isEmpty { result.append(inline(language + "\n", size: 11)) }
                let style = NSMutableParagraphStyle()
                style.lineSpacing = 4; style.paragraphSpacing = 14
                result.append(NSAttributedString(string: code + "\n", attributes: [
                    .font: NSFont.monospacedSystemFont(ofSize: 14, weight: .regular),
                    .foregroundColor: StudyTheme.text, .backgroundColor: StudyTheme.subtle,
                    .paragraphStyle: style]))
            case .prose(let prose):
                for line in prose.components(separatedBy: "\n") {
                    let range = NSRange(line.startIndex..., in: line)
                    let style = NSMutableParagraphStyle()
                    style.lineSpacing = 6; style.paragraphSpacing = 10
                    let paragraph: NSMutableAttributedString
                    if line.trimmingCharacters(in: .whitespaces).isEmpty {
                        // Markdown 段落分隔只留小间距，避免原文空行叠加成大块留白。
                        paragraph = NSMutableAttributedString(string: "", attributes: [.font: NSFont.systemFont(ofSize: 4)])
                        style.lineSpacing = 0; style.paragraphSpacing = 4
                    } else if let image = ImageAttachments.attachment(line, root: root) {
                        paragraph = NSMutableAttributedString(attributedString: image)
                    } else if let match = heading.firstMatch(in: line, range: range) {
                        let level = (line as NSString).substring(with: match.range(at: 1)).count
                        let title = (line as NSString).substring(with: match.range(at: 2))
                        paragraph = NSMutableAttributedString(attributedString: inline(title, size: CGFloat([26, 22, 18, 16, 15, 14][level - 1]), bold: true))
                        style.paragraphSpacingBefore = 10; style.paragraphSpacing = 12
                    } else if let match = list.firstMatch(in: line, range: range) {
                        let indent = (line as NSString).substring(with: match.range(at: 1)).replacingOccurrences(of: "\t", with: "    ").count
                        let marker = (line as NSString).substring(with: match.range(at: 2))
                        var body = (line as NSString).substring(with: match.range(at: 3))
                        var prefix = ["-", "+", "*"].contains(marker) ? "•" : marker
                        if body.hasPrefix("[ ] ") { prefix = "☐"; body = String(body.dropFirst(4)) }
                        else if body.hasPrefix("[x] ") || body.hasPrefix("[X] ") { prefix = "☑"; body = String(body.dropFirst(4)) }
                        paragraph = NSMutableAttributedString(attributedString: inline(prefix + "\t" + body, size: 14))
                        style.firstLineHeadIndent = CGFloat(indent) * 7
                        style.headIndent = style.firstLineHeadIndent + 32
                        style.tabStops = [NSTextTab(textAlignment: .left, location: style.headIndent)]
                        style.paragraphSpacing = 8
                    } else {
                        paragraph = NSMutableAttributedString(attributedString: inline(line, size: 14))
                    }
                    paragraph.append(NSAttributedString(string: "\n", attributes: [.font: NSFont.systemFont(ofSize: line.trimmingCharacters(in: .whitespaces).isEmpty ? 4 : 14)]))
                    paragraph.addAttribute(.paragraphStyle, value: style, range: NSRange(location: 0, length: paragraph.length))
                    result.append(paragraph)
                }
            }
        }
        return result
    }

    @MainActor static func check() {
        let nested = render("1. Spring主要管理的内容为：\n\ta. 对象：创建了哪些对象\n    b. 依赖关系：对象之间如何建立依赖\n        A) 更深一层\n2. 下一项", root: "")
        for (text, indent) in [("a.\t对象", CGFloat(28)), ("b.\t依赖关系", CGFloat(28)), ("A)\t更深一层", CGFloat(56))] {
            let range = (nested.string as NSString).range(of: text)
            guard range.location != NSNotFound else {
                print("失败：字母子列表未识别：\(text)"); exit(1)
            }
            let style = nested.attribute(.paragraphStyle, at: range.location, effectiveRange: nil) as! NSParagraphStyle
            precondition(style.firstLineHeadIndent == indent && style.headIndent == indent + 32)
            precondition(style.lineSpacing == 6 && style.paragraphSpacing == 8)
            let font = nested.attribute(.font, at: range.location, effectiveRange: nil) as! NSFont
            precondition(font.pointSize == 14)
        }
        let fenced = render("```text\n\ta. 保持代码原文\n```", root: "")
        precondition(fenced.string.contains("\ta. 保持代码原文"))

        let source = "## 原理\n\n1. 调用 `interrupt()`\n   - **协作取消**\n- [x] 已验证\n\n```java\n    run();\n```"
        let host = NSHostingView(rootView: ReflectionNotesEditor(source: .constant(source), root: ""))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 680, height: 500), styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        func views(_ view: NSView) -> [NSTextView] {
            (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(views)
        }
        let preview = views(host).first!
        let rendered = preview.attributedString()
        precondition(!preview.isEditable)
        precondition(!rendered.string.contains("##") && !rendered.string.contains("`") && !rendered.string.contains("**"))
        precondition(rendered.string.contains("1.\t调用 interrupt()") && rendered.string.contains("•\t协作取消") && rendered.string.contains("☑\t已验证"))
        for code in ["interrupt()", "    run();"] {
            let range = (rendered.string as NSString).range(of: code)
            precondition(range.location != NSNotFound)
            let font = rendered.attribute(.font, at: range.location, effectiveRange: nil) as! NSFont
            precondition(font.fontDescriptor.symbolicTraits.contains(.monoSpace))
        }
        let titleFont = rendered.attribute(.font, at: 0, effectiveRange: nil) as! NSFont
        precondition(titleFont.pointSize > 15)
        let escaped = render(#"\*原文\* 与 ``a`b``"#, root: "")
        precondition(escaped.string.contains("*原文* 与 a`b"))
        print("通过：实际理解与思考预览显示标题、嵌套列表、任务项、行内代码与围栏代码。")
        exit(0)
    }
}

struct ReflectionNotesEditor: View {
    @Binding var source: String
    var root: String
    @State private var editing = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("理解与思考显示方式", selection: $editing) {
                Text("预览").tag(false)
                Text("编辑").tag(true)
            }.pickerStyle(.segmented).labelsHidden().frame(width: 170)
            Group {
                if editing { ReflectionEditor(source: $source) }
                else { EvidencePreview(source: source, root: root, markdown: true) }
            }.frame(height: 420)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: StudyTheme.border)))
            Text("编辑 Markdown 原文，切换到预览查看排版；⌘S 保存到文档。").font(.caption).foregroundStyle(Color(nsColor: StudyTheme.muted))
        }.frame(maxWidth: 860).frame(maxWidth: .infinity)
    }
}
