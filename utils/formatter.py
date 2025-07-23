import logging
import re

from telegram.helpers import escape_markdown

from .config_manager import get_config


logger = logging.getLogger(__name__)


def escape_v2(text: str) -> str:
    """Escapes text for Telegram MarkdownV2."""
    if not text:
        return ""
    return escape_markdown(text, version=2)


def format_with_markdown_v2(text: str) -> str:
    """
    智能处理带有MarkdownV2格式的文本，保持格式化效果的同时进行转义。

    最终版本：完全避免递归，使用更简单的一次性处理方法。

    Args:
        text (str): 包含MarkdownV2格式标记的文本

    Returns:
        str: 正确转义的MarkdownV2格式文本
    """
    if not text:
        return ""

    try:
        result_text = text

        # 第一步：保护代码块（它们的内容不应该被转义）
        code_blocks = []
        code_pattern = r"`([^`]+)`"
        matches = list(re.finditer(code_pattern, result_text))

        for i, match in enumerate(reversed(matches)):
            placeholder = f"__CODE_BLOCK_{i}__"
            code_blocks.append((placeholder, match.group(0)))  # 保存整个代码块
            result_text = result_text[: match.start()] + placeholder + result_text[match.end() :]

        # 第二步：保护链接格式
        link_blocks = []
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        matches = list(re.finditer(link_pattern, result_text))

        for i, match in enumerate(reversed(matches)):
            placeholder = f"__LINK_BLOCK_{i}__"
            link_text = escape_v2(match.group(1))
            link_url = escape_v2(match.group(2))
            link_blocks.append((placeholder, f"[{link_text}]({link_url})"))
            result_text = result_text[: match.start()] + placeholder + result_text[match.end() :]

        # 第三步：处理其他格式标记（粗体、斜体、删除线、spoiler）
        formats = [
            (r"\*([^*]+)\*", lambda m: f"*{escape_v2(m.group(1))}*"),
            (r"(?<!\w)_([^_\s][^_]*[^_\s]|[^_\s])_(?!\w)", lambda m: f"_{escape_v2(m.group(1))}_"),
            (r"~([^~]+)~", lambda m: f"~{escape_v2(m.group(1))}~"),
            (r"\|\|([^|]+)\|\|", lambda m: f"||{escape_v2(m.group(1))}||"),
        ]

        format_blocks = []
        for i, (pattern, formatter) in enumerate(formats):
            matches = list(re.finditer(pattern, result_text))
            for j, match in enumerate(reversed(matches)):
                placeholder = f"__FORMAT_{i}_{j}__"
                formatted_content = formatter(match)
                format_blocks.append((placeholder, formatted_content))
                result_text = result_text[: match.start()] + placeholder + result_text[match.end() :]

        # 第四步：转义剩余的普通文本
        escaped_result = escape_v2(result_text)

        # 第五步：恢复所有保护的内容
        # 注意：要用转义后的占位符来替换，并且要先恢复内层的内容

        # 首先恢复代码块和链接（它们可能在格式块内容中）
        for placeholder, content in code_blocks:
            escaped_placeholder = escape_v2(placeholder)
            # 在主文本中替换
            escaped_result = escaped_result.replace(escaped_placeholder, content)
            # 在格式块内容中也替换
            for i, (fmt_placeholder, fmt_content) in enumerate(format_blocks):
                if escaped_placeholder in fmt_content:
                    format_blocks[i] = (fmt_placeholder, fmt_content.replace(escaped_placeholder, content))

        for placeholder, content in link_blocks:
            escaped_placeholder = escape_v2(placeholder)
            # 在主文本中替换
            escaped_result = escaped_result.replace(escaped_placeholder, content)
            # 在格式块内容中也替换
            for i, (fmt_placeholder, fmt_content) in enumerate(format_blocks):
                if escaped_placeholder in fmt_content:
                    format_blocks[i] = (fmt_placeholder, fmt_content.replace(escaped_placeholder, content))

        # 最后恢复格式块
        for placeholder, content in format_blocks:
            escaped_placeholder = escape_v2(placeholder)
            escaped_result = escaped_result.replace(escaped_placeholder, content)

        return escaped_result

    except Exception as e:
        logger.error(f"Error during markdown formatting: {e}", exc_info=True)
        return escape_v2(text)  # 降级到安全转义


def foldable_text_v2(body: str) -> str:
    """
    Formats text for MarkdownV2, applying folding if it exceeds the configured line threshold.

    这是 foldable_text_with_markdown_v2 的简化版本，用于纯文本内容。

    Args:
        body (str): The text to format (plain text, no markdown).

    Returns:
        str: A MarkdownV2 formatted string, potentially folded.
    """
    try:
        config = get_config()
        folding_threshold = config.folding_threshold

        body_lines = body.split("\n")

        if len(body_lines) > folding_threshold:
            if not body_lines:
                return ""

            escaped_lines = [escape_v2(line) for line in body_lines]

            first_line = f"**> {escaped_lines[0]}"
            following_lines = [f"> {line}" for line in escaped_lines[1:]]
            all_lines = [first_line, *following_lines]

            if all_lines:
                all_lines[-1] += "||"

            return "\n".join(all_lines)
        else:
            return escape_v2(body)

    except Exception as e:
        logger.error(f"Error during foldable text formatting: {e}", exc_info=True)
        return escape_v2(body)  # Fallback to safe escaped text


def foldable_text_with_markdown_v2(body: str) -> str:
    """
    格式化包含MarkdownV2格式的文本，支持基于行数的折叠功能。

    Args:
        body (str): 包含MarkdownV2格式标记的文本

    Returns:
        str: 正确格式化和可能折叠的MarkdownV2文本
    """
    try:
        config = get_config()
        folding_threshold = config.folding_threshold

        body_lines = body.split("\n")

        if len(body_lines) > folding_threshold:
            if not body_lines:
                return ""

            # 对每行进行智能格式化
            formatted_lines = [format_with_markdown_v2(line) for line in body_lines]

            first_line = f"**> {formatted_lines[0]}"
            following_lines = [f"> {line}" for line in formatted_lines[1:]]
            all_lines = [first_line, *following_lines]

            if all_lines:
                # 检查最后一行是否以spoiler结尾，避免冲突
                last_line = all_lines[-1]
                if last_line.endswith("||"):
                    # 如果最后一行已经以 || 结尾（spoiler格式），添加空格分隔
                    all_lines[-1] += " ||"
                else:
                    # 正常情况，直接添加折叠结束标记
                    all_lines[-1] += "||"

            return "\n".join(all_lines)
        else:
            return format_with_markdown_v2(body)

    except Exception as e:
        logger.error(f"Error during foldable markdown formatting: {e}", exc_info=True)
        return escape_v2(body)  # 降级到安全转义
