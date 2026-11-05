import SwiftUI
import AppKit

struct StudyTask: Codable { var done: Bool; var text: String }
struct StudyDay: Codable {
    var number: Int; var title: String; var date: String; var hours: Double?
    var status: String; var level: String; var tasks: [StudyTask]; var records: [String: String]
}
struct Summary: Codable { var status: String; var completed: Int; var hours: Double }
struct Week: Codable {
    var id: String; var title: String; var days: [StudyDay]; var references: [String]
    var review: [String: String]; var summary: Summary
}
struct Snapshot: Codable {
    var revision: String; var weeks: [Week]; var summary: Summary
    var statuses: [String]; var levels: [String]; var recordLabels: [String]; var reviewLabels: [String]; var root: String
}

@MainActor final class StudyModel: ObservableObject {
    @Published var snapshot: Snapshot?
    @Published var week = 0
    @Published var day = 0
    @Published var draft: StudyDay?
    @Published var review: [String: String] = [:]
    @Published var hours = ""
    @Published var dirty = false
    @Published var message = ""
    @Published var error = false
    let root: String

    init() {
        root = UserDefaults.standard.string(forKey: "planRoot") ?? (Bundle.main.object(forInfoDictionaryKey: "StudyPlanRoot") as? String ?? "")
        load()
        if CommandLine.arguments.contains("--check") {
            do { try ImageAttachments.check() }
            catch { print("图片检查失败：\(error)"); exit(1) }
            if let snapshot {
                // 验证实际计划的展示文案，且不改动传给存储层的原始值。
                let labels = snapshot.weeks.flatMap { w in [w.title] + w.days.flatMap { d in [d.title] + d.tasks.map(\.text) } }
                for label in labels {
                    let display = Presentation.text(label)
                    precondition(!["面试", "简历", "岗位", "求职", "闭卷", "追问"].contains(where: { display.contains($0) }))
                }
                precondition(Presentation.text("可应对追问") == "融会贯通")
                precondition(Presentation.reference("目录/面试准备/技术取舍分析框架") == "技术取舍分析框架")
                for reference in snapshot.weeks.flatMap(\.references) {
                    let file = try! ReadingLink.file(reference, planRoot: root)
                    let uri = ReadingLink.obsidianURL(file)
                    let components = URLComponents(url: uri, resolvingAgainstBaseURL: false)!
                    precondition(components.queryItems!.first(where: { $0.name == "path" })!.value == file.path)
                }
                let special = URL(fileURLWithPath: "/tmp/中文 空格/笔记 & + %.md")
                let query = URLComponents(url: ReadingLink.obsidianURL(special), resolvingAgainstBaseURL: false)!.queryItems!
                precondition(query.first(where: { $0.name == "path" })!.value == special.path)
                precondition((try? ReadingLink.file("../../不存在", planRoot: root)) == nil)
                print("原生应用读取成功：\(snapshot.weeks.count) 周，\(snapshot.weeks.reduce(0) { $0 + $1.days.count }) 个学习日。")
                exit(0)
            }
            print(message)
            exit(1)
        }
    }
    func call(_ request: [String: Any]) throws -> Snapshot {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.environment = ProcessInfo.processInfo.environment.merging(["PYTHONDONTWRITEBYTECODE": "1"]) { _, new in new }
        process.arguments = [Bundle.main.resourceURL!.appendingPathComponent("native_bridge.py").path]
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input; process.standardOutput = output; process.standardError = errors
        try process.run()
        try input.fileHandleForWriting.write(contentsOf: JSONSerialization.data(withJSONObject: request))
        try input.fileHandleForWriting.close()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let reason = object["error"] as? String {
            throw NSError(domain: "学习文档", code: 1, userInfo: [NSLocalizedDescriptionKey: reason])
        }
        guard process.terminationStatus == 0 else {
            throw NSError(domain: "学习文档", code: 2, userInfo: [NSLocalizedDescriptionKey: "无法读取文档，请检查计划目录和 Python 3 环境。"])
        }
        return try JSONDecoder().decode(Snapshot.self, from: data)
    }
    func checkEvidencePreview() {
        precondition(EvidenceRenderer.blocks("~~~sql\nSELECT 1;\n~~~") == [.code("sql", "SELECT 1;")])
        precondition(EvidenceRenderer.blocks("```\na\n\n    b") == [.code("", "a\n\n    b")])
        precondition(EvidenceRenderer.blocks("````md\n```\n````") == [.code("md", "```")])
        precondition(EvidenceRenderer.blocks("```java\r\n    run();\r\n```\r\n后文") == [.code("java", "    run();"), .prose("后文")])
        precondition(EvidenceRenderer.blocks("```java\na\n```\n```sql\nb\n```") == [.code("java", "a"), .code("sql", "b")])
        guard draft != nil else { print(message); exit(1) }
        if CommandLine.arguments.contains("--from-document") {
            select(0, 0, confirm: false)
        } else {
            draft!.records["代码、图、实验或问答证据"] = "示例说明\n\n```java\nif (ready) {\n    run();\n}\n```\n\n验证完成"
        }
        let expectedCodes = EvidenceRenderer.blocks(draft!.records["代码、图、实验或问答证据"] ?? "").compactMap { block -> String? in
            if case .code(_, let code) = block, !code.isEmpty { return code }
            return nil
        }
        let host = NSHostingView(rootView: ContentView(model: self).editor("代码、图、实验或问答证据", weekly: false))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 650, height: 420), styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        func textViews(_ view: NSView) -> [NSTextView] {
            (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(textViews)
        }
        let views = textViews(host)
        guard let preview = views.first, !expectedCodes.isEmpty,
              expectedCodes.allSatisfy({ preview.string.contains($0) }), !preview.string.contains("```") else {
            print("失败：证据模块显示了代码围栏原文，或未保留代码缩进。")
            exit(1)
        }
        for code in expectedCodes {
        let range = (preview.string as NSString).range(of: code)
        guard let font = preview.textStorage?.attribute(.font, at: range.location, effectiveRange: nil) as? NSFont,
              font.fontDescriptor.symbolicTraits.contains(.monoSpace) else {
            print("失败：代码没有使用等宽字体。")
            exit(1)
        }
        }
        print("通过：实际证据视图完整展示 \(expectedCodes.count) 个代码块，隐藏围栏、保留缩进，并使用等宽代码字体。")
        exit(0)
    }
    func mayDiscard() -> Bool {
        if !dirty { return true }
        let alert = NSAlert()
        alert.messageText = "当前修改尚未保存"
        alert.informativeText = "切换或关闭会放弃这些修改。请取消后保存，或选择放弃修改。"
        alert.addButton(withTitle: "取消"); alert.addButton(withTitle: "放弃修改")
        let discard = alert.runModal() == .alertSecondButtonReturn
        if discard { dirty = false }
        return discard
    }
    func load() {
        do {
            let firstLoad = snapshot == nil
            snapshot = try call(["action": "load", "root": root])
            if firstLoad, let found = snapshot?.weeks.firstIndex(where: { $0.summary.completed < 5 }) {
                week = found
                day = snapshot!.weeks[week].days.firstIndex(where: { $0.status == "学习中" || $0.status == "待复习" }) ?? snapshot!.weeks[week].days.firstIndex(where: { $0.status != "已完成" }) ?? 0
            }
            select(week, day, confirm: false)
            message = "已读取本地学习文档"; error = false
        } catch { show(error) }
    }
    func select(_ w: Int, _ d: Int, confirm: Bool = true) {
        if confirm && !mayDiscard() { return }
        guard let snapshot else { return }
        week = w; day = d; draft = snapshot.weeks[w].days[d]; review = snapshot.weeks[w].review
        hours = draft!.hours.map { String(format: "%g", $0) } ?? ""
        dirty = false
    }
    func adjacentDay(_ offset: Int) -> (week: Int, day: Int)? {
        guard let snapshot else { return nil }
        let positions = snapshot.weeks.enumerated().flatMap { w, value in
            value.days.indices.map { (week: w, day: $0) }
        }
        guard let current = positions.firstIndex(where: { $0.week == week && $0.day == day }),
              positions.indices.contains(current + offset) else { return nil }
        return positions[current + offset]
    }
    func moveDay(_ offset: Int) {
        guard let target = adjacentDay(offset) else { return }
        select(target.week, target.day)
    }
    func change(_ action: (inout StudyDay) -> Void) {
        guard var value = draft else { return }; action(&value); draft = value; dirty = true
    }
    func save() {
        guard let snapshot, let draft else { return }
        if !hours.isEmpty && (Double(hours) == nil || !Double(hours)!.isFinite) {
            message = "请填写有效的小时数，例如 4.5。"; error = true; return
        }
        let data: [String: Any] = ["revision": snapshot.revision, "week": snapshot.weeks[week].id, "day": day + 1,
            "status": draft.status, "level": draft.level, "date": draft.date,
            "hours": Double(hours).map { $0 as Any } ?? NSNull(), "checks": draft.tasks.map(\.done), "records": draft.records, "review": review]
        do {
            self.snapshot = try call(["action": "save", "root": root, "data": data])
            select(week, day, confirm: false)
            message = "保存成功 · 已同步 Markdown 和汇总，原文档已备份"; error = false
        } catch { show(error) }
    }
    func show(_ failure: Error) { message = failure.localizedDescription; error = true }
    func openReading(_ reference: String) {
        do {
            let file = try ReadingLink.file(reference, planRoot: root)
            let workspace = NSWorkspace.shared
            if let application = workspace.urlForApplication(withBundleIdentifier: "md.obsidian") {
                let configuration = NSWorkspace.OpenConfiguration()
                configuration.activates = true
                workspace.open([ReadingLink.obsidianURL(file)], withApplicationAt: application, configuration: configuration) { _, failure in
                    Task { @MainActor in
                        if let failure { self.show(failure) }
                        else { self.message = "已请求在 Obsidian 中打开笔记"; self.error = false }
                    }
                }
            } else if workspace.open(file) {
                message = "未找到 Obsidian，已使用默认应用打开笔记"; error = false
            } else {
                message = "未能打开笔记，请在 Finder 中检查默认打开方式。"; error = true
            }
        } catch { show(error) }
    }
    func chooseFolder() {
        guard mayDiscard() else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.message = "选择包含十二份周计划和学习进度记录的目录"
        if panel.runModal() == .OK, let url = panel.url {
            UserDefaults.standard.set(url.path, forKey: "planRoot")
            message = "已记住新目录，请退出并重新打开应用。"; error = false
        }
    }
}

