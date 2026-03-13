"""
Battle Music Manager
Handles voice channel music playback for battles with queue management.
"""

import asyncio
import discord
import yt_dlp
import os
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum
import random
import shutil
from battle_themes import CASUAL_NPC_THEMES, RANKED_NPC_THEMES


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
        self.session_queue: List[Dict[str, Optional[str]]] = []
        self.session_history: List[Dict[str, Optional[str]]] = []
        self.session_current_track: Optional[Dict[str, Optional[str]]] = None
        self.session_loop: bool = False
        self.session_voice_channel_id: Optional[int] = None
        self.session_override_active: bool = False
        self.music_cache_dir = Path(os.getenv("MUSIC_CACHE_DIR", "data/music_cache"))
        self.music_cache_dir.mkdir(parents=True, exist_ok=True)

        # Check if FFmpeg is available
        if not shutil.which('ffmpeg'):
            print("⚠️ WARNING: FFmpeg not found! Music playback will not work.")
            print("   Install FFmpeg: https://ffmpeg.org/download.html")
        else:
            print("✅ FFmpeg found, music system ready")

        # FFMPEG options for high-quality audio streaming
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            # Force 48k stereo PCM out of FFmpeg to keep Discord voice quality high
            'options': '-vn -ac 2 -ar 48000 -b:a 320k'
        }

        # yt-dlp options optimized for high-quality Discord streaming
        self.YDL_OPTIONS = {
            'format': 'bestaudio/best',  # Avoid over-constraining formats; let FFmpeg normalize to 48k
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
            # Try multiple client profiles; this can reduce YouTube bot checks
            # for some public videos without requiring user auth.
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'ios']
                }
            },
        }

        self._configure_ytdlp_auth()

    def _configure_ytdlp_auth(self):
        """Apply optional yt-dlp authentication settings from environment variables."""
        cookies_file = (os.getenv("YTDLP_COOKIES_FILE") or "").strip()
        browser_spec = (os.getenv("YTDLP_COOKIES_FROM_BROWSER") or "").strip()

        # 1) Prefer cookie file only when it is a real, readable file.
        if cookies_file:
            cookie_path = Path(cookies_file).expanduser()
            if cookie_path.is_file():
                self.YDL_OPTIONS['cookiefile'] = str(cookie_path)
                print(f"🍪 yt-dlp using cookie file: {cookie_path}")
                return
            print(f"⚠️ YTDLP_COOKIES_FILE is set but file was not found: {cookie_path}")

        # 2) Fallback to browser cookies when specified.
        if browser_spec:
            # Accept values like:
            #   chrome
            #   firefox:default-release
            #   chromium:Default
            parts = [part.strip() for part in browser_spec.split(':') if part.strip()]
            if parts:
                self.YDL_OPTIONS['cookiesfrombrowser'] = tuple(parts)
                print(f"🍪 yt-dlp loading cookies from browser: {browser_spec}")
                return

        print("ℹ️ yt-dlp running without cookies (public videos only).")


    def _candidate_battle_theme_urls(self, exclude_url: str) -> List[str]:
        """Build a shuffled list of alternate battle theme URLs excluding the current URL."""
        all_urls = [battle for battle, _ in (CASUAL_NPC_THEMES + RANKED_NPC_THEMES)]
        deduped = list(dict.fromkeys(all_urls))
        candidates = [url for url in deduped if url != exclude_url]
        random.shuffle(candidates)
        return candidates

    def _get_optimal_bitrate(self, guild: discord.Guild) -> int:
        """
        Determine the optimal audio bitrate based on server boost level.

        Discord bitrate limits:
        - No boost: 96 kbps
        - Boost Level 1: 128 kbps
        - Boost Level 2: 256 kbps
        - Boost Level 3: 384 kbps

        Returns bitrate in bits per second (bps) for the encoder.
        """
        if not guild:
            return 96000  # Default to 96 kbps

        boost_level = guild.premium_tier
        bitrate_map = {
            0: 96000,   # 96 kbps - no boost
            1: 128000,  # 128 kbps - boost level 1
            2: 256000,  # 256 kbps - boost level 2
            3: 384000,  # 384 kbps - boost level 3
        }

        bitrate = bitrate_map.get(boost_level, 96000)
        print(f"🎵 Server boost level {boost_level}: using {bitrate // 1000} kbps bitrate")
        return bitrate

    async def _configure_voice_quality(self, voice_client: discord.VoiceClient, guild: discord.Guild):
        """
        Configure voice client for optimal audio quality based on server capabilities.
        """
        if not voice_client or not voice_client.is_connected():
            return

        try:
            optimal_bitrate = self._get_optimal_bitrate(guild)

            # Configure the Opus encoder for high-quality audio
            if hasattr(voice_client, 'encoder') and voice_client.encoder:
                voice_client.encoder.set_bitrate(optimal_bitrate)
                print(f"✅ Voice encoder configured to {optimal_bitrate // 1000} kbps")
        except Exception as e:
            print(f"⚠️ Could not configure voice quality: {e}")
            # Continue anyway - will use default settings

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

        if self.session_override_active:
            print("⚠️ Session music override active; skipping battle music.")
            return False

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

            # Configure optimal audio quality based on server boost level
            await self._configure_voice_quality(self.voice_client, channel.guild)

            # Start playing battle theme
            print(f"▶️ Starting battle theme playback...")
            started = await self._play_theme(battle_theme_url, loop=True)

            if not started:
                print("⚠️ Primary battle theme failed; trying fallback theme URLs...")
                for fallback_url in self._candidate_battle_theme_urls(battle_theme_url)[:8]:
                    started = await self._play_theme(fallback_url, loop=True)
                    if started:
                        self.battle_theme_url = fallback_url
                        print(f"✅ Fallback battle theme started: {fallback_url}")
                        break

            if not started:
                print("❌ Could not start any battle theme URL.")
                return False

            self.current_phase = BattlePhase.BATTLE
            print(f"✅ Battle music started successfully!")
            return True

        except Exception as e:
            print(f"❌ Error starting battle music: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def queue_session_track(self, voice_channel_id: int, url: str) -> int:
        """Queue a track for session music playback."""
        track = {"url": url, "title": None}
        self.session_queue.append(track)
        if not self.session_voice_channel_id:
            self.session_voice_channel_id = voice_channel_id
        if not self.session_current_track:
            await self._start_next_session_track()
        return len(self.session_queue)

    async def skip_session_next(self) -> bool:
        """Skip to the next track in the session queue."""
        if not self.session_queue:
            # No more tracks - stop current track but stay connected
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
            if self.session_current_track:
                self.session_history.append(self.session_current_track)
            self.session_current_track = None
            return False
        if self.session_current_track:
            self.session_history.append(self.session_current_track)
        await self._start_next_session_track()
        return True

    async def skip_session_previous(self) -> bool:
        """Return to the previous track in the session history."""
        if not self.session_history:
            return False
        if self.session_current_track:
            self.session_queue.insert(0, self.session_current_track)
        self.session_current_track = self.session_history.pop()
        await self._play_session_track(self.session_current_track)
        return True

    def toggle_session_loop(self) -> bool:
        """Toggle looping for the current session track."""
        self.session_loop = not self.session_loop
        return self.session_loop

    def remove_session_track(self, index: int) -> bool:
        """
        Remove a track from the session queue by index.

        Args:
            index: The 0-based index of the track to remove

        Returns:
            True if track was removed, False if index was invalid
        """
        if 0 <= index < len(self.session_queue):
            self.session_queue.pop(index)
            return True
        return False

    def get_session_queue_status(self) -> Dict[str, Optional[str]]:
        """Get current session music status for display."""
        current_title = None
        if self.session_current_track:
            current_title = self.session_current_track.get("title") or self.session_current_track.get("url")
        return {
            "current": current_title,
            "queue": [
                track.get("title") or track.get("url") for track in self.session_queue
            ],
            "loop": self.session_loop,
            "active": self.session_override_active
        }

    async def _start_next_session_track(self):
        if not self.session_queue:
            # Don't disconnect - just clear current track and wait for more tracks
            # The bot will stay in VC as long as the session is active
            self.session_current_track = None
            return
        self.session_current_track = self.session_queue.pop(0)
        await self._play_session_track(self.session_current_track)

    async def _play_session_track(self, track: Dict[str, Optional[str]]):
        """Play a queued session track and advance as needed."""
        url = track.get("url")
        if not url:
            return

        if not self.session_voice_channel_id:
            return

        channel = self.bot.get_channel(self.session_voice_channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            print(f"❌ Session voice channel not found: {self.session_voice_channel_id}")
            return

        try:
            self.session_override_active = True
            self.current_phase = None

            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect()

            # Configure optimal audio quality based on server boost level
            await self._configure_voice_quality(self.voice_client, channel.guild)

            if self.voice_client.is_playing():
                self.voice_client.stop()

            audio_input, _, title = await self._resolve_audio_input(url)
            if not audio_input:
                print(f"❌ Could not resolve audio for session track")
                return

            track["title"] = title or track.get("url")

            source = discord.FFmpegPCMAudio(audio_input, **self.FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)

            def after_playing(error):
                if error:
                    print(f"❌ Session music error: {error}")
                if self.session_loop and self.session_current_track:
                    asyncio.run_coroutine_threadsafe(
                        self._play_session_track(self.session_current_track),
                        self.bot.loop
                    )
                    return
                asyncio.run_coroutine_threadsafe(
                    self._start_next_session_track(),
                    self.bot.loop
                )

            self.voice_client.play(source, after=after_playing)

        except yt_dlp.utils.DownloadError as e:
            print(f"❌ Error playing session track: {e}")
            if "not a bot" in str(e).lower():
                print("💡 YouTube requested auth. Set YTDLP_COOKIES_FILE or YTDLP_COOKIES_FROM_BROWSER in your .env.")
        except Exception as e:
            print(f"❌ Error playing session track: {e}")
            import traceback
            traceback.print_exc()

    async def _stop_session_music(self):
        """Stop session music and clear override state."""
        self.session_override_active = False
        self.session_current_track = None
        self.session_queue = []
        self.session_history = []
        self.session_loop = False
        self.session_voice_channel_id = None
        if self.voice_client:
            if self.voice_client.is_playing():
                self.voice_client.stop()
            try:
                await self.voice_client.disconnect()
            except Exception:
                pass
            self.voice_client = None

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

    async def play_switch_sound(self, species_dex_number: int) -> None:
        """No-op: sound effects are disabled; music only."""
        return

    async def _play_theme(self, url: str, loop: bool = False, disconnect_after: bool = False) -> bool:
        """Play a theme from YouTube URL. Returns True if playback started."""
        if not self.voice_client:
            print("❌ No voice client available")
            return False

        if not self.voice_client.is_connected():
            print("❌ Voice client not connected")
            return False

        # Stop any currently playing audio
        if self.voice_client.is_playing():
            print("⏹️ Stopping current audio...")
            self.voice_client.stop()

        # Cancel any existing fade task
        if self._fade_task:
            self._fade_task.cancel()
            self._fade_task = None

        try:
            print(f"🎵 Resolving audio from: {url}")

            audio_input, duration, _ = await self._resolve_audio_input(url)
            if not audio_input:
                print(f"❌ Could not resolve playable audio input")
                return False
            print(f"🎵 Track duration: {duration} seconds")

            print(f"🎵 Creating FFmpeg audio source...")
            # Create audio source with PCMVolumeTransformer for volume control
            source = discord.FFmpegPCMAudio(audio_input, **self.FFMPEG_OPTIONS)
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

            # If this is a victory theme and it's longer than 2 minutes, fade out after 2 minutes
            if disconnect_after and duration > 120:
                print(f"🎵 Victory theme is {duration}s long, will fade out after 2 minutes")
                self._fade_task = asyncio.create_task(self._fade_victory_theme())

            # Verify playback started
            if self.voice_client.is_playing():
                print(f"✅ Playback confirmed!")
                return True
            print(f"⚠️ Voice client shows not playing after play() call")
            return False

        except yt_dlp.utils.DownloadError as e:
            print(f"❌ Error playing theme: {e}")
            if "not a bot" in str(e).lower():
                print("💡 YouTube requested auth. Set YTDLP_COOKIES_FILE or YTDLP_COOKIES_FROM_BROWSER in your .env.")
            return False
        except Exception as e:
            print(f"❌ Error playing theme: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _resolve_audio_input(self, url: str) -> Tuple[Optional[str], int, Optional[str]]:
        """
        Resolve a playable FFmpeg input using yt-dlp.

        Returns:
            (audio_input, duration_seconds, title)
        """
        def _extract(ydl_options: Dict) -> Optional[Dict]:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(_extract, self.YDL_OPTIONS)
        except yt_dlp.utils.DownloadError as e:
            # Some videos do not expose a 48k-tagged audio stream even though they are playable.
            # Retry with a very permissive format selector before giving up.
            if "Requested format is not available" not in str(e):
                raise

            print("⚠️ Preferred yt-dlp format unavailable, retrying with fallback selector...")
            fallback_options = dict(self.YDL_OPTIONS)
            fallback_options['format'] = 'bestaudio/best'
            info = await asyncio.to_thread(_extract, fallback_options)

        if not info:
            return None, 0, None

        # Handle playlist/search responses by selecting the first real entry.
        if 'entries' in info and info['entries']:
            info = next((entry for entry in info['entries'] if entry), None)
            if not info:
                return None, 0, None

        audio_input = info.get('url')
        if not audio_input:
            return None, 0, info.get('title')

        return audio_input, info.get('duration', 0) or 0, info.get('title')

    async def _fade_victory_theme(self):
        """Fade out victory theme after 2 minutes of playback"""
        try:
            await asyncio.sleep(120)  # Play for 2 minutes

            # Fade out over 5 seconds
            if self.voice_client and self.voice_client.source:
                print("🎵 Fading out victory theme after 2 minutes...")
                initial_volume = self.voice_client.source.volume
                steps = 50
                for i in range(steps):
                    if self.voice_client and self.voice_client.source:
                        self.voice_client.source.volume = initial_volume * (1 - i / steps)
                        await asyncio.sleep(0.1)

            # Stop playback and disconnect
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()

            print("🎵 Victory theme faded out, disconnecting...")
            await self._end_session()

        except asyncio.CancelledError:
            print("🎵 Victory theme fade cancelled")
            pass
        except Exception as e:
            print(f"❌ Error during victory theme fade: {e}")

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
