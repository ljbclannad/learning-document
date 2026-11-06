import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// 仅设置编辑区的显示属性，保存内容仍为原始纯文本。
struct ReflectionEditor: NSViewRepresentable {
    @Binding var source: String

    private static var attributes: [NSAttributedString.Key: Any] {
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 6
        paragraph.paragraphSpacing = 12
        return [.font: NSFont.systemFont(ofSize: 15),
                .foregroundColor: StudyTheme.text, .paragraphStyle: paragraph]
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        let text = NSTextView()
        text.isRichText = false
        text.allowsUndo = true
        text.isAutomaticQuoteSubstitutionEnabled = false
        text.isAutomaticDashSubstitutionEnabled = false
        text.isVerticallyResizable = true
        text.autoresizingMask = [.width]
        text.textContainer?.widthTracksTextView = true
        text.textContainerInset = NSSize(width: 20, height: 18)
        text.backgroundColor = StudyTheme.canvas
        text.minSize = .zero
        text.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        text.delegate = context.coordinator
        scroll.documentView = text
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let text = scroll.documentView as? NSTextView else { return }
        if text.string != source {
            text.textStorage?.setAttributedString(NSAttributedString(string: source, attributes: Self.attributes))
            text.undoManager?.removeAllActions()
        }
        text.typingAttributes = Self.attributes
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ReflectionEditor
        init(_ parent: ReflectionEditor) { self.parent = parent }
        func textDidChange(_ notification: Notification) {
            guard let text = notification.object as? NSTextView else { return }
            parent.source = text.string
        }
    }
}

/// 证据字段使用原文解析，不应用界面用语替换，也不执行代码。
enum EvidenceRenderer {
    enum Block: Equatable { case prose(String); case code(String, String) }

    static func blocks(_ source: String) -> [Block] {
        var result: [Block] = [], buffer: [String] = []
        var fence: Character?, length = 0, language = ""
        func flushProse() {
            if !buffer.isEmpty { result.append(.prose(buffer.joined(separator: "\n"))); buffer = [] }
        }
        for line in source.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n") {
            let leading = line.prefix(while: { $0 == " " }).count
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            let marker = trimmed.first
            let run = trimmed.prefix(while: { $0 == marker }).count
            if let active = fence {
                if leading <= 3, marker == active, run >= length, trimmed.dropFirst(run).isEmpty {
                    result.append(.code(language, buffer.joined(separator: "\n")))
                    buffer = []; fence = nil
                } else { buffer.append(line) }
            } else if leading <= 3, let marker, (marker == "`" || marker == "~"), run >= 3,
                      !(marker == "`" && trimmed.dropFirst(run).contains("`")) {
                flushProse(); fence = marker; length = run
                language = String(trimmed.dropFirst(run)).trimmingCharacters(in: .whitespaces)
            } else { buffer.append(line) }
        }
        if fence != nil { result.append(.code(language, buffer.joined(separator: "\n"))) }
        else { flushProse() }
        return result
    }

    static func attributed(_ source: String, root: String = "") -> NSAttributedString {
        let output = NSMutableAttributedString(string: "")
        let prose: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 14), .foregroundColor: StudyTheme.text]
        for block in blocks(source) {
            switch block {
            case .prose(let text):
                for line in text.components(separatedBy: "\n") {
                    if let attachment = ImageAttachments.attachment(line, root: root) {
                        output.append(attachment)
                        output.append(NSAttributedString(string: "\n", attributes: prose))
                    } else {
                        output.append(NSAttributedString(string: line + "\n", attributes: prose))
                    }
                }
            case .code(let language, let code):
                if !language.isEmpty {
                    output.append(NSAttributedString(string: language + "\n", attributes: [.font: NSFont.systemFont(ofSize: 11, weight: .semibold), .foregroundColor: StudyTheme.muted]))
                }
                let style = NSMutableParagraphStyle()
                style.lineSpacing = 3
                output.append(NSAttributedString(string: code + "\n", attributes: [
                    .font: NSFont.monospacedSystemFont(ofSize: 13, weight: .regular),
                    .foregroundColor: StudyTheme.text,
                    .backgroundColor: StudyTheme.subtle,
                    .paragraphStyle: style
                ]))
            }
        }
        return output
    }
}

struct EvidencePreview: NSViewRepresentable {
    var source: String
    var root: String = ""
    var markdown = false
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        let text = NSTextView()
        text.isEditable = false; text.isSelectable = true
        text.insertionPointColor = StudyTheme.text
        text.isVerticallyResizable = true
        text.autoresizingMask = [.width]
        text.textContainer?.widthTracksTextView = true
        text.textContainerInset = NSSize(width: 24, height: 20)
        text.linkTextAttributes = [.foregroundColor: StudyTheme.link]
        text.backgroundColor = StudyTheme.canvas
        text.minSize = .zero
        text.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        scroll.documentView = text
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let text = scroll.documentView as? NSTextView else { return }
        let rendered = markdown ? NotesMarkdown.render(source, root: root) : EvidenceRenderer.attributed(source, root: root)
        if !text.attributedString().isEqual(to: rendered) {
            text.textStorage?.setAttributedString(rendered)
        }
    }
}

struct EvidenceEditor: View {
    @Binding var source: String
    var root: String
    @State private var mode = "预览"
    @State private var imageError: String?

    private func insert(_ image: NSImage) {
        do {
            let link = try ImageAttachments.save(image, root: root)
            source += (source.isEmpty ? "" : "\n\n") + link + "\n"
            mode = "预览"
        } catch { imageError = error.localizedDescription }
    }

    private func chooseImage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image]
        panel.canChooseDirectories = false
        panel.prompt = "添加图片"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        guard let image = NSImage(contentsOf: url) else {
            imageError = "无法读取这张图片，请尝试 PNG 或 JPEG 格式。"; return
        }
        insert(image)
    }

    private func pasteImage() {
        guard let image = NSImage(pasteboard: .general) else {
            imageError = "剪贴板中没有可读取的图片。请先复制图片或将截图复制到剪贴板。"; return
        }
        insert(image)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Picker("显示方式", selection: $mode) {
                    Text("预览").tag("预览")
                    Text("源码").tag("源码")
                }.pickerStyle(.segmented).frame(width: 170)
                Spacer()
                Button("复制原文") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(source, forType: .string)
                }
            }
            HStack {
                Button("添加图片…", action: chooseImage)
                Button("粘贴图片", action: pasteImage)
                Spacer()
            }
            if mode == "预览" {
                if source.isEmpty { Text("在“源码”中粘贴记录；用三反引号包围代码，可在此预览。").font(.caption).foregroundStyle(Color(nsColor: StudyTheme.muted)) }
                EvidencePreview(source: source, root: root).frame(height: 300)
            } else {
                TextEditor(text: $source).font(.system(size: 13, design: .monospaced)).frame(height: 300)
            }
            Text("图片添加到记录末尾；⌘S 保存图片引用和笔记。代码保留缩进与换行。").font(.caption).foregroundStyle(Color(nsColor: StudyTheme.muted))
        }.padding(12).background(Color(nsColor: StudyTheme.canvas)).clipShape(RoundedRectangle(cornerRadius: 6))
        .alert("图片未能添加", isPresented: Binding(get: { imageError != nil }, set: { if !$0 { imageError = nil } })) {
            Button("好", role: .cancel) { imageError = nil }
        } message: { Text(imageError ?? "") }
    }
}
