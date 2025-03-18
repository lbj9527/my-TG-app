#!/usr/bin/env python
"""
修复Telegram转发应用中的错误
1. 修复元数据加载问题
2. 修复Peer ID无效错误
3. 增强上传时对消息结构的兼容性
"""

import os
import sys
import shutil
import logging
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_errors')

def backup_file(file_path):
    """创建文件备份"""
    if os.path.exists(file_path):
        backup_path = file_path + '.bak'
        logger.info(f"备份文件 {file_path} 到 {backup_path}")
        shutil.copy2(file_path, backup_path)
        return True
    return False

def fix_assember_file():
    """修复assember.py文件中的元数据加载问题"""
    file_path = os.path.join('tg_forwarder', 'uploader', 'assember.py')
    
    if not os.path.exists(file_path):
        logger.error(f"文件 {file_path} 不存在")
        return False
    
    backup_file(file_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 确保在assemble_batch方法开始处添加_load_metadata调用
    pattern = r'(def assemble_batch\([^:]+:[^"]*"[^"]*"\s+logger\.info\([^)]+\))'
    replacement = r'\1\n\n        # 重新加载最新的元数据文件，确保获取最新数据\n        self._load_metadata()'
    
    content = re.sub(pattern, replacement, content)
    
    # 2. 修复metadata访问错误
    pattern = r'(if result and )("caption" in result\[0\]\["metadata"\])'
    replacement = r'\1"caption" in result[0].get("metadata", {})'
    content = re.sub(pattern, replacement, content)
    
    # 3. 增强caption安全访问
    pattern = r'(logger\.debug\(f"设置媒体组的标题: )(.*?)(\}\.\.\."\))'
    replacement = r'\1{caption[:30] if caption else "None"}\3'
    content = re.sub(pattern, replacement, content)
    
    # 保存修改后的文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"已修复文件 {file_path}")
    return True

def fix_client_file():
    """修复client.py文件中的Peer ID无效错误"""
    file_path = os.path.join('tg_forwarder', 'client.py')
    
    if not os.path.exists(file_path):
        logger.error(f"文件 {file_path} 不存在")
        return False
    
    backup_file(file_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 添加handle_updates方法来处理Peer ID无效错误
    handle_updates_method = '''
    async def handle_updates(self):
        """
        处理Telegram更新
        重写此方法以增加错误处理，防止Peer ID无效错误导致程序崩溃
        """
        try:
            # 调用原始方法
            await super().handle_updates()
        except ValueError as e:
            if "Peer id invalid" in str(e):
                # 记录错误但不中断程序
                logger.warning(f"处理更新时遇到无效的Peer ID: {str(e)}")
            else:
                # 其他ValueError重新抛出
                raise
        except Exception as e:
            # 记录其他异常但不终止程序
            logger.error(f"处理更新时发生错误: {str(e)}")
            import traceback
            logger.debug(f"错误详情: {traceback.format_exc()}")
    '''
    
    # 查找适合插入的位置
    last_method_end = content.rfind('        raise')
    
    if last_method_end > 0:
        # 在方法结束后插入新方法
        content = content[:last_method_end+15] + '\n' + handle_updates_method + content[last_method_end+15:]
        
        # 保存修改后的文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"已修复文件 {file_path}")
        return True
    else:
        logger.error(f"未找到适合的插入位置")
        return False

def fix_media_uploader_file():
    """修复media_uploader.py文件中的消息结构兼容性问题"""
    file_path = os.path.join('tg_forwarder', 'uploader', 'media_uploader.py')
    
    if not os.path.exists(file_path):
        logger.error(f"文件 {file_path} 不存在")
        return False
    
    backup_file(file_path)
    
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 增强_upload_media_group方法，添加对消息结构的防错检查
    pattern = r'(async def _upload_media_group\([^)]+\)[^{]*{[^}]*?)\s+# 准备媒体组数据'
    replacement = r'\1\n        # 检查消息结构\n        for i, msg in enumerate(messages[:3]):  # 只检查前三条消息\n            logger.debug(f"媒体组消息 {i+1} 结构: {list(msg.keys())}")\n        \n        # 准备媒体组数据'
    content = re.sub(pattern, replacement, content)
    
    # 增强caption查找逻辑，支持嵌套metadata结构
    pattern = r'(# 查找第一个有caption的消息\s+for msg in messages:[^}]+?)break'
    replacement = r'\1break\n            \n            # 兼容可能的嵌套metadata结构\n            metadata = msg.get("metadata", {})\n            if isinstance(metadata, dict) and metadata.get("caption"):\n                caption = metadata.get("caption")\n                caption_entities = metadata.get("caption_entities")\n                logger.debug(f"从metadata中找到媒体组标题: {caption[:30] if caption else \'None\'}...")\n                break'
    content = re.sub(pattern, replacement, content)
    
    # 修改文件路径获取逻辑，支持嵌套结构
    pattern = r'(file_path = msg\.get\("file_path"\))'
    replacement = r'\1\n            if not file_path and isinstance(msg.get("metadata"), dict):\n                file_path = msg.get("metadata", {}).get("file_path")'
    content = re.sub(pattern, replacement, content)
    
    # 修改媒体类型获取，支持不同的字段名和嵌套结构
    pattern = r'(# 确定媒体类型\s+)(msg_type = msg\.get\("message_type"\))'
    replacement = r'\1# 确定媒体类型，支持两种可能的结构\n            msg_type = msg.get("type") or msg.get("message_type")\n            if not msg_type and isinstance(msg.get("metadata"), dict):\n                msg_type = msg.get("metadata", {}).get("message_type")\n            \n            if not msg_type:\n                logger.warning(f"消息 {msg.get(\'message_id\')} 没有指定媒体类型")\n                # 尝试根据文件扩展名猜测类型\n                ext = os.path.splitext(file_path)[1].lower()\n                if ext in [\'.jpg\', \'.jpeg\', \'.png\', \'.webp\']:\n                    msg_type = "photo"\n                    logger.info(f"根据扩展名将消息 {msg.get(\'message_id\')} 类型设为 photo")\n                elif ext in [\'.mp4\', \'.avi\', \'.mov\', \'.mkv\']:\n                    msg_type = "video"\n                    logger.info(f"根据扩展名将消息 {msg.get(\'message_id\')} 类型设为 video")\n                elif ext in [\'.mp3\', \'.ogg\', \'.m4a\', \'.wav\']:\n                    msg_type = "audio"\n                    logger.info(f"根据扩展名将消息 {msg.get(\'message_id\')} 类型设为 audio")\n                else:\n                    msg_type = "document"\n                    logger.info(f"根据扩展名将消息 {msg.get(\'message_id\')} 类型设为 document")'
    content = re.sub(pattern, replacement, content)
    
    # 添加获取属性的辅助函数
    pattern = r'(# 第一个消息使用caption，其他消息不使用\s+use_caption = i == 0 and caption)'
    replacement = r'\1 is not None\n            \n            # 获取附加属性的辅助函数\n            def get_prop(prop_name, default=None):\n                # 直接在消息中查找\n                value = msg.get(prop_name)\n                if value is not None:\n                    return value\n                \n                # 在metadata中查找\n                if isinstance(msg.get("metadata"), dict):\n                    value = msg.get("metadata", {}).get(prop_name)\n                    if value is not None:\n                        return value\n                \n                return default'
    content = re.sub(pattern, replacement, content)
    
    # 使用get_prop函数获取属性
    content = content.replace('width=msg.get("width")', 'width=get_prop("width")')
    content = content.replace('height=msg.get("height")', 'height=get_prop("height")')
    content = content.replace('duration=msg.get("duration")', 'duration=get_prop("duration")')
    content = content.replace('file_name=msg.get("file_name")', 'file_name=get_prop("file_name")')
    content = content.replace('performer=msg.get("performer")', 'performer=get_prop("performer")')
    content = content.replace('title=msg.get("title")', 'title=get_prop("title")')
    
    # 改进不支持媒体类型的处理
    pattern = r'(else:\s+)logger\.warning\(f"不支持的媒体类型: {msg_type}"\)\s+continue'
    replacement = r'\1logger.warning(f"不支持的媒体类型: {msg_type}，尝试作为文档发送")\n                media = InputMediaDocument(\n                    file_path,\n                    caption=caption if use_caption else None,\n                    caption_entities=caption_entities if use_caption else None\n                )'
    content = re.sub(pattern, replacement, content)
    
    # 添加异常处理和日志
    pattern = r'(media_group\.append\(media\))'
    replacement = r'\1\n                logger.debug(f"已添加媒体项: 类型={msg_type}, 文件={os.path.basename(file_path)}")\n                \n            except Exception as e:\n                logger.error(f"创建媒体项时出错: {str(e)}")\n                import traceback\n                logger.debug(f"错误详情: {traceback.format_exc()}")'
    content = re.sub(pattern, replacement, content)
    
    # 保存修改后的文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"已修复文件 {file_path}")
    return True

def main():
    """主函数"""
    success = True
    
    logger.info("开始修复错误...")
    
    # 修复assember.py文件
    if not fix_assember_file():
        success = False
    
    # 修复client.py文件
    if not fix_client_file():
        success = False
    
    # 修复media_uploader.py文件
    if not fix_media_uploader_file():
        success = False
    
    if success:
        logger.info("所有错误修复成功！")
        return 0
    else:
        logger.error("修复过程中发生错误")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 