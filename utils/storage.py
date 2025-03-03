import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class FileStorage:
    def __init__(self, base_dir: str = "storage"):
        self.base_dir = Path(base_dir)
        self.config_dir = self.base_dir / "config"
        self.temp_dir = self.base_dir / "temp"
        self.audio_dir = self.base_dir / "audio"
        self.pdf_dir = self.base_dir / "pdf"
        
        # Create necessary directories
        for directory in [self.config_dir, self.temp_dir, self.audio_dir, self.pdf_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def save_guild_config(self, guild_id: int, config: Dict[str, Any]) -> None:
        """Save guild-specific configuration."""
        file_path = self.config_dir / f"guild_{guild_id}.json"
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=4)
    
    def load_guild_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Load guild-specific configuration."""
        file_path = self.config_dir / f"guild_{guild_id}.json"
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        return None
    
    def save_temp_file(self, content: bytes, prefix: str, suffix: str) -> Path:
        """Save temporary content with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}{suffix}"
        file_path = self.temp_dir / filename
        with open(file_path, 'wb') as f:
            f.write(content)
        return file_path
    
    def save_audio(self, audio_data: bytes, identifier: str) -> Path:
        """Save generated audio file."""
        file_path = self.audio_dir / f"{identifier}.mp3"
        with open(file_path, 'wb') as f:
            f.write(audio_data)
        return file_path
    
    def save_pdf(self, pdf_data: bytes, filename: str) -> Path:
        """Save uploaded PDF file."""
        file_path = self.pdf_dir / filename
        with open(file_path, 'wb') as f:
            f.write(pdf_data)
        return file_path
    
    def cleanup_old_files(self, max_age_hours: int = 48) -> None:
        """Clean up files older than specified hours."""
        current_time = datetime.now().timestamp()
        
        for directory in [self.temp_dir, self.audio_dir]:
            for file_path in directory.glob('*'):
                if file_path.is_file():
                    file_age = current_time - os.path.getctime(file_path)
                    if file_age > max_age_hours * 3600:
                        file_path.unlink() 