"""
自定义异常类定义
定义应用中使用的各种异常类型
"""


class ConfigError(Exception):
    """配置错误异常"""
    pass


class ClientError(Exception):
    """客户端错误异常"""
    pass


class DownloadError(Exception):
    """下载错误异常"""
    pass


class UploadError(Exception):
    """上传错误异常"""
    pass


class ForwardError(Exception):
    """转发错误异常"""
    pass


class StorageError(Exception):
    """存储错误异常"""
    pass


class ChannelParseError(Exception):
    """频道解析错误异常"""
    pass 