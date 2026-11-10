import AppKit
import SwiftUI

/// 仅识别围栏外的 Markdown 表格；代码块由上层解析器隔离。
enum MarkdownTable {
    static func cells(_ line: String) -> [String]? {
        let text = line.trimmingCharacters(in: .whitespaces)
        guard text.contains("|") else { return nil }
        var cells: [String] = [], buffer = "", escaped = false
        for character in text {
            if escaped {
                buffer.append("\\"); buffer.append(character); escaped = false
            } else if character == "\\" { escaped = true }
            else if character == "|" { cells.append(buffer); buffer = "" }
            else { buffer.append(character) }
        }
        if escaped { buffer.append("\\") }
        cells.append(buffer)
        if text.hasPrefix("|") { cells.removeFirst() }
        if text.hasSuffix("|"), cells.last == "" { cells.removeLast() }
        return cells.map { $0.trimmingCharacters(in: .whitespaces) }
    }

    static func render(_ source: String, lineRenderer: (String) -> NSAttributedString) -> NSAttributedString {
        let lines = source.components(separatedBy: "\n")
        let output = NSMutableAttributedString(string: "")
        var index = 0
        while index < lines.count {
            if index + 1 < lines.count, let headers = cells(lines[index]),
               let separators = cells(lines[index + 1]), !headers.isEmpty,
               headers.count == separators.count,
               separators.allSatisfy({ $0.range(of: #"^:?-{3,}:?$"#, options: .regularExpression) != nil }) {
                var rows = [headers]
                index += 2
                while index < lines.count, let row = cells(lines[index]), row.count == headers.count {
                    rows.append(row); index += 1
                }
                output.append(table(rows, separators: separators))
                output.append(NSAttributedString(string: "\n"))
            } else {
                output.append(lineRenderer(lines[index])); index += 1
            }
        }
        return output
    }

    static func table(_ rows: [[String]], separators: [String]) -> NSAttributedString {
        let table = NSTextTable()
        table.numberOfColumns = separators.count
        table.layoutAlgorithm = .fixedLayoutAlgorithm
        table.collapsesBorders = true
        table.setValue(100, type: .percentageValueType, for: .width)
        let result = NSMutableAttributedString(string: "")
        for (rowIndex, row) in rows.enumerated() {
            for (column, value) in row.enumerated() {
                let cell = NSTextTableBlock(table: table, startingRow: rowIndex, rowSpan: 1, startingColumn: column, columnSpan: 1)
                cell.setValue(100 / CGFloat(separators.count), type: .percentageValueType, for: .width)
                cell.setWidth(8, type: .absoluteValueType, for: .padding)
                cell.setWidth(0.5, type: .absoluteValueType, for: .border)
                cell.setBorderColor(StudyTheme.border)
                if rowIndex == 0 { cell.backgroundColor = StudyTheme.subtle }
                let style = NSMutableParagraphStyle()
                style.textBlocks = [cell]
                style.lineSpacing = 4
                if separators[column].hasSuffix(":") {
                    style.alignment = separators[column].hasPrefix(":") ? .center : .right
                }
                let content = NSMutableAttributedString(attributedString: NotesMarkdown.inline(value, size: 14, bold: rowIndex == 0))
                content.append(NSAttributedString(string: "\n", attributes: [.font: NSFont.systemFont(ofSize: 14), .foregroundColor: StudyTheme.text]))
                content.addAttribute(.paragraphStyle, value: style, range: NSRange(location: 0, length: content.length))
                result.append(content)
            }
        }
        return result
    }

    @MainActor static func check() {
        let source = "表格示例\n\n| 属性 | 说明 |\n| :--- | ---: |\n| `state` | **同步状态** |\n| 空值 | |\n| 转义 | a\\|b |\n\n```text\n| 保留 | 代码 |\n| --- | --- |\n```"
        let host = NSHostingView(rootView: EvidenceEditor(source: .constant(source), root: ""))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 680, height: 440), styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        func views(_ view: NSView) -> [NSTextView] { (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(views) }
        let preview = views(host).first!
        let rendered = preview.attributedString()
        let range = (rendered.string as NSString).range(of: "state")
        let style = rendered.attribute(.paragraphStyle, at: range.location, effectiveRange: nil) as! NSParagraphStyle
        precondition(style.textBlocks.first is NSTextTableBlock)
        let font = rendered.attribute(.font, at: range.location, effectiveRange: nil) as! NSFont
        precondition(font.fontDescriptor.symbolicTraits.contains(.monoSpace))
        precondition(rendered.string.contains("a|b") && rendered.string.contains("| 保留 | 代码 |"))
        precondition(cells("| a | |") == ["a", ""])
        precondition(cells("a | b") == ["a", "b"])
        let plain = EvidenceRenderer.attributed("| A | B |\n| 不是 | 分隔行 |")
        precondition(plain.string.contains("| A | B |"))
        let png = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
        host.cacheDisplay(in: host.bounds, to: png)
        let path = FileManager.default.temporaryDirectory.appendingPathComponent("study-table-preview.png")
        try! png.representation(using: .png, properties: [:])!.write(to: path)
        print("通过：原生表格、空单元格、转义竖线、行内代码及围栏隔离。预览：\(path.path)")
        exit(0)
    }
}
