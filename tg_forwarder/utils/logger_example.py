"""
日志系统使用示例
"""

import time
import asyncio
from tg_forwarder.utils.logger import LogManager, get_logger, setup_logger

def basic_logging_example():
    """基本日志使用示例"""
    # 初始化日志系统
    setup_logger({
        'level': 'DEBUG',
        'file': 'logs/example.log'
    })
    
    # 获取日志记录器
    logger = get_logger('example')
    
    # 记录不同级别的日志
    logger.debug("这是一条调试日志")
    logger.info("这是一条信息日志")
    logger.success("这是一条成功日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    logger.critical("这是一条致命错误日志")
    
    print("\n基本日志记录示例完成。")

def progress_bar_example():
    """进度条示例"""
    logger = get_logger('progress_example')
    
    # 创建进度条
    total_files = 100
    progress_bar = logger.create_progress_bar(
        id="file_upload", 
        total=total_files, 
        desc="上传文件"
    )
    
    # 模拟文件上传
    for i in range(total_files):
        # 更新进度条
        logger.update_progress("file_upload", 1)
        
        # 模拟中途的日志输出
        if i % 20 == 0 and i > 0:
            logger.info(f"已上传 {i} 个文件")
        
        # 模拟处理时间
        time.sleep(0.05)
    
    # 关闭进度条
    logger.close_progress_bar("file_upload")
    logger.success("所有文件上传完成！")
    
    print("\n进度条示例完成。")

def multiple_progress_bars_example():
    """多个进度条示例"""
    logger = get_logger('multi_progress_example')
    
    # 创建第一个进度条：下载
    logger.create_progress_bar(
        id="download", 
        total=100, 
        desc="下载文件"
    )
    
    # 创建第二个进度条：处理
    logger.create_progress_bar(
        id="process", 
        total=100, 
        desc="处理文件"
    )
    
    # 创建第三个进度条：上传
    logger.create_progress_bar(
        id="upload", 
        total=100, 
        desc="上传文件"
    )
    
    # 模拟下载、处理、上传流程
    # 首先进行下载
    logger.set_active_progress_bar("download")
    for i in range(100):
        logger.update_progress("download", 1)
        time.sleep(0.02)
    logger.info("下载完成")
    
    # 然后进行处理
    logger.set_active_progress_bar("process")
    for i in range(100):
        logger.update_progress("process", 1)
        time.sleep(0.01)
    logger.info("处理完成")
    
    # 最后进行上传
    logger.set_active_progress_bar("upload")
    for i in range(100):
        logger.update_progress("upload", 1)
        time.sleep(0.03)
    logger.success("上传完成")
    
    # 关闭所有进度条
    logger.close_progress_bar("download")
    logger.close_progress_bar("process")
    logger.close_progress_bar("upload")
    
    print("\n多进度条示例完成。")

def log_filter_example():
    """日志过滤示例"""
    logger = get_logger('filter_example')
    
    # 记录原始日志
    logger.info("正常日志：这条消息会显示")
    logger.debug("调试日志：这条消息也会显示")
    
    # 添加过滤器，过滤包含"DEBUG"的日志
    logger.add_filter(r"^调试日志")
    
    # 过滤后的日志
    logger.info("正常日志：这条消息仍会显示")
    logger.debug("调试日志：这条消息将被过滤掉")
    
    # 清除过滤器
    logger.clear_filters()
    
    # 恢复后的日志
    logger.info("正常日志：过滤器已清除")
    logger.debug("调试日志：这条消息又可以显示了")
    
    print("\n日志过滤示例完成。")

def ffmpeg_filter_example():
    """FFmpeg日志过滤示例"""
    logger = get_logger('ffmpeg_example')
    
    # 启用FFmpeg过滤器
    logger.enable_ffmpeg_filter()
    
    # 模拟一些FFmpeg输出
    logger.info("frame=   10 fps=5.0 q=29.0 size=      2kB time=00:00:00.51 bitrate=  31.5kbits/s speed=1.02x")
    logger.info("正常日志：这条消息会显示")
    logger.info("Input #0, mp4, from 'input.mp4'")
    logger.info("Stream #0:0: Video: h264, yuv420p, 1920x1080")
    logger.info("Press [q] to stop, [?] for help")
    
    # 清除过滤器
    logger.clear_filters()
    
    # 恢复后的日志
    logger.info("过滤器已清除，FFmpeg日志现在将正常显示")
    logger.info("frame=   10 fps=5.0 q=29.0 size=      2kB time=00:00:00.51 bitrate=  31.5kbits/s speed=1.02x")
    
    print("\nFFmpeg日志过滤示例完成。")

async def download_upload_example():
    """重构下载和上传模块的示例"""
    # 使用全局配置初始化日志系统
    LogManager.setup({
        'level': 'INFO',
        'file': 'logs/download_upload.log',
        'show_progress': True
    })
    
    # 获取下载模块的日志记录器
    dl_logger = LogManager.get_logger('downloader')
    
    # 获取上传模块的日志记录器
    up_logger = LogManager.get_logger('uploader')
    
    # 全局启用FFmpeg过滤器
    LogManager.enable_ffmpeg_filter()
    
    # 下载模块使用进度条
    dl_logger.info("开始下载文件")
    progress_bar = dl_logger.create_progress_bar(
        id="download_progress", 
        total=10, 
        desc="下载媒体文件"
    )
    
    for i in range(10):
        # 模拟下载
        await asyncio.sleep(0.2)
        # 可以在下载过程中输出日志，不会影响进度条
        if i == 5:
            dl_logger.info("下载进行中，已完成一半")
        dl_logger.update_progress("download_progress", 1)
    
    dl_logger.close_progress_bar("download_progress")
    dl_logger.success("下载完成")
    
    # 上传模块使用进度条
    up_logger.info("开始上传文件")
    progress_bar = up_logger.create_progress_bar(
        id="upload_progress", 
        total=10, 
        desc="上传媒体文件"
    )
    
    for i in range(10):
        # 模拟上传
        await asyncio.sleep(0.3)
        # 可以在上传过程中输出日志，不会影响进度条
        if i == 3:
            up_logger.info("上传进行中，编码模式：高质量")
        up_logger.update_progress("upload_progress", 1)
    
    up_logger.close_progress_bar("upload_progress")
    up_logger.success("上传完成")
    
    # 输出FFmpeg过滤的示例
    up_logger.info("正在转码媒体文件...")
    # 这些FFmpeg日志会被过滤掉
    up_logger.info("frame=  100 fps=50.0 q=29.0 size=    128kB time=00:00:10.00 bitrate=104.9kbits/s speed=2.00x")
    up_logger.info("Press [q] to stop encoding")
    # 普通日志不会被过滤
    up_logger.info("转码完成")
    
    print("\n下载上传示例完成。")

if __name__ == "__main__":
    # 执行示例
    basic_logging_example()
    progress_bar_example()
    multiple_progress_bars_example()
    log_filter_example()
    ffmpeg_filter_example()
    
    # 异步示例需要使用事件循环运行
    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_upload_example()) 