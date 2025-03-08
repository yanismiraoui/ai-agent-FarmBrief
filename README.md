# FarmBrief 🌾

FarmBrief is a powerful Discord bot designed to enhance your server's functionality with AI-powered features for content creation, learning, and collaboration.

**Deployed with Replit and available 24/7 on the FarmBrief Discord server 🌟**

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
- TXT file summarization
- Discussion thread summarization
- Customizable summary length
- Structured output format

Usage:
```bash
# Summarize PDF
!summarize pdf [max_words]
# Summarize TXT
!summarize txt [max_words]
# Summarize discussion
!summarize discussion [max_words]
```

### 6. Interactive Flashcards 🎴
Convert any content into interactive study flashcards:
- Generate flashcards from PDF documents, TXT files, or discussions
- Difficulty levels (Easy 🟢, Medium 🟡, Hard 🔴)
- Category-based organization
- Interactive reaction-based controls
- Progress tracking and statistics
- Spaced repetition learning

Usage:
```bash
# Create from PDF
!create_flashcards pdf [num_cards]
# Create from TXT
!create_flashcards txt [num_cards]
# Create from discussion
!create_flashcards discussion [num_cards] [message_limit]
```

### 7. Text-to-Speech 🗣️
Convert text to natural-sounding speech:
- High-quality voice synthesis
- Support for various languages
- Custom voice selection

Usage:
```bash
!speak "Your text here"
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

- **!summarize [source_type] [max_words]**
  - **Arguments**: 
    - `source_type`: Type of content to summarize ("pdf", "txt", or "discussion")
    - `max_words`: Optional maximum number of words for the summary
  - **Use Case**: Summarizes content from different sources. For PDF/TXT, attach the file to the message. For discussions, it processes recent messages in the channel.
  - **Example**: 
    - `!summarize pdf 100` (with PDF attachment)
    - `!summarize txt 200` (with TXT attachment)
    - `!summarize discussion 150`
  
- **!create_quiz [source_type] [search] [args]**
  - **Arguments**: 
    - `source_type`: Either "pdf", "txt", or "discussion"
    - `search`: Optional string to search for cached PDF files (only for "pdf" source type)
    - `args`: For "pdf"/"txt", specify `[num_questions]`. For "discussion", specify `[message_limit] [num_questions]`
  - **Use Case**: Creates an interactive quiz from a document or discussion. Users can join the quiz and answer questions to earn points. Can use a cached PDF file if a search string is provided.
  - **Example**: `!create_quiz pdf report 10` or `!create_quiz discussion 50 5`

- **!create_podcast [source_type] [search] [message_limit]**
  - **Arguments**: 
    - `source_type`: Either "pdf" or "discussion"
    - `search`: Optional string to search for cached PDF files (only for "pdf" source type)
    - `message_limit`: Number of messages to consider for discussion (default is 50)
  - **Use Case**: Generates a podcast from a document or discussion. Users can attach a PDF or use recent messages in the channel to create a podcast script and audio. Can use a cached PDF file if a search string is provided.
  - **Example**: `!create_podcast pdf report` or `!create_podcast discussion 30`

- **!create_flashcards [source_type] [num_cards] [message_limit]**
  - **Arguments**: 
    - `source_type`: Type of content to create flashcards from ("pdf", "txt", or "discussion")
    - `num_cards`: Number of flashcards to generate (default: 10)
    - `message_limit`: For discussion mode, number of messages to process (default: 50)
  - **Use Case**: Creates an interactive flashcard set from documents or discussions. Uses reaction-based controls for easy navigation and progress tracking.
  - **Example**: 
    - `!create_flashcards pdf 15` (with PDF attachment)
    - `!create_flashcards txt 10` (with TXT attachment)
    - `!create_flashcards discussion 20 100` (from last 100 messages)
  - **Controls**:
    - 🔄 Show Answer
    - ⏭️ Next Card
    - ✅ Mark Correct
    - ❌ Mark Incorrect
    - 🏁 End Session

- **!speak [text]**
  - **Arguments**: 
    - `text`: The text to convert into speech
  - **Use Case**: Converts the provided text into an audio file using Eleven Labs and sends it back to the channel
  - **Example**: `!speak Hello, this is a test message.`

- **!cleanup [hours]**
  - **Arguments**: 
    - `hours`: The age of files to clean up (default is 48 hours)
  - **Use Case**: Cleans up old files stored by the bot. This command is restricted to administrators.
  - **Example**: `!cleanup 24`

- **!ping**
  - **Arguments**: None
  - **Use Case**: Checks the bot's responsiveness and latency
  - **Example**: `!ping`

- **!help**
  - **Arguments**: None
  - **Use Case**: Provides a list of available commands and their descriptions
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
