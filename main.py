from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
from pkg.platform.types import *  # 导入所有消息类型
import re


# 注册插件
@register(name="ToImage", description="将AI回复中的Markdown图片转换为图片消息发送", version="0.1", author="yumo")
class ToImagePlugin(BasePlugin):
    """ToImage 插件

    功能：
    - 拦截 AI 的文本回复，解析其中的 Markdown 图片（![]()），并直接以 Image(url=...) 的方式构建消息链发送。
    - 不处理任何 "hello" 相关逻辑，也不再处理包含“测试”的特殊回复逻辑。
    """

    def __init__(self, host: APIHost):
        """插件构造函数。
        初始化插件所需的资源或状态。

        Args:
            host (APIHost): 插件宿主对象。
        """
        # 调用父类初始化，确保宿主对象等正确注入
        super().__init__(host)
        # base_url 不设默认值，仅在 initialize 中从配置读取
        # self.base_url 将在 initialize 中按需设置

    async def initialize(self):
        """插件的异步初始化方法。
        用于在插件加载后进行异步资源初始化，例如网络连接、缓存预热等。
        同时在此阶段从插件配置（manifest 注入）中读取 base_url（如未配置则不设置）。
        """
        try:
            cfg = self.config or {}
            cfg_base_url = str(cfg.get("base_url", "")).strip()
            if cfg_base_url:
                # 去除末尾斜杠，避免拼接出现重复 //
                self.base_url = cfg_base_url.rstrip("/")
                if hasattr(self, 'ap') and hasattr(self.ap, 'logger'):
                    self.ap.logger.debug(f"ToImagePlugin 已应用配置 base_url={self.base_url}")
        except Exception as e:
            # 不中断主流程，记录日志以便排查
            if hasattr(self, 'ap') and hasattr(self.ap, 'logger'):
                self.ap.logger.error(f"ToImagePlugin.initialize 读取配置失败: {e}")

    def normalize_image_url(self, url: str) -> str:
        """将图片URL标准化。

        功能：
        - 若已是 http/https 或 data URI，则原样返回；
        - 若以 "/" 开头（相对路径，如 /api/system/img/...），且已配置 base_url，则自动补齐为 base_url + 相对路径；
        - 未配置 base_url 时不做补齐；
        - 其他情况维持原样。

        Args:
            url (str): 图片原始URL。

        Returns:
            str: 处理后的完整URL（或原URL）。
        """
        try:
            if not url:
                return url
            lower = url.lower()
            if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("data:"):
                return url
            if url.startswith("/"):
                # 仅在已配置 base_url 时进行补齐
                base = getattr(self, 'base_url', '').strip()
                if base:
                    return base.rstrip("/") + url
                return url
            return url
        except Exception:
            # 失败时不阻断流程，直接返回原URL
            return url

    def parse_markdown_content(self, text: str):
        """解析包含Markdown图片的文本，返回文本片段和图片URL的有序列表。

        支持的图片格式：![]()，例如：这是文本![描述](https://example.com/1.png)继续文本。
        会将文本拆分为若干段：文本段使用 Plain，图片段直接使用 Image(url=...)，并保持原顺序组合。

        Args:
            text (str): 包含Markdown格式图片的文本。

        Returns:
            list: 有序列表，元素为{"type": "text", "content": str}或{"type": "image", "alt": str, "url": str}。
        """
        # 匹配Markdown图片格式：![]()
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

        result = []
        last_end = 0

        for match in re.finditer(pattern, text):
            # 添加图片前的文本
            if match.start() > last_end:
                text_before = text[last_end:match.start()]
                if text_before.strip():
                    result.append({"type": "text", "content": text_before})

            # 添加图片信息
            alt_text = match.group(1)
            image_url = self.normalize_image_url(match.group(2))
            result.append({"type": "image", "alt": alt_text, "url": image_url})

            last_end = match.end()

        # 添加最后剩余的文本
        if last_end < len(text):
            remaining_text = text[last_end:]
            if remaining_text.strip():
                result.append({"type": "text", "content": remaining_text})

        return result

    @handler(NormalMessageResponded)
    async def normal_message_responded(self, ctx: EventContext):
        """拦截并修改 AI 即将发送的普通文本回复。

        功能：
        1. 如果回复内容包含Markdown格式的图片（![]()），则直接使用Image(url=...)按原顺序与文本一起构建消息链。
        2. 不再处理任何与“hello”或“测试”相关的逻辑。

        Args:
            ctx (EventContext): 事件上下文，包含AI响应文本等信息。
        """
        try:
            resp_text = ctx.event.response_text or ""

            # 仅处理 Markdown 图片
            if re.search(r'!\[([^\]]*)\]\(([^)]+)\)', resp_text):
                parsed_content = self.parse_markdown_content(resp_text)
                message_components = []

                for item in parsed_content:
                    if item["type"] == "text":
                        message_components.append(Plain(item["content"]))
                    elif item["type"] == "image":
                        # 直接使用URL，让平台适配器处理图片下载
                        message_components.append(Image(url=item["url"]))

                if message_components:
                    ctx.event.reply = message_components
                    return

        except Exception as e:
            # 不中断主流程，记录日志以便排查
            if hasattr(self, 'ap') and hasattr(self.ap, 'logger'):
                self.ap.logger.error(f"ToImagePlugin.normal_message_responded 处理异常: {e}")

    def __del__(self):
        """插件析构函数，释放资源（如果有）。"""
        pass
