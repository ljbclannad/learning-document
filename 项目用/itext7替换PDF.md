```java
package com.sano.slmc.business.util;

  

import java.io.IOException;

import java.util.ArrayList;

import java.util.HashMap;

import java.util.List;

import java.util.Map;

import java.util.stream.Collectors;

  

import com.itextpdf.io.font.PdfEncodings;

import com.itextpdf.kernel.colors.ColorConstants;

import com.itextpdf.kernel.font.PdfFont;

import com.itextpdf.kernel.font.PdfFontFactory;

import com.itextpdf.kernel.font.PdfFontFactory.EmbeddingStrategy;

import com.itextpdf.kernel.geom.Rectangle;

import com.itextpdf.kernel.pdf.PdfDocument;

import com.itextpdf.kernel.pdf.PdfPage;

import com.itextpdf.kernel.pdf.PdfReader;

import com.itextpdf.kernel.pdf.PdfWriter;

import com.itextpdf.kernel.pdf.canvas.PdfCanvas;

import com.itextpdf.kernel.pdf.canvas.parser.EventType;

import com.itextpdf.kernel.pdf.canvas.parser.PdfTextExtractor;

import com.itextpdf.kernel.pdf.canvas.parser.data.IEventData;

import com.itextpdf.kernel.pdf.canvas.parser.data.TextRenderInfo;

import com.itextpdf.kernel.pdf.canvas.parser.listener.LocationTextExtractionStrategy;

import com.sano.slmc.business.util.ReplaceTextInPdfUtil.CustomLocationTextStrategy.TextLocation;

  

public class ReplaceTextInPdfUtil {

public static void main(String[] args) throws IOException {

// 使用ClassLoader获取资源文件

ClassLoader classLoader = ReplaceTextInPdfUtil.class.getClassLoader();

String src = classLoader.getResource("test1.pdf").getPath();

String dest = "test_replace.pdf"; // 输出到当前目录

  

Map<String, String> replacements = new HashMap<>();

replacements.put("王先生", "八面玲珑龟");

  

// 使用 try-with-resources

try (PdfDocument pdfDoc = new PdfDocument(new PdfReader(src), new PdfWriter(dest))) {

for (int i = 1; i <= pdfDoc.getNumberOfPages(); i++) {

PdfPage page = pdfDoc.getPage(i);

CustomLocationTextStrategy strategy = new CustomLocationTextStrategy();

String content = PdfTextExtractor.getTextFromPage(page, strategy);

  

System.out.println("页面 " + i + " 内容: " + content);

  

// 处理所有替换文本

for (Map.Entry<String, String> entry : replacements.entrySet()) {

String oldText = entry.getKey();

String newText = entry.getValue();

  

List<TextLocation> matchedLocations = strategy.getLocations().stream()

.filter(location -> location.getText().trim().contains(oldText.trim()))

.collect(Collectors.toList());

  

System.out.println("找到 [" + oldText + "] 的匹配位置数量: " + matchedLocations.size());

  

for (TextLocation location : matchedLocations) {

try {

replaceText(page, location, newText);

System.out.println("完成替换: " + oldText + " -> " + newText);

} catch (IOException e) {

e.printStackTrace();

}

}

}

}

System.out.println("替换完成，新文件保存到: " + dest);

}

}

  

private static void replaceText(PdfPage page, TextLocation location, String newText) throws IOException {

Rectangle rect = location.getRectangle();

PdfCanvas canvas = new PdfCanvas(page, true);

String oldText = location.getText();

  

// 计算字体大小和位置调整

// float fontSize = rect.getHeight();

// float textWidth = rect.getWidth();

// float scale = textWidth / oldText.length();

// float newTextWidth = scale * newText.length();

// float xOffset = (textWidth - newTextWidth) / 2; // 居中对齐

PdfFont font = PdfFontFactory.createFont("./src/main/resources/MiSans-Medium.ttf",

PdfEncodings.IDENTITY_H, EmbeddingStrategy.FORCE_EMBEDDED);

  

// 使用白色矩形覆盖原始文本

canvas.saveState()

.setFillColor(ColorConstants.WHITE)

.rectangle(rect)

.fill()

.restoreState();

  

// 写入新文本

canvas.beginText()

.setFontAndSize(font, rect.getHeight())

.moveText(rect.getLeft(), rect.getBottom())

.showText(newText)

.endText();

  

canvas.release();

}

  

// 创建自定义的文本提取策略类

static class CustomLocationTextStrategy extends LocationTextExtractionStrategy {

private List<TextLocation> locations = new ArrayList<>();

private StringBuilder currentText = new StringBuilder();

private List<Rectangle> currentRectangles = new ArrayList<>();

private float lastY = -1; // 记录上一个文本的Y坐标

  

@Override

public void eventOccurred(IEventData data, EventType type) {

if (type == EventType.RENDER_TEXT) {

TextRenderInfo renderInfo = (TextRenderInfo) data;

System.out.printf("Text: %s, X: %.2f, Y: %.2f, Width: %.2f, Height: %.2f%n",

renderInfo.getText(),

renderInfo.getBaseline().getBoundingRectangle().getLeft(),

renderInfo.getBaseline().getBoundingRectangle().getBottom(),

renderInfo.getBaseline().getBoundingRectangle().getWidth(),

renderInfo.getBaseline().getBoundingRectangle().getHeight());

String text = renderInfo.getText();

Rectangle rectangle = renderInfo.getBaseline().getBoundingRectangle();

rectangle.setHeight(rectangle.getHeight() + 88);

rectangle.setY(rectangle.getBottom() - 10);

float currentY = rectangle.getBottom();

  

// 检查是否换行（Y坐标发生显著变化）

boolean isNewLine = lastY != -1 && Math.abs(currentY - lastY) > 1;

  

// 如果是新行且有累积的文本，保存当前文本

if (isNewLine && currentText.length() > 0) {

saveCurrentText();

}

  

// 累积文本和矩形

currentText.append(text);

currentRectangles.add(rectangle);

lastY = currentY;

  

// 如果遇到空格、特殊字符或是一行的结束，认为是一个词的结束

if (text.trim().isEmpty() || text.endsWith(" ") || text.endsWith("\n")) {

saveCurrentText();

}

}

super.eventOccurred(data, type);

}

  

private void saveCurrentText() {

if (currentText.length() > 0) {

// 合并所有矩形

Rectangle mergedRect = mergeRectangles(currentRectangles);

locations.add(new TextLocation(currentText.toString().trim(), mergedRect));

  

// 重置缓存

currentText = new StringBuilder();

currentRectangles = new ArrayList<>();

}

}

  

private Rectangle mergeRectangles(List<Rectangle> rectangles) {

if (rectangles.isEmpty()) {

return null;

}

float minX = Float.MAX_VALUE;

float minY = Float.MAX_VALUE;

float maxX = Float.MIN_VALUE;

float maxY = Float.MIN_VALUE;

  

for (Rectangle rect : rectangles) {

minX = Math.min(minX, rect.getLeft());

minY = Math.min(minY, rect.getBottom());

maxX = Math.max(maxX, rect.getRight());

maxY = Math.max(maxY, rect.getTop());

}

  

return new Rectangle(minX, minY, maxX - minX, maxY - minY);

}

  

@Override

public String getResultantText() {

// 处理最后一个词

saveCurrentText();

return super.getResultantText();

}

  

public List<TextLocation> getLocations() {

return locations;

}

  

static class TextLocation {

private String text;

private Rectangle rectangle;

  

public TextLocation(String text, Rectangle rectangle) {

this.text = text;

this.rectangle = rectangle;

}

  

public String getText() {

return text;

}

  

public Rectangle getRectangle() {

return rectangle;

}

}

}

}
```