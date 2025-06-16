import logging
import os
import asyncio
import yt_dlp as youtube_dl
from typing import Optional, Dict, List, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
    ContextTypes
)

# ������������ (����������� ���������� ��������� � production!)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '���  �����')
TELEGRAM_MAX_SIZE = 50 * 1024 * 1024  # 50MB - ����� Telegram
COMPRESSED_QUALITY = '480p'  # �������� ��� ������
MAX_DURATION = 15 * 60  # 15 ����� ��������

# ��������� �����������
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VideoDownloaderBot:
    def __init__(self):
        self.user_data: Dict[int, Dict[str, Any]] = {}
        self.app = None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """���������� ������� /start"""
        user = update.effective_user
        await update.message.reply_text(
            f"������, {user.first_name}!\n\n"
            "������� ��� ������ �� ����� ��:\n"
            "- YouTube\n- Instagram\n- TikTok\n\n"
            "� ������ ��� � �������� ������� ��������!"
        )

    def get_quality_keyboard(self, formats: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        """���������� � ���������� ��������"""
        buttons = []
        for fmt in formats[:5]:
            res = fmt.get('height', '?')
            ext = fmt.get('ext', 'mp4')
            buttons.append([InlineKeyboardButton(
                f"{res}p ({ext})", 
                callback_data=f"quality_{fmt['format_id']}"
            )])
        buttons.append([InlineKeyboardButton(
            "? ����������� ��������", 
            callback_data="quality_best"
        )])
        return InlineKeyboardMarkup(buttons)

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """��������� ���������� � �����"""
        ydl_opts = {'quiet': True, 'no_warnings': True}
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"Video info error: {e}")
            return None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """���������� ��������� � ��������"""
        text = update.message.text.strip()
        user_id = update.message.from_user.id
        
        if not any(d in text for d in ['youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com']):
            await update.message.reply_text("��������� ������ �� ����� � YouTube, Instagram ��� TikTok")
            return

        await update.message.reply_text("?? ���������� ������...")
        info = await self.get_video_info(text)
        
        if not info:
            await update.message.reply_text("? �� ������� �������� ���������� � �����")
            return

        formats = info.get('formats', [])
        video_formats = [f for f in formats if f.get('vcodec') != 'none']
        
        if not video_formats:
            await update.message.reply_text("? ����� ���������� ��� ����������")
            return

        self.user_data[user_id] = {'url': text}
        await update.message.reply_text(
            "�������� ��������:",
            reply_markup=self.get_quality_keyboard(video_formats)
        )

    async def download_video(self, url: str, quality: str) -> Optional[str]:
        """�������� ����� � ��������� ���������"""
        ydl_opts = {
            'format': quality,
            'outtmpl': 'video.%(ext)s',
            'quiet': True,
            'max_filesize': TELEGRAM_MAX_SIZE
        }
        
        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                for f in os.listdir():
                    if f.startswith('video.'):
                        return f
        except Exception as e:
            logger.error(f"Download error: {e}")
        return None

    async def quality_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """���������� ������ ��������"""
        query = update.callback_query
        await query.answer()
        
        quality = query.data.replace('quality_', '')
        user_id = query.from_user.id
        url = self.user_data.get(user_id, {}).get('url')
        
        if not url:
            await query.edit_message_text("? ������ ��������, ��������� ������ �����")
            return

        await query.edit_message_text("? �������� �����...")
        
        try:
            video_path = await self.download_video(url, 'best' if quality == 'best' else quality)
            if not video_path:
                await query.edit_message_text("? ������ ��������")
                return

            if os.path.getsize(video_path) > TELEGRAM_MAX_SIZE:
                await query.edit_message_text("? ����� ������� ������� (����. 50MB)")
                os.remove(video_path)
                return

            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=video_file,
                    supports_streaming=True
                )
            os.remove(video_path)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await query.edit_message_text("? ��������� ������")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """���������� ���������� ������"""
        logger.error("Exception:", exc_info=context.error)

    def run(self):
        """������ ����"""
        self.app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # ����������� ������������
        handlers = [
            CommandHandler("start", self.start),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message),
            CallbackQueryHandler(self.quality_handler, pattern="^quality_")
        ]
        
        for handler in handlers:
            self.app.add_handler(handler)
        
        self.app.add_error_handler(self.error_handler)
        
        # ������ ����
        logger.info("��� �������")
        self.app.run_polling()

if __name__ == '__main__':
    bot = VideoDownloaderBot()
    bot.run()