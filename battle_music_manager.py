"""
Battle Music Manager
Handles voice channel music playback for battles with queue management.
"""

import asyncio
import discord
import yt_dlp
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
import random


class BattlePhase(Enum):
    """Music phases during battle"""
    BATTLE = "battle"
    VICTORY = "victory"


@dataclass
class MusicRequest:
    """Represents a music request for a battle"""
    battle_id: str
    user_id: int
    username: str
    voice_channel_id: int
    battle_type: str  # "npc", "pvp", "raid"
    generation: Optional[int] = None  # For NPC battles


class BattleMusicManager:
    """Manages music playback for battles with queue system"""

    def __init__(self, bot):
        self.bot = bot
        self.current_session: Optional[MusicRequest] = None
        self.queue: List[MusicRequest] = []
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_phase: Optional[BattlePhase] = None
        self.battle_theme_url: Optional[str] = None
        self.victory_theme_url: Optional[str] = None
        self._fade_task: Optional[asyncio.Task] = None

        # FFMPEG options for audio streaming
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=0.5"'
        }

        # yt-dlp options
        self.YDL_OPTIONS = {
            'format': 'bestaudio/best',
            'extractaudio': True,
            'audioformat': 'mp3',
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
        }

    async def request_music(self, battle_id: str, user_id: int, username: str,
                           voice_channel_id: int, battle_type: str,
                           generation: Optional[int] = None) -> Tuple[bool, str, int]:
        """
        Request music for a battle.

        Returns:
            Tuple of (can_start_immediately, message, queue_position)
        """
        request = MusicRequest(
            battle_id=battle_id,
            user_id=user_id,
            username=username,
            voice_channel_id=voice_channel_id,
            battle_type=battle_type,
            generation=generation
        )

        # Check if user already has an active session
        if self.current_session and self.current_session.user_id == user_id:
            return False, "You already have an active music session!", 0

        # Check if user is already in queue
        if any(req.user_id == user_id for req in self.queue):
            return False, "You're already in the music queue!", 0

        # If no current session, start immediately
        if self.current_session is None:
            self.current_session = request
            return True, "Music session starting!", 0

        # Otherwise, add to queue
        self.queue.append(request)
        position = len(self.queue)
        return False, f"Added to queue at position {position}", position

    async def start_battle_music(self, battle_theme_url: str, victory_theme_url: str) -> bool:
        """
        Start playing battle music for the current session.

        Args:
            battle_theme_url: YouTube URL for battle theme
            victory_theme_url: YouTube URL for victory theme

        Returns:
            True if music started successfully, False otherwise
        """
        if not self.current_session:
            return False

        self.battle_theme_url = battle_theme_url
        self.victory_theme_url = victory_theme_url

        # Get voice channel
        channel = self.bot.get_channel(self.current_session.voice_channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return False

        try:
            # Connect to voice channel
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect()

            # Start playing battle theme
            await self._play_theme(battle_theme_url, loop=True)
            self.current_phase = BattlePhase.BATTLE
            return True

        except Exception as e:
            print(f"Error starting battle music: {e}")
            return False

    async def play_victory_music(self):
        """Switch to victory music after battle ends"""
        if not self.current_session or not self.victory_theme_url:
            return

        self.current_phase = BattlePhase.VICTORY

        # Stop current music
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

        # Play victory theme (no loop, will fade out after 1 minute)
        await self._play_theme(self.victory_theme_url, loop=False)

        # Schedule fade out after 1 minute
        if self._fade_task:
            self._fade_task.cancel()
        self._fade_task = asyncio.create_task(self._fade_and_disconnect())

    async def _play_theme(self, url: str, loop: bool = False):
        """Play a theme from YouTube URL"""
        if not self.voice_client:
            return

        try:
            # Extract audio info
            with yt_dlp.YoutubeDL(self.YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']

            # Create audio source
            source = discord.FFmpegPCMAudio(audio_url, **self.FFMPEG_OPTIONS)

            # If looping, wrap in PCMVolumeTransformer for volume control
            if loop:
                source = discord.PCMVolumeTransformer(source, volume=0.5)

                def after_playing(error):
                    if error:
                        print(f"Player error: {error}")
                    # Replay if still in battle phase
                    if self.current_phase == BattlePhase.BATTLE and self.voice_client:
                        asyncio.run_coroutine_threadsafe(
                            self._play_theme(url, loop=True),
                            self.bot.loop
                        )

                self.voice_client.play(source, after=after_playing)
            else:
                source = discord.PCMVolumeTransformer(source, volume=0.5)
                self.voice_client.play(source)

        except Exception as e:
            print(f"Error playing theme: {e}")

    async def _fade_and_disconnect(self):
        """Fade out music over 60 seconds and disconnect"""
        try:
            await asyncio.sleep(60)  # Play for 1 minute

            # Fade out over 5 seconds
            if self.voice_client and self.voice_client.source:
                initial_volume = self.voice_client.source.volume
                steps = 50
                for i in range(steps):
                    if self.voice_client and self.voice_client.source:
                        self.voice_client.source.volume = initial_volume * (1 - i / steps)
                        await asyncio.sleep(0.1)

            # Disconnect and move to next in queue
            await self._end_session()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error during fade: {e}")

    async def _end_session(self):
        """End current session and start next in queue"""
        # Disconnect from voice
        if self.voice_client:
            try:
                await self.voice_client.disconnect()
            except:
                pass
            self.voice_client = None

        # Clear current session
        self.current_session = None
        self.current_phase = None
        self.battle_theme_url = None
        self.victory_theme_url = None

        # Start next in queue
        if self.queue:
            next_request = self.queue.pop(0)
            self.current_session = next_request
            # Note: The battle system will need to call start_battle_music() for the next session

    async def cancel_session(self, battle_id: str):
        """Cancel a music session (if battle is cancelled)"""
        # If it's the current session
        if self.current_session and self.current_session.battle_id == battle_id:
            if self._fade_task:
                self._fade_task.cancel()
            await self._end_session()
            return True

        # If it's in the queue
        for i, req in enumerate(self.queue):
            if req.battle_id == battle_id:
                self.queue.pop(i)
                return True

        return False

    def get_queue_display(self) -> List[Dict]:
        """Get queue information for display"""
        queue_data = []

        if self.current_session:
            queue_data.append({
                'position': 0,
                'username': self.current_session.username,
                'battle_type': self.current_session.battle_type,
                'status': 'active'
            })

        for i, req in enumerate(self.queue, 1):
            queue_data.append({
                'position': i,
                'username': req.username,
                'battle_type': req.battle_type,
                'status': 'queued'
            })

        return queue_data

    def is_user_in_queue(self, user_id: int) -> bool:
        """Check if user is currently using or waiting for music"""
        if self.current_session and self.current_session.user_id == user_id:
            return True
        return any(req.user_id == user_id for req in self.queue)

    def get_user_position(self, user_id: int) -> Optional[int]:
        """Get user's position in queue (0 = active, 1+ = waiting)"""
        if self.current_session and self.current_session.user_id == user_id:
            return 0

        for i, req in enumerate(self.queue, 1):
            if req.user_id == user_id:
                return i

        return None
