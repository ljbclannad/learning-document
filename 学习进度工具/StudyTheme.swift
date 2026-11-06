import SwiftUI
import AppKit

/// GitHub 风格的中性表面、细边框和语义色，随系统外观解析。
enum StudyTheme {
    static func color(_ light: UInt32, _ dark: UInt32) -> NSColor {
        NSColor(name: nil) { appearance in
            let value = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat((value >> 16) & 255) / 255,
                           green: CGFloat((value >> 8) & 255) / 255,
                           blue: CGFloat(value & 255) / 255, alpha: 1)
        }
    }
    static let canvas = color(0xffffff, 0x0d1117)
    static let subtle = color(0xf6f8fa, 0x161b22)
    static let border = color(0xd1d9e0, 0x3d444d)
    static let text = color(0x1f2328, 0xf0f6fc)
    static let muted = color(0x59636e, 0x9198a1)
    static let link = color(0x0969da, 0x4493f8)
    static let selection = color(0xddf4ff, 0x172f48)
    static let success = color(0x1f883d, 0x238636)
}

struct StudyPanelStyle: GroupBoxStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            configuration.label.font(.system(size: 13, weight: .semibold))
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16).padding(.vertical, 10)
                .background(Color(nsColor: StudyTheme.subtle))
            configuration.content.frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Color(nsColor: StudyTheme.canvas))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: StudyTheme.border), lineWidth: 1))
    }
}

@MainActor enum ThemePreviewCheck {
    static func run() {
        let model = StudyModel()
        guard model.snapshot != nil else { print(model.message); exit(1) }
        // 预览只修改内存草稿，不调用保存。
        model.draft?.records["我的解释或答案要点"] = "# 学习笔记\n\n## 线程池的执行流程\n\n使用 **有界队列** 控制积压，通过 `execute()` 提交任务。\n\n1. 判断核心线程数\n2. 尝试入队\n   - 队列已满时触发扩容或拒绝\n- [x] 已完成实验\n\n```java\nexecutor.execute(() -> {\n    process();\n});\n```\n\n[阅读笔记](https://example.com)"
        do {
            for dark in [false, true] {
                let appearance = NSAppearance(named: dark ? .darkAqua : .aqua)!
                let scheme: ColorScheme = dark ? .dark : .light
                let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1150, height: 1000), styleMask: [.titled], backing: .buffered, defer: false)
                window.appearance = appearance
                let host = NSHostingView(rootView: ContentView(model: model).environment(\.colorScheme, scheme).environment(\.controlActiveState, .key).frame(width: 1150, height: 1000))
                window.contentView = host
                host.layoutSubtreeIfNeeded()
                RunLoop.main.run(until: Date().addingTimeInterval(0.5))
                let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
                host.cacheDisplay(in: host.bounds, to: bitmap)
                let path = "/tmp/study-theme-\(dark ? "dark" : "light").png"
                try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
                print("原生视图预览：\(path)")
            }
        } catch { print(error); exit(1) }
        exit(0)
    }
}
