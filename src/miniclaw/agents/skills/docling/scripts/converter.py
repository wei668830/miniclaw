# -*- coding: utf-8 -*-
"""
Docling文档转换命令行工具
将各种文档格式转换为Markdown格式
"""

import sys
import os
import argparse
import warnings
from pathlib import Path
from docling.document_converter import DocumentConverter

# 忽略警告信息，抑制stderr输出
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def convert_to_markdown(source_file: str, target_file: str, skip_images: bool = False) -> None:
    """
    将源文件转换为Markdown格式
    
    Args:
        source_file: 源文件路径或URL
        target_file: 目标Markdown文件路径
        skip_images: 是否跳过图片处理（默认False）
    """
    # 检查是否为URL
    is_url = source_file.startswith('http://') or source_file.startswith('https://')
    
    # 如果是本地文件，检查是否存在
    if not is_url and not os.path.exists(source_file):
        raise FileNotFoundError(f"源文件不存在: {source_file}")
    
    # 确保目标文件目录存在
    target_path = Path(target_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 执行转换（重定向stderr以避免显示警告）
    source_type = "URL" if is_url else "文件"
    print(f"正在转换{source_type}: {source_file}")
    if skip_images:
        print("已启用跳过图片模式")
    
    # 临时重定向stderr
    stderr_backup = sys.stderr
    markdown_content = None
    conversion_error = None
    
    try:
        sys.stderr = open(os.devnull, 'w')
        
        if skip_images:
            # 配置跳过图片处理
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import PdfFormatOption
            
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_picture_classification = False
            pipeline_options.do_picture_description = False
            pipeline_options.generate_picture_images = False
            pipeline_options.do_ocr = False  # 关闭OCR，减少内存占用
            
            converter = DocumentConverter(
                format_options={
                    "pdf": PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        else:
            converter = DocumentConverter()
        
        result = converter.convert(source_file)
        doc = result.document
        markdown_content = doc.export_to_markdown()
        
    except Exception as e:
        conversion_error = str(e)
    finally:
        sys.stderr.close()
        sys.stderr = stderr_backup
    
    # 如果docling转换失败或内容过少，尝试使用pdfplumber备用方案
    if (conversion_error or not markdown_content or len(markdown_content) < 1000):
        print(f"警告: docling转换可能不完整 (错误: {conversion_error or '内容过少'})")
        
        # 检查是否为PDF且为本地文件
        if not is_url and source_file.lower().endswith('.pdf'):
            print("尝试使用 pdfplumber 备用方案...")
            try:
                import pdfplumber
                
                with pdfplumber.open(source_file) as pdf:
                    all_text = []
                    all_text.append(f"# 文档转换结果\n\n")
                    all_text.append(f"> 使用 pdfplumber 提取 (共 {len(pdf.pages)} 页)\n\n")
                    
                    for i, page in enumerate(pdf.pages, 1):
                        print(f"  处理第 {i}/{len(pdf.pages)} 页...")
                        text = page.extract_text()
                        if text:
                            all_text.append(f"\n## 第 {i} 页\n\n")
                            all_text.append(text)
                            all_text.append("\n")
                    
                    markdown_content = ''.join(all_text)
                    print("备用方案转换成功")
            except ImportError:
                print("错误: pdfplumber 未安装，无法使用备用方案")
                if conversion_error:
                    raise Exception(f"转换失败: {conversion_error}")
            except Exception as e:
                print(f"备用方案也失败: {e}")
                if conversion_error:
                    raise Exception(f"转换失败: {conversion_error}")
        elif conversion_error:
            raise Exception(f"转换失败: {conversion_error}")
    
    # 保存Markdown内容
    if markdown_content:
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"转换完成，已保存至: {target_file}")
        print(f"输出内容: {len(markdown_content)} 字符")
    else:
        raise Exception("转换失败: 未生成任何内容")


def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(
        description='将文档转换为Markdown格式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s input.pdf output.md
  %(prog)s document.docx result.md
  %(prog)s https://arxiv.org/pdf/2206.01062 paper.md
  %(prog)s input.pdf output.md --skip-images
        """
    )
    
    parser.add_argument('source', help='源文件路径或URL（支持http://和https://）')
    parser.add_argument('target', help='目标Markdown文件路径')
    parser.add_argument('--skip-images', action='store_true', 
                        help='跳过图片处理，避免因图片导致的转换中断')
    
    args = parser.parse_args()
    
    try:
        convert_to_markdown(args.source, args.target, args.skip_images)
    except Exception as e:
        print(f"转换失败: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
