"""
Battle Sound Effects Manager
Handles Pokemon cries and battle sound effects alongside music.
"""

import asyncio
import discord
import os
from pathlib import Path
from typing import Optional, List, Callable
from pydub import AudioSegment
import tempfile


class BattleSoundEffects:
    """Manages battle sound effects and Pokemon cries"""

    CRIES_DIR = Path("cries")

    # Sound effect file paths
    POKEBALL_THROW = CRIES_DIR / "Ruby_003D.wav"
    SWITCH_SOUND = CRIES_DIR / "In-Battle_Recall_Switch_Alive.mp3.mpeg"
    FAINT_SOUND = CRIES_DIR / "In-Battle_Faint_No_Health_XY.mp3.mpeg"

    def __init__(self):
        """Initialize sound effects manager"""
        self._sound_cache = {}
        self._check_files()
        self._temp_files = []

    def _check_files(self):
        """Check if sound effects directory and files exist"""
        if not self.CRIES_DIR.exists():
            print(f"⚠️ WARNING: Cries directory not found at {self.CRIES_DIR}")
            print("   Sound effects will be disabled until files are added.")
            print(f"   Please create the '{self.CRIES_DIR}' directory and add:")
            print("   - Ruby_003D.wav (pokeball throw)")
            print("   - In-Battle_Recall_Switch_Alive.mp3.mpeg (switch sound)")
            print("   - In-Battle_Faint_No_Health_XY.mp3.mpeg (faint sound)")
            print("   - PV-INDEX_###.wav for each Pokemon (normal cries)")
            print("   - SAD_###.wav for each Pokemon (faint cries)")
            return

        # Check for required sound effect files
        required_files = [
            ("Pokeball throw", self.POKEBALL_THROW),
            ("Switch sound", self.SWITCH_SOUND),
            ("Faint sound", self.FAINT_SOUND)
        ]

        for name, file_path in required_files:
            if file_path.exists():
                print(f"✅ Found {name}: {file_path}")
            else:
                print(f"⚠️ Missing {name}: {file_path}")

    def _get_cry_path(self, dex_number: int, cry_type: str = "INDEX") -> Optional[Path]:
        """
        Get path to Pokemon cry file

        Args:
            dex_number: National Pokedex number
            cry_type: "INDEX" for normal cry, "SAD" for faint cry

        Returns:
            Path to cry file or None if not found
        """
        # Try different file extensions and naming patterns
        extensions = [".wav", ".mp3", ".ogg", ".mpeg"]

        # Different naming patterns to try
        if cry_type == "INDEX":
            patterns = [
                f"PLAY_PV_{dex_number:04d} [PV-INDEX]",  # PLAY_PV_0001 [PV-INDEX].wav
                f"PLAY_PV_{dex_number:04d}",              # PLAY_PV_0001.wav
                f"PV-INDEX_{dex_number:03d}",             # PV-INDEX_001.wav
                f"PV-INDEX_{dex_number:04d}",             # PV-INDEX_0001.wav
            ]
        else:  # SAD
            patterns = [
                f"PLAY_PV_{dex_number:04d} [SAD]",       # PLAY_PV_0001 [SAD].wav
                f"SAD_{dex_number:03d}",                  # SAD_001.wav
                f"SAD_{dex_number:04d}",                  # SAD_0001.wav
            ]

        for pattern in patterns:
            for ext in extensions:
                cry_file = self.CRIES_DIR / f"{pattern}{ext}"
                if cry_file.exists():
                    print(f"✅ Found cry: {cry_file.name}")
                    return cry_file

        # Try glob pattern as last resort
        if cry_type == "INDEX":
            glob_patterns = [f"*{dex_number:04d}*INDEX*", f"*{dex_number:03d}*INDEX*"]
        else:
            glob_patterns = [f"*{dex_number:04d}*SAD*", f"*{dex_number:03d}*SAD*"]

        for glob_pattern in glob_patterns:
            matches = list(self.CRIES_DIR.glob(glob_pattern))
            if matches:
                cry_file = matches[0]
                print(f"✅ Found cry via glob: {cry_file.name}")
                return cry_file

        print(f"⚠️ Cry not found for Pokemon #{dex_number:03d} (type: {cry_type})")
        return None

    def _load_audio(self, file_path: Path) -> Optional[AudioSegment]:
        """Load audio file using pydub"""
        if not file_path.exists():
            print(f"⚠️ Audio file not found: {file_path}")
            return None

        # Check cache
        cache_key = str(file_path)
        if cache_key in self._sound_cache:
            return self._sound_cache[cache_key]

        try:
            # Determine format from extension
            ext = file_path.suffix.lower()
            if ext == ".mpeg":
                audio = AudioSegment.from_file(str(file_path), format="mp3")
            elif ext == ".wav":
                audio = AudioSegment.from_wav(str(file_path))
            elif ext == ".mp3":
                audio = AudioSegment.from_mp3(str(file_path))
            elif ext == ".ogg":
                audio = AudioSegment.from_ogg(str(file_path))
            else:
                audio = AudioSegment.from_file(str(file_path))

            # Cache it
            self._sound_cache[cache_key] = audio
            print(f"✅ Loaded audio: {file_path.name} ({len(audio)}ms)")
            return audio

        except Exception as e:
            print(f"❌ Error loading audio file {file_path}: {e}")
            return None

    def _create_sound_sequence(self, sounds: List[AudioSegment], pauses: List[int] = None) -> Optional[AudioSegment]:
        """
        Create a sequence of sounds with optional pauses between them

        Args:
            sounds: List of AudioSegment objects to play in sequence
            pauses: List of pause durations in milliseconds (one less than sounds count)

        Returns:
            Combined AudioSegment or None
        """
        if not sounds:
            return None

        if pauses is None:
            pauses = [0] * (len(sounds) - 1)

        result = sounds[0]
        for i, sound in enumerate(sounds[1:]):
            if i < len(pauses) and pauses[i] > 0:
                result += AudioSegment.silent(duration=pauses[i])
            result += sound

        return result

    def create_send_out_sequence(self, dex_number: int) -> Optional[tuple[str, float]]:
        """
        Create send out sequence: throw → switch → pokemon cry

        Args:
            dex_number: Pokemon's national dex number

        Returns:
            Tuple of (temp_file_path, duration_in_seconds) or None
        """
        if not self.CRIES_DIR.exists():
            return None

        sounds = []

        # Load throw sound
        throw = self._load_audio(self.POKEBALL_THROW)
        if throw:
            sounds.append(throw)

        # Load switch sound
        switch = self._load_audio(self.SWITCH_SOUND)
        if switch:
            sounds.append(switch)

        # Load Pokemon cry
        cry_path = self._get_cry_path(dex_number, "INDEX")
        if cry_path:
            cry = self._load_audio(cry_path)
            if cry:
                sounds.append(cry)

        if not sounds:
            return None

        # Create sequence with small pauses
        sequence = self._create_sound_sequence(sounds, pauses=[50, 100])  # 50ms and 100ms pauses
        if not sequence:
            return None

        # Export to temp file
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_path = temp_file.name
            temp_file.close()

            sequence.export(temp_path, format="mp3")
            self._temp_files.append(temp_path)

            duration = len(sequence) / 1000.0
            print(f"✅ Created send out sequence for #{dex_number:03d} ({duration:.2f}s)")
            return (temp_path, duration)

        except Exception as e:
            print(f"❌ Error creating send out sequence: {e}")
            return None

    def create_switch_sequence(self, dex_number: int) -> Optional[tuple[str, float]]:
        """
        Create switch sequence: switch → pause → throw → switch → pokemon cry

        Args:
            dex_number: Pokemon's national dex number

        Returns:
            Tuple of (temp_file_path, duration_in_seconds) or None
        """
        if not self.CRIES_DIR.exists():
            return None

        sounds = []
        pauses = []

        # Load switch sound (recall)
        switch = self._load_audio(self.SWITCH_SOUND)
        if switch:
            sounds.append(switch)
            pauses.append(200)  # 200ms pause after recall

        # Load throw sound
        throw = self._load_audio(self.POKEBALL_THROW)
        if throw:
            sounds.append(throw)
            pauses.append(50)  # 50ms pause

        # Load switch sound again (send out)
        if switch:
            sounds.append(switch)
            pauses.append(100)  # 100ms pause

        # Load Pokemon cry
        cry_path = self._get_cry_path(dex_number, "INDEX")
        if cry_path:
            cry = self._load_audio(cry_path)
            if cry:
                sounds.append(cry)

        if not sounds:
            return None

        # Create sequence
        sequence = self._create_sound_sequence(sounds, pauses=pauses)
        if not sequence:
            return None

        # Export to temp file
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_path = temp_file.name
            temp_file.close()

            sequence.export(temp_path, format="mp3")
            self._temp_files.append(temp_path)

            duration = len(sequence) / 1000.0
            print(f"✅ Created switch sequence for #{dex_number:03d} ({duration:.2f}s)")
            return (temp_path, duration)

        except Exception as e:
            print(f"❌ Error creating switch sequence: {e}")
            return None

    def create_faint_sequence(self, dex_number: int) -> Optional[tuple[str, float]]:
        """
        Create faint sequence: sad cry → faint noise

        Args:
            dex_number: Pokemon's national dex number

        Returns:
            Tuple of (temp_file_path, duration_in_seconds) or None
        """
        if not self.CRIES_DIR.exists():
            return None

        sounds = []

        # Load sad cry
        cry_path = self._get_cry_path(dex_number, "SAD")
        if cry_path:
            cry = self._load_audio(cry_path)
            if cry:
                sounds.append(cry)

        # Load faint sound
        faint = self._load_audio(self.FAINT_SOUND)
        if faint:
            sounds.append(faint)

        if not sounds:
            return None

        # Create sequence with small pause
        sequence = self._create_sound_sequence(sounds, pauses=[100])  # 100ms pause
        if not sequence:
            return None

        # Export to temp file
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_path = temp_file.name
            temp_file.close()

            sequence.export(temp_path, format="mp3")
            self._temp_files.append(temp_path)

            duration = len(sequence) / 1000.0
            print(f"✅ Created faint sequence for #{dex_number:03d} ({duration:.2f}s)")
            return (temp_path, duration)

        except Exception as e:
            print(f"❌ Error creating faint sequence: {e}")
            return None

    def cleanup_temp_files(self):
        """Clean up temporary audio files"""
        for temp_path in self._temp_files:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as e:
                print(f"⚠️ Error cleaning up temp file {temp_path}: {e}")

        self._temp_files.clear()

    def is_available(self) -> bool:
        """Check if sound effects are available"""
        return self.CRIES_DIR.exists()
