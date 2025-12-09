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
import shutil


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
        self.volume: float = 0.8  # Audio volume (0.0 to 1.0)

        # Check if FFmpeg is available
        if not shutil.which('ffmpeg'):
            print("⚠️ WARNING: FFmpeg not found! Music playback will not work.")
            print("   Install FFmpeg: https://ffmpeg.org/download.html")
        else:
            print("✅ FFmpeg found, music system ready")

        # FFMPEG options for high-quality audio streaming
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -b:a 192k'  # High bitrate for better quality
        }

        # yt-dlp options optimized for high-quality Discord streaming
        self.YDL_OPTIONS = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',  # Prefer high-quality formats
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'extract_flat': False,
            'skip_download': True,
            'prefer_ffmpeg': True,
            'keepvideo': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'best',
            }],
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
        print(f"🎵 start_battle_music called")
        print(f"   Battle theme: {battle_theme_url}")
        print(f"   Victory theme: {victory_theme_url}")

        if not self.current_session:
            print(f"❌ No current session!")
            return False

        print(f"✅ Current session found for user {self.current_session.username}")

        self.battle_theme_url = battle_theme_url
        self.victory_theme_url = victory_theme_url

        # Get voice channel
        channel = self.bot.get_channel(self.current_session.voice_channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            print(f"❌ Voice channel not found or invalid: {self.current_session.voice_channel_id}")
            return False

        print(f"✅ Voice channel found: {channel.name}")

        try:
            # Connect to voice channel
            if self.voice_client and self.voice_client.is_connected():
                print(f"🔄 Moving to voice channel...")
                await self.voice_client.move_to(channel)
            else:
                print(f"🔌 Connecting to voice channel...")
                self.voice_client = await channel.connect()

            print(f"✅ Connected to voice channel!")

            # Start playing battle theme
            print(f"▶️ Starting battle theme playback...")
            await self._play_theme(battle_theme_url, loop=True)
            self.current_phase = BattlePhase.BATTLE
            print(f"✅ Battle music started successfully!")
            return True

        except Exception as e:
            print(f"❌ Error starting battle music: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def play_victory_music(self):
        """Switch to victory music after battle ends"""
        if not self.current_session or not self.victory_theme_url:
            return

        self.current_phase = BattlePhase.VICTORY

        # Stop current music
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

        # Play victory theme (no loop, will disconnect when song ends)
        await self._play_theme(self.victory_theme_url, loop=False, disconnect_after=True)

    async def _play_theme(self, url: str, loop: bool = False, disconnect_after: bool = False):
        """Play a theme from YouTube URL"""
        if not self.voice_client:
            print("❌ No voice client available")
            return

        if not self.voice_client.is_connected():
            print("❌ Voice client not connected")
            return

        # Stop any currently playing audio
        if self.voice_client.is_playing():
            print("⏹️ Stopping current audio...")
            self.voice_client.stop()

        try:
            print(f"🎵 Extracting audio from: {url}")

            # Extract audio info using yt-dlp (run in executor to avoid blocking)
            event_loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(self.YDL_OPTIONS) as ydl:
                info = await event_loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))

            if 'url' not in info:
                print(f"❌ No audio URL found in video info")
                return

            audio_url = info['url']
            print(f"✅ Audio URL extracted: {audio_url[:100]}...")

            print(f"🎵 Creating FFmpeg audio source...")
            # Create audio source with PCMVolumeTransformer for volume control
            source = discord.FFmpegPCMAudio(audio_url, **self.FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)
            print(f"✅ FFmpeg source created with volume control (volume={self.volume})")

            # Define callback for when audio finishes
            def after_playing(error):
                if error:
                    print(f"❌ Player error: {error}")
                else:
                    print(f"🎵 Track finished")

                # Replay if still in battle phase and looping
                if loop and self.current_phase == BattlePhase.BATTLE and self.voice_client:
                    print(f"🔁 Replaying battle theme...")
                    asyncio.run_coroutine_threadsafe(
                        self._play_theme(url, loop=True),
                        self.bot.loop
                    )
                # Disconnect after victory theme ends
                elif disconnect_after:
                    print(f"🎵 Victory theme ended, disconnecting...")
                    asyncio.run_coroutine_threadsafe(
                        self._end_session(),
                        self.bot.loop
                    )

            print(f"▶️ Starting playback (loop={loop}, disconnect_after={disconnect_after})...")
            self.voice_client.play(source, after=after_playing)

            # Verify playback started
            if self.voice_client.is_playing():
                print(f"✅ Playback confirmed!")
            else:
                print(f"⚠️ Voice client shows not playing after play() call")

        except Exception as e:
            print(f"❌ Error playing theme: {e}")
            import traceback
            traceback.print_exc()

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
