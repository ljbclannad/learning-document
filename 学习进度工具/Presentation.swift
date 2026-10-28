import Foundation

/// 仅调整界面文案；文件字段、用户输入和保存内容保持原样。
enum Presentation {
    static func text(_ source: String) -> String {
        let replacements: [(String, String)] = [
            ("岗位定向与完整模拟", "专题整理与综合实践"),
            ("项目追问与系统设计", "项目研讨与系统设计"),
            ("分主题闭卷与查漏", "主题回顾与知识整理"),
            ("完整模拟一", "综合实践一"), ("完整模拟二", "综合实践二"),
            ("完整模拟", "综合实践"), ("综合模拟", "综合练习"),
            ("模拟面试", "交流练习"), ("面试训练", "表达练习"),
            ("面试表达", "技术表达"), ("面试准备", "学习整理"),
            ("面试前", "交流前"), ("面试官", "交流伙伴"), ("面试", "技术交流"),
            ("目标岗位要求", "当前学习目标"), ("实际目标岗位", "当前技术方向"),
            ("目标岗位", "学习方向"), ("岗位匹配", "方向梳理"),
            ("岗位要求", "实践要求"), ("岗位", "方向"),
            ("简历核对", "经历整理"), ("简历表达", "项目总结"),
            ("简历", "项目经历"), ("求职", "学习"),
            ("自我介绍", "经历概述"), ("反问", "开放问题"),
            ("连续追问", "延伸讨论"), ("项目追问", "项目研讨"),
            ("可应对追问", "融会贯通"), ("追问", "延伸问题"),
            ("闭卷问答", "独立回顾"), ("闭卷", "独立回顾"),
            ("脱稿", "独立"), ("限时", "专注"), ("答题", "实践"),
            ("错题", "待巩固内容"), ("复测", "再次验证"),
            ("待复习", "待回顾"), ("复习", "回顾"),
            ("我的解释或答案要点", "理解与思考"),
            ("可独立解释", "清晰理解"), ("需提示", "继续探索"),
            ("可动手验证", "实践验证"), ("未评估", "尚未记录")
        ]
        return replacements.reduce(source) { value, pair in
            value.replacingOccurrences(of: pair.0, with: pair.1)
        }
    }

    static func reference(_ path: String) -> String {
        text(path.components(separatedBy: "/").last ?? path)
    }
}

enum ReadingLink {
    /// 周计划的引用以项目根目录为起点，不能使用经过展示替换的标题寻址。
    static func file(_ reference: String, planRoot: String) throws -> URL {
        let project = URL(fileURLWithPath: planRoot).deletingLastPathComponent().deletingLastPathComponent().resolvingSymlinksInPath()
        let path = String(reference.split(separator: "|", maxSplits: 1)[0]).components(separatedBy: "#")[0]
        let target = project.appendingPathComponent(path.hasSuffix(".md") ? path : path + ".md").standardizedFileURL.resolvingSymlinksInPath()
        var directory: ObjCBool = false
        guard target.path.hasPrefix(project.path + "/"), target.pathExtension == "md",
              FileManager.default.fileExists(atPath: target.path, isDirectory: &directory), !directory.boolValue else {
            throw NSError(domain: "阅读入口", code: 1, userInfo: [NSLocalizedDescriptionKey: "对应笔记不存在或已移动，请检查周计划中的阅读链接。"])
        }
        return target
    }

    static func obsidianURL(_ file: URL) -> URL {
        // 官方 open?path 接受绝对路径，可自动定位包含此文件的知识库。
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        let path = file.path.addingPercentEncoding(withAllowedCharacters: allowed)!
        return URL(string: "obsidian://open?path=\(path)&paneType=tab")!
    }
}
