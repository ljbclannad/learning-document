import AppKit

// 原生矢量绘制：暖白纸面、绿色手记与新叶，按各个分辨率直接栅格化。
func render(size: Int, destination: URL) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                                  bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                  isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let scale = CGFloat(size) / 1024
    let transform = NSAffineTransform()
    transform.scale(by: scale)
    transform.concat()
    NSColor(calibratedRed: 0.96, green: 0.95, blue: 0.91, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 64, y: 64, width: 896, height: 896), xRadius: 200, yRadius: 200).fill()
    let green = NSColor(calibratedRed: 0.15, green: 0.37, blue: 0.29, alpha: 1)
    green.setFill()
    NSBezierPath(roundedRect: NSRect(x: 250, y: 216, width: 524, height: 592), xRadius: 65, yRadius: 65).fill()
    NSColor(calibratedRed: 0.91, green: 0.90, blue: 0.82, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 286, y: 240, width: 462, height: 40), xRadius: 20, yRadius: 20).fill()
    NSColor(calibratedRed: 0.23, green: 0.48, blue: 0.37, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 290, y: 310, width: 16, height: 434), xRadius: 8, yRadius: 8).fill()
    let leaf = NSBezierPath()
    leaf.move(to: NSPoint(x: 448, y: 446))
    leaf.curve(to: NSPoint(x: 660, y: 686), controlPoint1: NSPoint(x: 372, y: 598), controlPoint2: NSPoint(x: 558, y: 710))
    leaf.curve(to: NSPoint(x: 448, y: 446), controlPoint1: NSPoint(x: 694, y: 538), controlPoint2: NSPoint(x: 574, y: 420))
    NSColor(calibratedRed: 0.79, green: 0.85, blue: 0.62, alpha: 1).setFill()
    leaf.fill()
    let stem = NSBezierPath()
    stem.move(to: NSPoint(x: 428, y: 394))
    stem.curve(to: NSPoint(x: 608, y: 622), controlPoint1: NSPoint(x: 470, y: 480), controlPoint2: NSPoint(x: 536, y: 560))
    green.setStroke()
    stem.lineWidth = 18
    stem.lineCapStyle = .round
    stem.stroke()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: destination)
}

let directory = URL(fileURLWithPath: CommandLine.arguments[1])
for points in [16, 32, 128, 256, 512] {
    try render(size: points, destination: directory.appendingPathComponent("icon_\(points)x\(points).png"))
    try render(size: points * 2, destination: directory.appendingPathComponent("icon_\(points)x\(points)@2x.png"))
}
