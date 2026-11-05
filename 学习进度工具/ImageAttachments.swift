import AppKit

/// 图片与周计划位于同一目录树，Markdown 使用可迁移的相对路径。
enum ImageAttachments {
    static func save(_ image: NSImage, root: String) throws -> String {
        guard let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw failure("无法读取这张图片，请使用 PNG、JPEG 等常见图片格式。")
        }
        let directory = URL(fileURLWithPath: root).appendingPathComponent("附件/实践笔记", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let name = "图片-\(UUID().uuidString).png"
        try png.write(to: directory.appendingPathComponent(name), options: .atomic)
        return "![实践图片](附件/实践笔记/\(name))"
    }

    static func attachment(_ line: String, root: String) -> NSAttributedString? {
        let pattern = #"^!\[[^\]]*\]\(([^\n]+)\)$"#
        let value = line.trimmingCharacters(in: .whitespaces)
        guard let expression = try? NSRegularExpression(pattern: pattern),
              let match = expression.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)),
              let range = Range(match.range(at: 1), in: value) else { return nil }
        let raw = String(value[range]).trimmingCharacters(in: CharacterSet(charactersIn: "<>"))
        let path = raw.removingPercentEncoding ?? raw
        let base = URL(fileURLWithPath: root).resolvingSymlinksInPath()
        let file = base.appendingPathComponent(path).standardizedFileURL.resolvingSymlinksInPath()
        guard !root.isEmpty, !path.hasPrefix("/"), !path.contains("://"),
              file.path.hasPrefix(base.path + "/"), let image = NSImage(contentsOf: file),
              image.size.width > 0, image.size.height > 0 else { return nil }
        let scale = min(1, 420 / image.size.width, 600 / image.size.height)
        image.size = NSSize(width: image.size.width * scale, height: image.size.height * scale)
        let attachment = NSTextAttachment()
        attachment.attachmentCell = NSTextAttachmentCell(imageCell: image)
        return NSAttributedString(attachment: attachment)
    }

    static func failure(_ message: String) -> NSError {
        NSError(domain: "实践图片", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
    }

    // 只在临时目录验证，不改写真实学习记录，也不使用系统剪贴板。
    static func check() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("study-image-check-\(UUID().uuidString)")
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 20, pixelsHigh: 10, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        let image = NSImage(size: NSSize(width: 20, height: 10))
        image.addRepresentation(bitmap)
        let first = try save(image, root: directory.path)
        let second = try save(image, root: directory.path)
        precondition(first != second)
        precondition(attachment(first, root: directory.path)?.attribute(.attachment, at: 0, effectiveRange: nil) is NSTextAttachment)
        precondition(attachment("![图片](../outside.png)", root: directory.path) == nil)
        precondition(attachment("![图片](https://example.com/a.png)", root: directory.path) == nil)
        precondition(attachment("![图片](不存在.png)", root: directory.path) == nil)
        let rendered = EvidenceRenderer.attributed("说明\n" + first + "\n```text\n" + first + "\n```", root: directory.path)
        precondition(rendered.string.contains(first)) // 围栏内的图片语法仍显示为代码。
        var count = 0
        rendered.enumerateAttribute(.attachment, in: NSRange(location: 0, length: rendered.length)) { value, _, _ in
            if value is NSTextAttachment { count += 1 }
        }
        precondition(count == 1)
        print("通过：图片保存、独立命名、相对路径预览和代码围栏兼容检查。")
    }
}
