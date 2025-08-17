from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
from pkg.platform.types import *  # 导入所有消息类型
import re
import json
import os


# 注册插件
@register(name="MdToImage", description="将AI回复中的Markdown图片转换为图片消息发送", version="0.1.0", author="yumo")
class MdToImage(BasePlugin):
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
        # 从插件目录下的 config.json 读取 base_url
        self.base_url: str = self._load_base_url_from_config()

    def _load_base_url_from_config(self) -> str:
        """从同目录的 config.json 读取 base_url 配置。

        读取顺序：
        - 优先从 plugins/ToImage/config.json 读取 base_url 字段；
        - 如果文件不存在、解析失败或字段缺失/为空，返回空字符串（表示未配置）。

        Returns:
            str: 读取到的 base_url（可能为空字符串表示未配置）。
        """
        current_dir = os.path.dirname(__file__)
        config_path = os.path.join(current_dir, 'config.json')
        try:
            if not os.path.exists(config_path):
                return ""
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                base_url = (data.get('base_url') or '').strip()
                return base_url.rstrip('/') if base_url else ""
        except Exception:
            # 读取失败即视为未配置
            return ""

    async def initialize(self):
        """插件的异步初始化方法。
        用于在插件加载后进行异步资源初始化，例如网络连接、缓存预热等。
        """
        pass

    def normalize_image_url(self, url: str) -> str:
        """将图片URL标准化。

        功能：
        - 若已是 http/https 或 data URI，则原样返回；
        - 若以 "/" 开头（相对路径，如 /api/system/img/...），自动补齐为 base_url + 相对路径；
        - 其他情况维持原样。

        Args:
            url (str): 图片原始URL。

        Returns:
            str: 处理后的完整URL。
        """
        try:
            if not url:
                return url
            lower = url.lower()
            if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("data:"):
                return url
            if url.startswith("/"):
                # 补齐前缀
                return self.base_url.rstrip("/") + url
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
        # 匹配Markdown图片格式：![描述](URL)
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
        1. 如果回复内容包含Markdown格式的图片（![]()），则直接使用Image(url=...)按原顺序与文本一起构建消息链；
        2. 当图片URL是相对路径且 base_url 未配置时，保持原消息不改写（直接返回）。
        3. 不再处理任何与“hello”或“测试”相关的逻辑。

        Args:
            ctx (EventContext): 事件上下文，包含AI响应文本等信息。
        """
        try:
            resp_text = ctx.event.response_text or ""

            # 仅处理 Markdown 图片
            img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
            if re.search(img_pattern, resp_text):
                # 如果存在相对URL且未配置 base_url，则不改写原消息
                # 判定相对URL：不以 http(s):// 或 data: 开头
                urls = [m.group(2).strip() for m in re.finditer(img_pattern, resp_text)]
                has_relative = any(not (u.lower().startswith('http://') or u.lower().startswith('https://') or u.lower().startswith('data:')) for u in urls)
                if has_relative and not self.base_url:
                    # 未配置 base_url，保持原消息
                    return

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
