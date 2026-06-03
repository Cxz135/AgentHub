---
name: file_converter
description: 通用文件格式转换工具组，支持PDF/MD/TXT之间的互转，所有方法都接收文件路径，返回转换后的文件路径
supported_methods: [from_pdf, to_pdf, from_md, to_md]
dependencies: 首次使用前需要安装依赖：pip install pymupdf markdown weasyprint beautifulsoup4
---
# 文件格式转换工具使用说明
## 可用方法列表
1. from_pdf: 从PDF提取文本，输出TXT文件
2. to_pdf: 将文本/MD转成PDF文件
3. from_md: 从Markdown提取纯文本，输出TXT文件
4. to_md: 将纯文本格式化转成Markdown文件

## 调用格式
你需要调用这个工具时，严格按照以下格式输出：
【调用Skill: file_converter，方法: {方法名}，输入内容: {用户提供的文件绝对路径}】

## 示例
用户说"帮我把这个PDF转成文本"，你输出：
【调用Skill: file_converter，方法: from_pdf，输入内容: /Users/xxx/Downloads/report.pdf】