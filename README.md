# FarmBrief 🌾

FarmBrief is a powerful Discord bot designed to enhance your server's functionality with AI-powered features for content creation, learning, and collaboration.

## Features

### 1. Podcast Creation 🎙️
Convert text content into engaging podcast-style conversations:
- Generate natural dialogues between two hosts (Alex and Rachel)
- Process content from channel discussions and/or PDF documents
- Create high-quality audio using ElevenLabs voices
- Automatic script generation with natural transitions and insights

Usage:
```bash
# Create from PDF
!create_podcast pdf
# Create from discussion
!create_podcast discussion [message_limit]
```

### 2. Interactive Quizzes 📝
Create and manage engaging quiz sessions:
- Generate questions from channel discussions and/or PDF documents
- Multiplayer games with timed responses
- Points system based on speed and accuracy

Usage:
```bash
# Create quiz from PDF
!create_quiz pdf [num_questions]
# Create quiz from discussion
!create_quiz discussion [message_limit] [num_questions]
```

### 3. Structured Debates 🎭
Facilitate organized debates in voice channels:
- Multiple debate formats (standard, quick, extended)
- Timed speaking periods for each participant
- Structured phases (opening, main arguments, closing)
- Automated timekeeping and announcements
- AI-generated balanced summaries

Usage:
```bash
!start_debate "topic" [format]
```

### 4. Whiteboard Sessions 🎨
Capture and analyze whiteboard content:
- Convert visual notes to structured text summaries
- Real-time processing of whiteboard images
- Support for multiple images per session
- Comprehensive session summaries
- Participant tracking and statistics

Usage:
```bash
# Start a session
!start_whiteboard "Session Title"
# End and summarize session
!end_whiteboard
```

### 5. Content Summarization 📚
Generate concise summaries of various content types:
- PDF document summarization
- Discussion thread summarization
- Customizable summary length
- Structured output format

Usage:
```bash
# Summarize PDF
!summarize_pdf [max_words]
# Summarize discussion
!summarize_discussion [message_limit]
```

### 6. Text-to-Speech 🗣️
Convert text to natural-sounding speech:
- High-quality voice synthesis
- Support for various languages
- Custom voice selection

Usage:
```bash
!speak "Your text here"
!list_voices
```

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yanismiraoui/ai-agent-FarmBrief.git
cd ai-agent-FarmBrief
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
DISCORD_TOKEN=your_discord_token
ELEVEN_LABS_API_KEY=your_elevenlabs_key
MISTRAL_API_KEY=your_mistral_key
```

4. Run the bot:
```bash
python main.py
```

## Registered Discord Commands

Below is a list of the registered Discord commands available in this bot, along with their arguments, use cases, and examples:

- **!summarize_pdf [search] [max_words]**
  - **Arguments**: 
    - `search`: Optional string to search for cached PDF files.
    - `max_words`: Optional maximum number of words for the summary.
  - **Use Case**: Summarizes the content of an attached PDF file or a cached PDF file matching the search string. Users need to attach a PDF to the message or provide a search string.
  - **Example**: `!summarize_pdf report 100`

- **!summarize_discussion [message_limit]**
  - **Arguments**: 
    - `message_limit`: Number of recent messages to summarize (default is 50).
  - **Use Case**: Summarizes the recent discussion in the channel, providing a concise overview of the conversation.
  - **Example**: `!summarize_discussion 20`
  
- **!create_quiz [source_type] [search] [args]**
  - **Arguments**: 
    - `source_type`: Either "pdf" or "discussion".
    - `search`: Optional string to search for cached PDF files (only for "pdf" source type).
    - `args`: For "pdf", specify `[num_questions]`. For "discussion", specify `[message_limit] [num_questions]`.
  - **Use Case**: Creates an interactive quiz from a document or discussion. Users can join the quiz and answer questions to earn points. Can use a cached PDF file if a search string is provided.
  - **Example**: `!create_quiz pdf report 10` or `!create_quiz discussion 50 5`

- **!create_podcast [source_type] [search] [message_limit]**
  - **Arguments**: 
    - `source_type`: Either "pdf" or "discussion".
    - `search`: Optional string to search for cached PDF files (only for "pdf" source type).
    - `message_limit`: Number of messages to consider for discussion (default is 50).
  - **Use Case**: Generates a podcast from a document or discussion. Users can attach a PDF or use recent messages in the channel to create a podcast script and audio. Can use a cached PDF file if a search string is provided.
  - **Example**: `!create_podcast pdf report` or `!create_podcast discussion 30`

- **!speak [text]**
  - **Arguments**: 
    - `text`: The text to convert into speech.
  - **Use Case**: Converts the provided text into an audio file using Eleven Labs and sends it back to the channel.
  - **Example**: `!speak Hello, this is a test message.`

- **!list_voices**
  - **Arguments**: None
  - **Use Case**: Lists available voices from Eleven Labs that can be used for text-to-speech conversion.
  - **Example**: `!list_voices`

- **!cleanup [hours]**
  - **Arguments**: 
    - `hours`: The age of files to clean up (default is 48 hours).
  - **Use Case**: Cleans up old files stored by the bot. This command is restricted to administrators.
  - **Example**: `!cleanup 24`

- **!ping**
  - **Arguments**: None
  - **Use Case**: Checks the bot's responsiveness and latency.
  - **Example**: `!ping`

- **!help**
  - **Arguments**: None
  - **Use Case**: Provides a list of available commands and their descriptions.
  - **Example**: `!help`

## Dependencies
- discord.py
- elevenlabs
- mistralai
- pydub
- python-dotenv
- asyncio

## File Structure
```
FarmBrief/
├── main.py
├── handlers/
│   └── commands.py
├── processors/
│   ├── content_processor.py
│   └── audio_generator.py
├── utils/
│   └── storage.py
└── README.md
```


## Acknowledgments
- Discord.py for the Discord API wrapper
- ElevenLabs for text-to-speech capabilities
- Mistral AI for content processing and generation