struct ContentView: View {
    @ObservedObject var model: StudyModel
    @AppStorage("compactWorkspace") private var compactWorkspace = true
    @AppStorage("sidebarVisible") private var sidebarVisible = true
    let accent = Color(red: 0.15, green: 0.42, blue: 0.32)
    func field(_ key: WritableKeyPath<StudyDay, String>) -> Binding<String> {
        Binding(get: { model.draft?[keyPath: key] ?? "" }, set: { value in model.change { $0[keyPath: key] = value } })
    }
    func note(_ label: String, weekly: Bool = false) -> Binding<String> {
        Binding(get: { weekly ? model.review[label] ?? "" : model.draft?.records[label] ?? "" }, set: { value in
            if weekly { model.review[label] = value; model.dirty = true }
            else { model.change { $0.records[label] = value } }
        })
    }
    var body: some View {
        HSplitView {
            if sidebarVisible { sidebar }
            detail
        }.frame(minWidth: 930, minHeight: 700).textFieldStyle(.roundedBorder)
        .toolbar {
            ToolbarItem(placement: .navigation) {
                Button { sidebarVisible.toggle() } label: {
                    Label(sidebarVisible ? "隐藏侧边栏" : "显示侧边栏", systemImage: "sidebar.left")
                }
                .keyboardShortcut("s", modifiers: [.command, .control])
                .help(sidebarVisible ? "隐藏侧边栏（⌃⌘S）" : "显示侧边栏（⌃⌘S）")
            }
        }
    }
    private var sidebar: some View {
VStack(alignment: .leading, spacing: 18) {
                Label("研习手记", systemImage: "leaf.fill").font(.title2.bold()).foregroundStyle(accent)
                Text("工程实践 · 日常积累").foregroundStyle(.secondary)
                if let s = model.snapshot {
                    Text("\(s.summary.completed) / 60 天 · \(s.summary.hours, specifier: "%g") 小时").font(.callout)
                    ProgressView(value: Double(s.summary.completed), total: 60).tint(accent)
                    ScrollView {
                        VStack(spacing: 6) {
                            ForEach(s.weeks.indices, id: \.self) { i in
                                Button { model.select(i, 0) } label: {
                                    HStack(alignment: .top) {
                                        Text(String(format: "%02d", i+1)).monospacedDigit().foregroundStyle(.secondary)
                                        Text(Presentation.text(s.weeks[i].title.replacingOccurrences(of: "第 \(String(format: "%02d", i+1)) 周 ", with: ""))).frame(maxWidth: .infinity, alignment: .leading)
                                        Text("\(s.weeks[i].summary.completed)/5").font(.caption).foregroundStyle(.secondary)
                                    }.padding(10).background(model.week == i ? accent.opacity(0.12) : .clear).clipShape(RoundedRectangle(cornerRadius: 8))
                                }.buttonStyle(.plain)
                            }
                        }
                    }
                }
                Spacer(minLength: 0)
                Toggle("简洁视图", isOn: $compactWorkspace).toggleStyle(.switch).font(.callout)
                Label("文档保存在本地", systemImage: "internaldrive").font(.caption).foregroundStyle(.secondary)
                Button("在 Finder 中查看文档") { NSWorkspace.shared.open(URL(fileURLWithPath: model.root)) }.buttonStyle(.link)
            }.padding(22).frame(minWidth: 235, idealWidth: 265, maxWidth: 300)
    }
    private var detail: some View {
VStack(spacing: 0) {
                if let s = model.snapshot, let d = model.draft {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 22) {
                            Text(Presentation.text(s.weeks[model.week].title)).font(.largeTitle.bold())
                            Text("理解一个原理，完成一次实践，留下一点思考。").foregroundStyle(.secondary)
                            HStack(spacing: 10) {
                                ForEach(0..<5) { i in
                                    Button { model.select(model.week, i) } label: {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text("第 \(i+1) 天").font(.headline)
                                            Text(Presentation.text(s.weeks[model.week].days[i].status)).font(.caption).foregroundStyle(.secondary)
                                        }.frame(maxWidth: .infinity, alignment: .leading).padding(12).background(model.day == i ? accent.opacity(0.14) : Color.primary.opacity(0.04)).clipShape(RoundedRectangle(cornerRadius: 10))
                                    }.buttonStyle(.plain)
                                }
                            }
                            dayFields(d, s)
                            GroupBox {
                                editor("我的解释或答案要点", weekly: false).padding(12)
                            }
                            if !compactWorkspace {
                            GroupBox("学习记录") {
                                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 18) {
                                    ForEach(s.recordLabels.filter { $0 != "代码、图、实验或问答证据" && $0 != "我的解释或答案要点" }, id: \.self) { label in editor(label, weekly: false) }
                                }.padding(12)
                            }
                            } else {
                                Label("关闭侧栏的简洁视图，可编辑其余实践笔记与周总结。", systemImage: "text.book.closed").font(.caption).foregroundStyle(.secondary)
                            }
                            if !compactWorkspace {
                            GroupBox("实践笔记") {
                                VStack(alignment: .leading, spacing: 18) {
                                editor("代码、图、实验或问答证据", weekly: false)
                                }.padding(12)
                            }
                            }
                            tasksView(d)
                            if !compactWorkspace {
                            DisclosureGroup("本周复盘") {
                                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 18) {
                                    ForEach(s.reviewLabels, id: \.self) { label in editor(label, weekly: true) }
                                }.padding(.top, 12)
                            }
                            }
                            DisclosureGroup("本周阅读入口") {
                                VStack(alignment: .leading, spacing: 8) {
                                    ForEach(s.weeks[model.week].references, id: \.self) { reference in
                                        Button { model.openReading(reference) } label: {
                                            Label(Presentation.reference(reference), systemImage: "arrow.up.forward.square").font(.callout)
                                        }.buttonStyle(.link).help("优先在 Obsidian 中打开笔记")
                                    }
                                }.padding(.top, 10).frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }.padding(28)
                    }
                } else {
                    Spacer(); Text("无法载入学习计划").font(.title2); Button("选择计划文件夹") { model.chooseFolder() }; Spacer()
                }
                Divider()
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(model.dirty ? "有未保存的修改" : "已与本地文档同步").font(.caption).foregroundStyle(.secondary)
                        Text(model.message).font(.caption).foregroundStyle(model.error ? .red : .secondary).textSelection(.enabled)
                    }
                    Spacer()
                            HStack {
                                Button { model.moveDay(-1) } label: {
                                    Label("前一天", systemImage: "chevron.left")
                                }
                                .disabled(model.adjacentDay(-1) == nil)
                                .help("前一天（⌘⌥←），支持跨周切换")
                                Button { model.moveDay(1) } label: {
                                    HStack(spacing: 5) {
                                        Text("后一天")
                                        Image(systemName: "chevron.right")
                                    }
                                }
                                .disabled(model.adjacentDay(1) == nil)
                                .help("后一天（⌘⌥→），支持跨周切换")
                            }.buttonStyle(.bordered)
                    Button("重新加载") { if model.mayDiscard() { model.load() } }
                    Button("保存到文档") { model.save() }.buttonStyle(.borderedProminent).tint(accent).keyboardShortcut("s").disabled(model.draft == nil)
                }.padding(18)
            }.frame(minWidth: 660)
    }
    private func dayFields(_ d: StudyDay, _ s: Snapshot) -> some View {
GroupBox {
                                VStack(alignment: .leading, spacing: 16) {
                                    Text(Presentation.text(d.title)).font(.title2.bold())
                                    HStack {
                                        Picker("进展", selection: field(\.status)) { ForEach(s.statuses, id: \.self) { Text(Presentation.text($0)).tag($0) } }
                                        Picker("理解程度", selection: field(\.level)) { ForEach(s.levels, id: \.self) { Text(Presentation.text($0)).tag($0) } }
                                    }
                                    HStack {
                                        Toggle("填写日期", isOn: Binding(get: { !d.date.isEmpty }, set: { selected in model.change { $0.date = selected ? Self.dateFormat.string(from: Date()) : "" } })).toggleStyle(.checkbox)
                                        if !d.date.isEmpty {
                                            DatePicker("实际日期", selection: Binding(get: { Self.dateFormat.date(from: d.date) ?? Date() }, set: { value in model.change { $0.date = Self.dateFormat.string(from: value) } }), displayedComponents: .date).labelsHidden()
                                        }
                                        Spacer()
                                        Text("实际时长")
                                        TextField("例如 4.5", text: Binding(get: { model.hours }, set: { model.hours = $0; model.dirty = true })).frame(width: 90)
                                        Text("小时")
                                    }
                                    Text("按实际情况记录；勾选任务不会自动标记当天完成。").font(.caption).foregroundStyle(.secondary)
                                }.padding(12)
                            }
    }
    private func tasksView(_ d: StudyDay) -> some View {
GroupBox("今日安排") {
                                VStack(alignment: .leading, spacing: 14) {
                                    ForEach(d.tasks.indices, id: \.self) { i in
                                        Toggle(isOn: Binding(get: { model.draft!.tasks[i].done }, set: { value in model.change { $0.tasks[i].done = value } })) {
                                            Text(Presentation.text(d.tasks[i].text)).fixedSize(horizontal: false, vertical: true)
                                        }.toggleStyle(.checkbox)
                                    }
                                }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                            }
    }
    func editor(_ label: String, weekly: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(Presentation.text(label)).font(.callout).foregroundStyle(.secondary)
            if label == "代码、图、实验或问答证据" && !weekly {
                EvidenceEditor(source: note(label, weekly: weekly), root: model.root)
            } else if label == "我的解释或答案要点" && !weekly {
                ReflectionNotesEditor(source: note(label), root: model.root)
            } else {
            TextEditor(text: note(label, weekly: weekly)).font(.body).frame(height: 95).padding(5).background(Color(nsColor: .textBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 6)).overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.2)))
            }
        }
    }
    static let dateFormat: DateFormatter = {
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyy-MM-dd"; return formatter
    }()
}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var model: StudyModel?
    func applicationDidFinishLaunching(_ notification: Notification) {
        if CommandLine.arguments.contains("--check-markdown") { NotesMarkdown.check() }
        if CommandLine.arguments.contains("--check-evidence") {
            let testModel = StudyModel()
            testModel.checkEvidencePreview()
        }
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply { model?.mayDiscard() == false ? .terminateCancel : .terminateNow }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func windowShouldClose(_ sender: NSWindow) -> Bool { model?.mayDiscard() ?? true }
}

@main struct StudyApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject var model = StudyModel()
    var body: some Scene {
        Window("研习手记", id: "main") {
            ContentView(model: model).onAppear {
                delegate.model = model
                NSApp.setActivationPolicy(.regular)
                NSApp.activate(ignoringOtherApps: true)
                DispatchQueue.main.async { NSApp.windows.first?.delegate = delegate }
            }
        }.defaultSize(width: 1150, height: 840)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("学习日") {
                Button("前一天") { model.moveDay(-1) }
                    .keyboardShortcut(.leftArrow, modifiers: [.command, .option])
                    .disabled(model.adjacentDay(-1) == nil)
                Button("后一天") { model.moveDay(1) }
                    .keyboardShortcut(.rightArrow, modifiers: [.command, .option])
                    .disabled(model.adjacentDay(1) == nil)
            }
            CommandGroup(after: .saveItem) { Button("选择学习计划文件夹…") { model.chooseFolder() } }
        }
    }
}
