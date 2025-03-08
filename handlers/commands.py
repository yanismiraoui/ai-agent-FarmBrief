import discord
from discord.ext import commands
from typing import Optional, List, Tuple, Dict, Any
from processors.content_processor import ContentProcessor
from processors.audio_generator import AudioGenerator
from utils.storage import FileStorage
import io
import asyncio
from pydub import AudioSegment
import tempfile
import os
import json
import base64
import random

class CommandHandler(commands.Cog):
    def __init__(self, bot: commands.Bot, content_processor: ContentProcessor, 
                 audio_generator: AudioGenerator, storage: FileStorage):
        self.bot = bot
        self.content_processor = content_processor
        self.audio_generator = audio_generator
        self.storage = storage
        # Voice management
        self.available_male_voices = []
        self.available_female_voices = []
        self.host1_voice = "21m00Tcm4TlvDq8ikWAM"  # Temporary default
        self.host2_voice = "21m00Tcm4TlvDq8ikWAM"  # Temporary default
        
        # Initialize voices asynchronously
        self.bot.loop.create_task(self.initialize_voices())
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 2  # seconds between requests
        
        # Store active sessions
        self.active_quizzes = {}
        self.active_debates = {}
        self.active_whiteboards = {}
        self.active_flashcard_sets = {}

    async def initialize_voices(self):
        """Initialize available voices for the podcast hosts."""
        try:
            voices = await self.audio_generator.list_voices()
            
            # Store available voices by gender
            self.available_male_voices = [
                {"voice_id": v["voice_id"], "name": v["name"]}
                for v in voices 
                if v.get("labels", {}).get("gender") == "male"
            ]
            self.available_female_voices = [
                {"voice_id": v["voice_id"], "name": v["name"]}
                for v in voices 
                if v.get("labels", {}).get("gender") == "female"
            ]
            
            # Set initial voices
            await self.select_random_voices()
            
            print(f"Available male voices: {[v['name'] for v in self.available_male_voices]}")
            print(f"Available female voices: {[v['name'] for v in self.available_female_voices]}")
                
        except Exception as e:
            print(f"Warning: Could not initialize voices, using fallback. Error: {str(e)}")

    async def select_random_voices(self) -> Tuple[str, str]:
        """Randomly select new voices for the podcast hosts."""
        if not self.available_male_voices or not self.available_female_voices:
            print("Warning: Not enough voices available, using fallback voices")
            return
        
        # Select random male voice for Alex
        male_voice = random.choice(self.available_male_voices)
        self.host1_voice = male_voice["voice_id"]
        
        # Select random female voice for Rachel
        female_voice = random.choice(self.available_female_voices)
        self.host2_voice = female_voice["voice_id"]
        
        print(f"Selected voices - Alex: {male_voice['name']}, Rachel: {female_voice['name']}")
        return self.host1_voice, self.host2_voice

    async def generate_podcast_script(self, content: str) -> List[Tuple[str, str]]:
        """Generate a conversational podcast script from content."""
        try:
            # Select new random voices for this podcast
            await self.select_random_voices()
            
            # First, get a detailed summary of the content
            summary = await self.content_processor.summarize_content(content)
            
            # Now, create a podcast script prompt
            script_prompt = f"""You are creating a natural, engaging podcast script between two hosts discussing the following content.

            Requirements:
            1. The hosts are Alex (witty and analytical) and Rachel (enthusiastic and relatable)
            2. Format each line exactly as "Alex: [dialogue]" or "Rachel: [dialogue]"
            3. Start with a catchy podcast intro:
               - Include a warm welcome and a relevant show name 
               - Brief host introductions (don't mention their their personalities)
               - Set up today's topic with an engaging hook
               - Keep intro under 20 seconds (2-3 exchanges)
            4. Make it highly conversational with:
               - Natural interruptions ("Oh wait-", "Hold on-", "Actually-")
               - Excited reactions ("No way!", "That's incredible!", "Really?")
               - Personal anecdotes and examples
               - Casual jokes and playful banter
               - Follow-up questions showing genuine curiosity
               - Friendly disagreements and debates
            5. Include dynamic elements:
               - Voice variations (excited, thoughtful, skeptical)
               - Tone changes (whispers, emphasis, dramatic pauses)
               - Short tangents that feel natural
               - References to current events when relevant
            6. Keep it to 2-5 minutes in length (about 8-12 exchanges)
            7. Structure:
               - Start with the podcast intro
               - Build natural flow between topics
               - Include back-and-forth discussion
               - End with key takeaways or thought-provoking conclusion
            8. Important: Do not include stage directions or action descriptions
               - No "*laughs*", "*sighs*", or similar markers
               - Instead, convey emotion through word choice and punctuation
               - Use em dashes for interruptions
               - Use ellipses for thoughtful pauses

            Content to discuss:
            {summary}

            Begin the script now, using only the Alex: and Rachel: format for every line:"""
            
            # Get the script from Mistral
            messages = [
                {
                    "role": "system", 
                    "content": "You are a professional podcast script writer who creates engaging, natural dialogue that feels like a real conversation between friends who are also experts."
                },
                {
                    "role": "user", 
                    "content": script_prompt
                }
            ]
            
            response = await self.content_processor.mistral_client.chat.complete_async(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.7
            )
            
            script = response.choices[0].message.content
            
            # Parse the script into a list of (speaker, text) tuples
            lines = [line.strip() for line in script.strip().split('\n') if line.strip()]
            dialogue = []
            
            for line in lines:
                if ':' in line:
                    speaker, text = line.split(':', 1)
                    speaker = speaker.strip()
                    text = text.strip()
                    if speaker in ['Alex', 'Rachel'] and text:
                        dialogue.append((speaker, text))
            
            # Validate the dialogue
            if len(dialogue) < 4:  # Minimum of 4 exchanges
                raise ValueError(f"Generated script too short ({len(dialogue)} lines). Expected at least 4 exchanges.")
            
            if not any(speaker == 'Alex' for speaker, _ in dialogue):
                raise ValueError("Missing dialogue for Alex")
            
            if not any(speaker == 'Rachel' for speaker, _ in dialogue):
                raise ValueError("Missing dialogue for Rachel")
            
            return dialogue
            
        except Exception as e:
            print(f"Script generation error: {str(e)}")
            print(f"Generated content: {script if 'script' in locals() else 'No script generated'}")
            return []

    def search_pdf(self, search_string: str, directory: str = "./storage/pdf") -> List[str]:
        """Search for PDF files in directory that partially match the provided search string."""
        pdf_directory = directory
        matches = []
        
        # Check if directory exists
        if not os.path.exists(pdf_directory):
            return matches
        
        # List all files in the directory
        for filename in os.listdir(pdf_directory):
            # Check if the file is a PDF and if the search string is in the filename
            if filename.lower().endswith('.pdf') and search_string.lower() in filename.lower():
                # Can return just the filename or the full path
                full_path = os.path.join(pdf_directory, filename)
                matches.append(full_path)
        
        return matches

    @commands.command(name="create_podcast")
    async def create_podcast(self, ctx: commands.Context, source_type: str = None, message_limit: int = 50, *args):
        """Create a podcast from a PDF, TXT file, or discussion.
        Usage: 
        !create_podcast pdf [file attachment]
        !create_podcast txt [file attachment]
        !create_podcast discussion [message_limit]
        """
        if not source_type or source_type.lower() not in ['pdf', 'txt', 'discussion']:
            await ctx.send("❌ Please specify the source type (pdf, txt, or discussion)!\n"
                          "Usage:\n"
                          "• `!create_podcast pdf` (with PDF attachment)\n"
                          "• `!create_podcast txt` (with TXT attachment)\n"
                          "• `!create_podcast discussion [message_limit]`")
            return

        try:
            content = None
            filename = None
            
            if source_type.lower() == "discussion":
                # Process discussion messages
                await ctx.send(f"📝 Extracting last {message_limit} messages from discussion...")
                messages = []
                async for message in ctx.channel.history(limit=message_limit):
                    if not message.author.bot:  # Skip bot messages
                        messages.append(message)
                
                if not messages:
                    await ctx.send("❌ No messages found in the discussion.")
                    return
                
                # Extract content from messages
                content = "\n".join([f"{msg.author.name}: {msg.content}" for msg in messages])
                filename = f"Discussion in #{ctx.channel.name}"
                
            else:
                # Handle file-based sources (PDF and TXT)
                if not ctx.message.attachments:
                    await ctx.send("❌ Please attach a file!")
                    return

                file = ctx.message.attachments[0]
                
                # Validate file type
                if source_type.lower() == 'pdf' and not file.filename.lower().endswith('.pdf'):
                    await ctx.send("❌ Please attach a PDF file!")
                    return
                elif source_type.lower() == 'txt' and not file.filename.lower().endswith('.txt'):
                    await ctx.send("❌ Please attach a TXT file!")
                    return

                # Download and process the file
                file_bytes = await file.read()
                
                # Process content based on file type
                if source_type.lower() == 'pdf':
                    content = await self.content_processor.process_pdf(file_bytes)
                else:  # txt
                    content = file_bytes.decode('utf-8')
                
                filename = file.filename

            if not content:
                await ctx.send("❌ No content found to process.")
                return

            # Generate podcast script
            await ctx.send("🎙️ Generating engaging podcast script...")
            script = await self.generate_podcast_script(content)
            
            if not script:
                await ctx.send("❌ Failed to generate podcast script. Please try again.")
                return

            # Create audio segments with sound effects
            await ctx.send("🎵 Creating audio segments...")
            audio_segments = []
            
            # Generate intro sound effect
            try:
                intro_effect = await self.audio_generator.generate_sound(
                    text="Professional radio podcast intro with upbeat synth melody and warm pad",
                    duration_seconds=3.0,
                    prompt_influence=0.4
                )
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                    temp_file.write(intro_effect)
                    audio_segments.append(temp_file.name)
            except Exception as e:
                print(f"Warning: Could not generate intro effect: {e}")

            for i, (speaker, text) in enumerate(script):
                try:
                    # Rate limiting
                    now = asyncio.get_event_loop().time()
                    time_since_last = now - self.last_request_time
                    if time_since_last < self.min_request_interval:
                        await asyncio.sleep(self.min_request_interval - time_since_last)
                    
                    # Select voice based on speaker
                    voice_id = self.host1_voice if speaker == "Alex" else self.host2_voice
                    
                    # Add SSML tags for more dynamic speech
                    ssml_text = self.add_speech_dynamics(text)
                    
                    await ctx.send(f"🎙️ Generating audio for segment {i+1}/{len(script)}...")
                    
                    # Generate audio with retry logic
                    audio_data = await self._generate_audio_with_retry(ssml_text, voice_id)
                    
                    if audio_data:
                        # Save speech segment
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                            temp_file.write(audio_data)
                            audio_segments.append(temp_file.name)
                        
                        # Add transition effect between segments (except for the last one)
                        if i < len(script) - 1:
                            try:
                                # Generate different types of transitions
                                if i % 3 == 0:
                                    effect_text = "Smooth radio transition with subtle whoosh and gentle chime"
                                elif i % 3 == 1:
                                    effect_text = "Soft ambient pad transition with warm texture"
                                else:
                                    effect_text = "Light musical transition with gentle bell tone"
                                
                                transition = await self.audio_generator.generate_sound(
                                    text=effect_text,
                                    duration_seconds=1.0,
                                    prompt_influence=0.3
                                )
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                                    temp_file.write(transition)
                                    audio_segments.append(temp_file.name)
                            except Exception as e:
                                print(f"Warning: Could not generate transition effect: {e}")
                                
                except Exception as e:
                    await ctx.send(f"⚠️ Error generating segment {i+1}: {str(e)}")
                    continue

            if not audio_segments:
                await ctx.send("❌ Failed to generate any audio segments. Please try again.")
                return

            # Generate outro sound effect
            try:
                outro_effect = await self.audio_generator.generate_sound(
                    text="Professional radio outro with gentle fade out and warm pad",
                    duration_seconds=2.5,
                    prompt_influence=0.35
                )
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                    temp_file.write(outro_effect)
                    audio_segments.append(temp_file.name)
            except Exception as e:
                print(f"Warning: Could not generate outro effect: {e}")

            # Combine audio segments with enhanced transitions
            await ctx.send("🎚️ Mixing audio with professional transitions...")
            try:
                combined = AudioSegment.empty()
                for i, segment in enumerate(audio_segments):
                    current = AudioSegment.from_mp3(segment)
                    
                    # Adjust volume levels for different types of audio
                    if i == 0:  # Intro effect
                        current = current - 5  # Slightly quieter than speech
                    elif i == len(audio_segments) - 1:  # Outro effect
                        current = current - 5
                    elif i % 2 == 0:  # Speech segments
                        current = current
                    else:  # Transition effects
                        current = current - 8  # Even quieter transitions
                    
                    # Add crossfade between segments
                    if len(combined) > 0:
                        combined = combined.append(current, crossfade=300)
                    else:
                        combined = current
                    
                    os.unlink(segment)  # Clean up temp file

                # Add final processing
                combined = combined.normalize()  # Normalize overall volume
                
                # Export final podcast
                output_file = f"podcast_{ctx.message.id}.mp3"
                combined.export(output_file, format="mp3", parameters=["-q:a", "2"])  # Higher quality export
                
                # Send the podcast file
                await ctx.send("🎉 Your podcast is ready!", file=discord.File(output_file))
                os.unlink(output_file)  # Clean up

            except Exception as e:
                await ctx.send(f"❌ Error creating podcast: {str(e)}")
                # Clean up any remaining temp files
                for segment in audio_segments:
                    if os.path.exists(segment):
                        os.unlink(segment)

        except Exception as e:
            await ctx.send(f"❌ Error processing file: {str(e)}")

    async def _generate_audio_with_retry(self, text: str, voice_id: str, max_retries: int = 3) -> Optional[bytes]:
        """Helper method to generate audio with retry logic."""
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                audio_data = await self.audio_generator.generate_audio(
                    text,
                    voice_id=voice_id
                )
                if audio_data:
                    return audio_data
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise e
        
        return None

    def add_speech_dynamics(self, text: str) -> str:
        """Add SSML tags to make speech more dynamic and natural."""
        # Add random pauses and emphasis
        words = text.split()
        enhanced_text = ""
        
        for i, word in enumerate(words):
            # Add emphasis to important words
            if any(marker in word.lower() for marker in ['!', '?', 'wow', 'amazing', 'interesting']):
                word = f'<emphasis level="strong">{word}</emphasis>'
            
            # Add brief pauses for commas and periods
            if ',' in word:
                word = f'{word}<break time="200ms"/>'
            elif '.' in word:
                word = f'{word}<break time="400ms"/>'
            
            enhanced_text += word + " "
        
        return f'<speak>{enhanced_text.strip()}</speak>'

    @commands.command(name="summarize")
    async def summarize(self, ctx: commands.Context, source_type: str = "discussion", max_words: Optional[int] = None):
        """Summarize content from different sources.
        Usage:
        - Discussion: !summarize discussion [max_words]
        - PDF: !summarize pdf [max_words] (with PDF attachment)
        - TXT: !summarize txt [max_words] (with TXT attachment)
        """
        try:
            # Handle file-based sources (PDF and TXT)
            if source_type.lower() in ["pdf", "txt"]:
                if not ctx.message.attachments:
                    await ctx.send(f"Please attach a {source_type.upper()} file to summarize!")
                    return
                
                attachment = ctx.message.attachments[0]
                file_ext = source_type.lower()
                if not attachment.filename.lower().endswith(f'.{file_ext}'):
                    await ctx.send(f"Please attach a valid {source_type.upper()} file!")
                    return
                
                # Read and process file
                file_bytes = await attachment.read()
                
                if source_type.lower() == "pdf":
                    file_io = io.BytesIO(file_bytes)
                    # Save PDF (synchronously) for reference
                    pdf_path = self.storage.save_pdf(file_bytes, attachment.filename)
                    await ctx.send("Processing PDF...")
                    text = await self.content_processor.process_pdf(file_io)
                else:  # txt
                    await ctx.send("Processing TXT...")
                    text = file_bytes.decode('utf-8')
                
            # Handle discussion summarization
            elif source_type.lower() == "discussion":
                await ctx.send("Processing discussion...")
                messages = []
                async for message in ctx.channel.history(limit=50):  # Default to last 50 messages
                    messages.append(message)
                text = await self.content_processor.extract_discussion(messages)
                await ctx.send(f"Extracted {len(messages)} messages from discussion.")
                
            else:
                await ctx.send("Invalid source type. Use 'pdf', 'txt', or 'discussion'.")
                return
            
            # Generate summary
            summary = await self.content_processor.summarize_content(text, max_words)
            
            # Split summary into chunks of 1900 characters (leaving room for formatting)
            chunks = [summary[i:i+1900] for i in range(0, len(summary), 1900)]
            
            # Send summary chunks
            if source_type.lower() in ["pdf", "txt"]:
                await ctx.send(f"Summary of {attachment.filename} (Part 1/{len(chunks)}):\n{chunks[0]}")
            else:
                await ctx.send(f"Discussion Summary (Part 1/{len(chunks)}):\n{chunks[0]}")
            
            # Send remaining chunks if any
            for i, chunk in enumerate(chunks[1:], 2):
                await ctx.send(f"Part {i}/{len(chunks)}:\n{chunk}")
                
        except Exception as e:
            await ctx.send(f"Error processing {source_type}: {str(e)}")
            
    @commands.command(name="speak")
    async def speak(self, ctx: commands.Context, *, text: str):
        """Convert text to speech using Eleven Labs."""
        await ctx.send("Generating audio...")
        
        try:
            # Generate audio
            audio_data = await self.audio_generator.generate_audio(text)
            
            # Save audio file (synchronously)
            audio_path = self.storage.save_audio(audio_data, f"speech_{ctx.message.id}")
            
            # Send audio file
            await ctx.send(file=discord.File(str(audio_path)))
            
        except Exception as e:
            await ctx.send(f"Error generating audio: {str(e)}")
    
    @commands.command(name="cleanup")
    @commands.has_permissions(administrator=True)
    async def cleanup(self, ctx: commands.Context, hours: int = 48):
        """Clean up old files (admin only)."""
        try:
            self.storage.cleanup_old_files(hours)
            await ctx.send(f"Cleaned up files older than {hours} hours.")
        except Exception as e:
            await ctx.send(f"Error during cleanup: {str(e)}")
    
    @commands.command(name="create_quiz")
    async def create_quiz(self, ctx: commands.Context, source_type: str = "discussion", *args):
        """Create an interactive quiz from a document or discussion.
        Usage:
        - With PDF: Attach a PDF and use '!create_quiz pdf [num_questions]'
        - With TXT: Attach a TXT and use '!create_quiz txt [num_questions]'
        - With discussion: Use '!create_quiz discussion [message_limit] [num_questions]'
        """
        try:
            await ctx.send("📝 Starting quiz creation...")
            
            # Parse arguments based on source type
            if source_type.lower() in ["pdf", "txt"]:
                num_questions = 5  # default
                if args:
                    try:
                        num_questions = int(args[0])
                    except ValueError:
                        await ctx.send("❌ Invalid number of questions. Using default (5).")
                message_limit = 50  # not used for PDF/TXT
            else:
                message_limit = 50  # default
                num_questions = 5  # default
                if len(args) >= 1:
                    try:
                        message_limit = int(args[0])
                    except ValueError:
                        await ctx.send("❌ Invalid message limit. Using default (50).")
                if len(args) >= 2:
                    try:
                        num_questions = int(args[1])
                    except ValueError:
                        await ctx.send("❌ Invalid number of questions. Using default (5).")
            
            # Get source content
            if source_type.lower() in ["pdf", "txt"]:
                if not ctx.message.attachments:
                    await ctx.send(f"Please attach a {source_type.upper()} file!")
                    return
                
                attachment = ctx.message.attachments[0]
                file_ext = source_type.lower()
                if not attachment.filename.lower().endswith(f'.{file_ext}'):
                    await ctx.send(f"Please attach a valid {source_type.upper()} file!")
                    return
                
                file_bytes = await attachment.read()
                
                if source_type.lower() == "pdf":
                    file_io = io.BytesIO(file_bytes)
                    content = await self.content_processor.process_pdf(file_io)
                else:  # txt
                    content = file_bytes.decode('utf-8')
                
                await ctx.send(f"📄 {source_type.upper()} processed successfully. Generating {num_questions} questions...")
                
            elif source_type.lower() == "discussion":
                messages = []
                async for message in ctx.channel.history(limit=message_limit):
                    messages.append(message)
                content = await self.content_processor.extract_discussion(messages)
                await ctx.send(f"💬 Extracted {len(messages)} messages from discussion.")
                
            else:
                await ctx.send("Invalid source type. Use 'pdf', 'txt', or 'discussion'.")
                return
            
            # First attempt with full content
            await ctx.send("🤔 Generating quiz questions...")
            questions = await self.content_processor.generate_quiz_questions(content, num_questions)
            
            # If failed, try with summarized content
            if not questions:
                await ctx.send("⚠️ First attempt failed. Trying with summarized content...")
                summary = await self.content_processor.summarize_content(content)
                questions = await self.content_processor.generate_quiz_questions(summary, num_questions)
                
                # If still failed, try with fewer questions
                if not questions and num_questions > 3:
                    await ctx.send("⚠️ Second attempt failed. Trying with fewer questions...")
                    questions = await self.content_processor.generate_quiz_questions(summary, 3)
            
            if not questions:
                await ctx.send("❌ Failed to generate quiz questions. Please try again with different content or fewer questions.")
                return
            
            # Save quiz data
            quiz_id = str(ctx.message.id)
            quiz_data = {
                "questions": questions,
                "current_question": 0,
                "scores": {},
                "channel_id": ctx.channel.id,
                "participants": set(),  # Track quiz participants
                "started": False        # Track if quiz has started
            }
            self.active_quizzes[quiz_id] = quiz_data
            
            # Create quiz embed
            embed = discord.Embed(
                title="📚 Interactive Quiz",
                description=f"A {len(questions)}-question quiz has been created! Get ready to test your knowledge.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="How to Play",
                value="1. React with 🎮 to join the quiz\n"
                      "2. Questions will appear one at a time\n"
                      "3. React with 🇦, 🇧, 🇨, or 🇩 to answer\n"
                      "4. You have 10 seconds per question\n"
                      "5. Points are awarded based on speed and accuracy",
                inline=False
            )
            embed.set_footer(text=f"Quiz ID: {quiz_id}")
            
            # Send quiz invitation
            quiz_msg = await ctx.send(embed=embed)
            await quiz_msg.add_reaction("🎮")
            
            # Wait for players to join (30 seconds)
            await ctx.send("⏳ Waiting 10 seconds for players to join...")
            
            def check(reaction, user):
                return (
                    reaction.message.id == quiz_msg.id and 
                    str(reaction.emoji) == "🎮" and 
                    not user.bot
                )
            
            try:
                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=10.0, check=check)
                        quiz_data["participants"].add(user.id)
                        quiz_data["scores"][user.id] = 0
                        await ctx.send(f"👋 {user.name} has joined the quiz!")
                    except asyncio.TimeoutError:
                        break
            except Exception as e:
                print(f"Error while waiting for players: {e}")
            
            if not quiz_data["participants"]:
                await ctx.send("❌ No players joined the quiz. Cancelling...")
                del self.active_quizzes[quiz_id]
                return
            
            # Start the quiz
            quiz_data["started"] = True
            await ctx.send(f"🎯 Starting quiz with {len(quiz_data['participants'])} players!")
            await self.run_quiz(ctx, quiz_id)
            
        except Exception as e:
            await ctx.send(f"❌ Error creating quiz: {str(e)}")
            import traceback
            await ctx.send(f"Detailed error:\n```{traceback.format_exc()}```")
    
    async def display_leaderboard(self, ctx: commands.Context, quiz_data: dict, title: str = "📊 Current Standings") -> None:
        """Display the current quiz leaderboard."""
        scores = quiz_data["scores"]
        if not scores:
            await ctx.send("No scores to display yet!")
            return
        
        # Sort players by score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Create leaderboard embed
        embed = discord.Embed(
            title=title,
            color=discord.Color.gold()
        )
        
        # Add player scores
        leaderboard_text = ""
        for i, (player_id, score) in enumerate(sorted_scores, 1):
            player = ctx.guild.get_member(player_id)
            if player:
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👤"
                leaderboard_text += f"{medal} {player.name}: {score} points\n"
        
        embed.add_field(name="Rankings", value=leaderboard_text or "No scores yet!", inline=False)
        await ctx.send(embed=embed)

    async def run_quiz(self, ctx: commands.Context, quiz_id: str):
        """Run a quiz session."""
        quiz_data = self.active_quizzes.get(quiz_id)
        if not quiz_data:
            await ctx.send("❌ Quiz not found.")
            return
        
        try:
            for i, question in enumerate(quiz_data["questions"]):
                # Create question embed
                embed = discord.Embed(
                    title=f"Question {i+1}/{len(quiz_data['questions'])}",
                    description=question["question"],
                    color=discord.Color.green()
                )
                
                # Add options
                options_text = "\n".join([f"{key}: {value}" for key, value in question["options"].items()])
                embed.add_field(name="Options", value=options_text, inline=False)
                
                # Send question
                question_msg = await ctx.send(embed=embed)
                
                # Add option reactions
                option_emojis = {"A": "🇦", "B": "🇧", "C": "🇨", "D": "🇩"}
                for option in question["options"].keys():
                    await question_msg.add_reaction(option_emojis[option])
                
                # Track who has answered
                answered_users = set()
                start_time = asyncio.get_event_loop().time()
                
                # Wait for answers (10 seconds)
                while asyncio.get_event_loop().time() - start_time < 10:
                    try:
                        reaction, user = await self.bot.wait_for(
                            'reaction_add',
                            timeout=10.0 - (asyncio.get_event_loop().time() - start_time),
                            check=lambda r, u: (
                                r.message.id == question_msg.id and
                                str(r.emoji) in option_emojis.values() and
                                u.id in quiz_data["participants"] and
                                u.id not in answered_users
                            )
                        )
                        
                        # Mark user as answered
                        answered_users.add(user.id)
                        
                        # Calculate points (more points for faster answers)
                        time_taken = asyncio.get_event_loop().time() - start_time
                        max_points = 100
                        time_bonus = int((10 - time_taken) * 10)  # Up to 100 bonus points for speed
                        
                        # Check if answer is correct
                        selected_option = next(key for key, emoji in option_emojis.items() if str(reaction.emoji) == emoji)
                        if selected_option == question["correct"]:
                            points = max_points + time_bonus
                            quiz_data["scores"][user.id] = quiz_data["scores"].get(user.id, 0) + points
                            await ctx.send(f"✅ {user.name} answered correctly! +{points} points")
                        
                    except asyncio.TimeoutError:
                        break
                
                # Show correct answer
                correct_emoji = option_emojis[question["correct"]]
                embed.add_field(
                    name="✅ Correct Answer",
                    value=f"{question['correct']}: {question['options'][question['correct']]}\n\n"
                          f"Explanation: {question['explanation']}",
                    inline=False
                )
                await question_msg.edit(embed=embed)
                await ctx.send(f"The correct answer was {correct_emoji}!")
                
                # Display leaderboard every 2 questions or if it's the last question
                if (i + 1) % 2 == 0 or i == len(quiz_data["questions"]) - 1:
                    await self.display_leaderboard(ctx, quiz_data)
                
                # Short pause between questions
                await asyncio.sleep(3)
            
            # End of quiz - show final leaderboard
            await ctx.send("🎉 Quiz completed!")
            await self.display_leaderboard(ctx, quiz_data, "🏆 Final Rankings")
            
        except Exception as e:
            await ctx.send(f"❌ Error during quiz: {str(e)}")
        finally:
            # Clean up
            if quiz_id in self.active_quizzes:
                del self.active_quizzes[quiz_id] 

    async def create_debate_summary(self, debate_data: dict) -> str:
        """Generate a balanced summary of the debate."""
        # Combine all transcribed content
        full_content = "\n\n".join([
            f"Opening Statements:\n{debate_data['transcripts']['opening']}",
            f"Main Arguments:\n{debate_data['transcripts']['main']}",
            f"Closing Statements:\n{debate_data['transcripts']['closing']}"
        ])
        
        prompt = f"""Create a balanced summary of this debate between two sides.

        Requirements:
        1. Maintain strict neutrality
        2. Present key arguments from both sides
        3. Highlight areas of agreement and disagreement
        4. Include notable evidence or examples cited
        5. Do not determine a "winner"

        Debate Content:
        {full_content}

        Format the summary with these sections:
        - Opening Positions
        - Key Arguments
        - Points of Agreement
        - Points of Contention
        - Concluding Statements"""

        try:
            summary = await self.content_processor.summarize_content(prompt)
            return summary
        except Exception as e:
            print(f"Error generating debate summary: {e}")
            return "Error generating debate summary. Please try again."

    @commands.command(name="start_debate")
    async def start_debate(self, ctx: commands.Context, *, args: str = None):
        """Start a structured debate in a voice channel.
        Usage: !start_debate "topic" [format]
        Formats:
        - standard (3min opening, 5min main, 2min closing)
        - quick (2min opening, 3min main, 1min closing)
        - extended (5min opening, 8min main, 3min closing)
        """
        if not args:
            await ctx.send("❌ Please provide a topic for the debate!\n"
                         "Usage: `!start_debate \"Your Topic Here\" [format]`\n"
                         "Available formats: `standard`, `quick`, `extended`")
            return

        # Parse arguments
        parts = args.split('" ')
        if not args.startswith('"') or len(parts) == 0:
            await ctx.send("❌ Topic must be in quotes!\n"
                         "Example: `!start_debate \"Should AI be regulated?\" standard`")
            return

        topic = parts[0].strip('"')
        format_str = parts[1].strip() if len(parts) > 1 else "standard"

        if not ctx.author.voice:
            await ctx.send("❌ You must be in a voice channel to start a debate!")
            return

        # Set up timing based on format
        formats = {
            "standard": {"opening": 180, "main": 300, "closing": 120},
            "quick": {"opening": 120, "main": 180, "closing": 60},
            "extended": {"opening": 300, "main": 480, "closing": 180}
        }
        
        if format_str.lower() not in formats:
            await ctx.send(f"❌ Invalid format '{format_str}'. Using standard format.\n"
                         "Available formats: `standard`, `quick`, `extended`")
            format_str = "standard"
        
        timings = formats[format_str.lower()]
        
        # Create debate data structure
        debate_id = str(ctx.message.id)
        debate_data = {
            "topic": topic,
            "channel_id": ctx.author.voice.channel.id,
            "format": format_str,
            "timings": timings,
            "participants": {"for": None, "against": None},
            "transcripts": {"opening": "", "main": "", "closing": ""},
            "current_phase": None,
            "phase_end_time": None
        }
        
        self.active_debates[debate_id] = debate_data
        
        # Create debate announcement embed
        embed = discord.Embed(
            title="🎭 Formal Debate",
            description=f"Topic: {topic}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Format",
            value=f"• Opening statements: {timings['opening']//60}min\n"
                  f"• Main arguments: {timings['main']//60}min\n"
                  f"• Closing statements: {timings['closing']//60}min",
            inline=False
        )
        embed.add_field(
            name="How to Join",
            value="React with:\n"
                  "✅ to argue in favor\n"
                  "❌ to argue against",
            inline=False
        )
        
        # Send announcement and add reactions
        debate_msg = await ctx.send(embed=embed)
        await debate_msg.add_reaction("✅")
        await debate_msg.add_reaction("❌")
        
        # Wait for participants
        await ctx.send("⏳ Waiting for participants to join...")
        
        def check(reaction, user):
            return (
                reaction.message.id == debate_msg.id and
                str(reaction.emoji) in ["✅", "❌"] and
                not user.bot and
                user.voice and
                user.voice.channel.id == ctx.author.voice.channel.id
            )
        
        try:
            while not (debate_data["participants"]["for"] and debate_data["participants"]["against"]):
                reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
                
                if str(reaction.emoji) == "✅" and not debate_data["participants"]["for"]:
                    debate_data["participants"]["for"] = user.id
                    await ctx.send(f"✅ {user.name} will argue in favor")
                elif str(reaction.emoji) == "❌" and not debate_data["participants"]["against"]:
                    debate_data["participants"]["against"] = user.id
                    await ctx.send(f"❌ {user.name} will argue against")
        
        except asyncio.TimeoutError:
            await ctx.send("❌ Not enough participants joined within 5 minutes. Debate cancelled.")
            del self.active_debates[debate_id]
            return
        
        # Start the debate
        await self.run_debate(ctx, debate_id)

    async def run_debate(self, ctx: commands.Context, debate_id: str):
        """Run a structured debate session."""
        debate_data = self.active_debates.get(debate_id)
        if not debate_data:
            await ctx.send("❌ Debate not found.")
            return
        
        try:
            # Get participant objects
            for_user = ctx.guild.get_member(debate_data["participants"]["for"])
            against_user = ctx.guild.get_member(debate_data["participants"]["against"])
            
            # Announce debate start
            await ctx.send(f"🎭 Debate starting!\nTopic: {debate_data['topic']}\n"
                         f"For: {for_user.mention} | Against: {against_user.mention}")
            
            # Run each phase
            phases = [
                ("opening", "Opening Statements"),
                ("main", "Main Arguments"),
                ("closing", "Closing Statements")
            ]
            
            for phase_id, phase_name in phases:
                debate_data["current_phase"] = phase_id
                phase_time = debate_data["timings"][phase_id]
                
                # Announce phase
                await ctx.send(f"\n📣 {phase_name} ({phase_time//60} minutes)")
                
                # For side speaks
                await ctx.send(f"🎤 {for_user.mention} has the floor...")
                await asyncio.sleep(phase_time // 2)
                await ctx.send(f"⏰ {for_user.mention} has {phase_time//4} seconds remaining...")
                await asyncio.sleep(phase_time // 4)
                
                # Against side speaks
                await ctx.send(f"🎤 {against_user.mention} has the floor...")
                await asyncio.sleep(phase_time // 2)
                await ctx.send(f"⏰ {against_user.mention} has {phase_time//4} seconds remaining...")
                await asyncio.sleep(phase_time // 4)
                
                await ctx.send("⌛ Time's up!")
                
                # Short break between phases
                if phase_id != "closing":
                    await ctx.send("💬 Taking a 30-second break...")
                    await asyncio.sleep(30)
            
            # Generate and send debate summary
            await ctx.send("📝 Generating debate summary...")
            summary = await self.create_debate_summary(debate_data)
            
            # Split summary into chunks if needed
            chunks = [summary[i:i+1900] for i in range(0, len(summary), 1900)]
            for i, chunk in enumerate(chunks):
                await ctx.send(f"Debate Summary (Part {i+1}/{len(chunks)}):\n{chunk}")
            
            await ctx.send("✨ Debate concluded! Thank you for participating!")
            
        except Exception as e:
            await ctx.send(f"❌ Error during debate: {str(e)}")
        finally:
            # Clean up
            if debate_id in self.active_debates:
                del self.active_debates[debate_id] 

    async def process_whiteboard_image(self, image_bytes: bytes) -> str:
        """Process a whiteboard image using Mistral's vision capabilities."""
        # Convert image bytes to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        prompt = """Provide a concise summary of this whiteboard image. Be brief but comprehensive.
        Include only the most important elements:
        • Key topics (2-3 main points)
        • Essential ideas and connections
        • Notable diagrams or visual elements
        • Action items (if any)

        Keep the summary short and focused. Use bullet points for clarity.
        Limit each section to 2-3 bullet points maximum."""
        
        # Create message with proper format for Mistral's vision API
        messages = [
            {
                "role": "system",
                "content": "You are a skilled visual content analyzer. Provide clear, concise summaries focusing only on the most important elements."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please analyze this whiteboard image and provide a brief summary:"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
        
        try:
            response = await self.content_processor.mistral_client.chat.complete_async(
                model="pixtral-12b-2409",
                messages=messages,
                max_tokens=400,  # Reduced from 1000 to enforce brevity
                temperature=0.7,
                top_p=0.95
            )
            
            if not response or not response.choices:
                raise Exception("No response received from the API")
            
            summary = response.choices[0].message.content.strip()
            
            # Ensure summary doesn't exceed 1000 characters
            if len(summary) > 1000:
                summary = summary[:997] + "..."
                
            return summary
            
        except Exception as e:
            print(f"Error processing whiteboard image: {e}")
            import traceback
            print(f"Detailed error:\n{traceback.format_exc()}")
            
            # Provide more specific error message
            if "vision" in str(e).lower():
                raise Exception("Vision model not available. Please contact the bot administrator.")
            elif "validation" in str(e).lower():
                raise Exception("Invalid image format. Please ensure the image is clear and in JPG/PNG format.")
            elif "timeout" in str(e).lower():
                raise Exception("Request timed out. Please try again with a smaller or more compressed image.")
            else:
                raise Exception("Failed to process image. Please try again with a clearer photo.")

    @commands.command(name="start_whiteboard")
    async def start_whiteboard(self, ctx: commands.Context, *, args: str = None):
        """Start a whiteboard brainstorming session.
        Usage: !start_whiteboard "Session Title"
        """
        if not args:
            await ctx.send("❌ Please provide a title for the whiteboard session!\n"
                         "Usage: `!start_whiteboard \"Your Session Title\"`\n"
                         "Example: `!start_whiteboard \"Project Brainstorming\"`")
            return

        # Parse title from args
        if not args.startswith('"') or not args.endswith('"'):
            await ctx.send("❌ Session title must be in quotes!\n"
                         "Example: `!start_whiteboard \"Q4 Planning Session\"`")
            return

        title = args.strip('"')
        if not title:
            await ctx.send("❌ Session title cannot be empty!")
            return
        
        # Check if there's already an active session in this channel
        for session in self.active_whiteboards.values():
            if session["channel_id"] == ctx.channel.id and session["status"] == "active":
                await ctx.send("❌ There's already an active whiteboard session in this channel.\n"
                             "Please end it first with `!end_whiteboard`")
                return
        
        session_id = str(ctx.message.id)
        
        # Create whiteboard session data
        whiteboard_data = {
            "title": title,
            "creator": ctx.author.id,
            "channel_id": ctx.channel.id,
            "images": [],
            "participants": set(),
            "created_at": ctx.message.created_at,
            "status": "active"
        }
        
        self.active_whiteboards[session_id] = whiteboard_data
        
        # Create session announcement embed
        embed = discord.Embed(
            title="🎨 Whiteboard Session",
            description=f"Topic: {title}",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="How to Participate",
            value="1. Take photos of your whiteboard notes\n"
                  "2. Send them in this channel\n"
                  "3. Bot will process and summarize the content\n"
                  "4. Use !end_whiteboard to finish the session",
            inline=False
        )
        embed.add_field(
            name="Tips",
            value="• Ensure good lighting and clear visibility\n"
                  "• Avoid glare and shadows\n"
                  "• Capture one section at a time for better results\n"
                  "• Supported formats: JPG, PNG",
            inline=False
        )
        embed.set_footer(text=f"Session ID: {session_id} | Created by {ctx.author.name}")
        
        await ctx.send(embed=embed)
        await ctx.send("🎨 Whiteboard session started! Send your whiteboard photos when ready.")

    @commands.command(name="end_whiteboard")
    async def end_whiteboard(self, ctx: commands.Context):
        """End the current whiteboard session and generate a comprehensive summary."""
        # Find the active session in this channel
        session_id = None
        session_data = None
        
        for sid, data in self.active_whiteboards.items():
            if data["channel_id"] == ctx.channel.id and data["status"] == "active":
                session_id = sid
                session_data = data
                break
        
        if not session_data:
            await ctx.send("❌ No active whiteboard session found in this channel.")
            return
        
        try:
            await ctx.send("📝 Generating comprehensive summary of all whiteboard content...")
            
            if not session_data["images"]:
                await ctx.send("❌ No whiteboard images were captured in this session.")
                return
            
            # Process all images and combine summaries
            summaries = []
            for i, image_bytes in enumerate(session_data["images"], 1):
                await ctx.send(f"Processing image {i}/{len(session_data['images'])}...")
                try:
                    summary = await self.process_whiteboard_image(image_bytes)
                    summaries.append(summary)
                except Exception as e:
                    await ctx.send(f"⚠️ Error processing image {i}: {str(e)}")
            
            # Create final summary with a more concise format
            final_summary = f"# {session_data['title']}\n\n"
            for i, summary in enumerate(summaries, 1):
                final_summary += f"## Image {i}\n{summary}\n\n"
            
            # Split and send summary in chunks
            chunks = [final_summary[i:i+1900] for i in range(0, len(final_summary), 1900)]
            for i, chunk in enumerate(chunks):
                await ctx.send(f"```md\n{chunk}\n```")
            
            # Create a final embed with session statistics
            embed = discord.Embed(
                title="📊 Session Summary",
                description=f"Whiteboard Session: {session_data['title']}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Statistics",
                value=f"• Duration: {(ctx.message.created_at - session_data['created_at']).seconds // 60} minutes\n"
                      f"• Images Processed: {len(session_data['images'])}\n"
                      f"• Participants: {len(session_data['participants'])}",
                inline=False
            )
            
            await ctx.send(embed=embed)
            await ctx.send("✨ Whiteboard session concluded!")
            
            # Clean up
            session_data["status"] = "completed"
            
        except Exception as e:
            await ctx.send(f"❌ Error ending whiteboard session: {str(e)}")
        finally:
            if session_id in self.active_whiteboards:
                del self.active_whiteboards[session_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle image uploads during whiteboard sessions."""
        # Skip if message is from a bot or has no attachments
        if message.author.bot or not message.attachments:
            return
        
        # Check if there's an active whiteboard session in this channel
        session_data = None
        for data in self.active_whiteboards.values():
            if data["channel_id"] == message.channel.id and data["status"] == "active":
                session_data = data
                break
        
        if not session_data:
            return
        
        # Process image attachments
        for attachment in message.attachments:
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                continue
            
            # Check if format is supported
            if not any(attachment.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
                await message.channel.send("⚠️ Only JPG and PNG images are supported.")
                continue
            
            try:
                # Download and process the image
                image_bytes = await attachment.read()
                
                # Save the image data
                session_data["images"].append(image_bytes)
                session_data["participants"].add(message.author.id)
                
                # Process and provide immediate feedback
                processing_msg = await message.channel.send("🔍 Processing whiteboard image...")
                try:
                    summary = await self.process_whiteboard_image(image_bytes)
                    
                    # Send the summary in an embed
                    embed = discord.Embed(
                        title="📝 Whiteboard Content Summary",
                        description=summary,
                        color=discord.Color.blue()
                    )
                    embed.set_thumbnail(url=attachment.url)
                    embed.add_field(
                        name="Image Info",
                        value=f"• Size: {attachment.size // 1024}KB\n"
                              f"• Format: {attachment.content_type.split('/')[-1].upper()}\n"
                              f"• Captured by: {message.author.name}",
                        inline=False
                    )
                    
                    await processing_msg.delete()
                    await message.channel.send(embed=embed)
                    
                except Exception as e:
                    await processing_msg.edit(content=f"⚠️ Error processing image: {str(e)}\n"
                                                    "Try taking another photo with better lighting and clarity.")
                
            except Exception as e:
                await message.channel.send(f"⚠️ Error handling image: {str(e)}")

    async def generate_flashcards(self, content: str, num_cards: int = 10) -> List[Dict[str, str]]:
        """Generate flashcards from content using Mistral."""
        try:
            # Create a prompt for flashcard generation
            prompt = f"""Create {num_cards} educational flashcards from this content. 
            Each flashcard should have:
            1. A clear, concise question
            2. A comprehensive but focused answer
            3. A difficulty level (1-3)
            4. A category/topic tag

            Format each flashcard exactly as:
            {{
                "question": "The question text",
                "answer": "The answer text",
                "difficulty": difficulty_level,
                "category": "topic_tag"
            }}

            Content to process:
            {content}

            Return the flashcards as a valid JSON array."""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert educator who creates effective, engaging flashcards for learning."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            response = await self.content_processor.mistral_client.chat.complete_async(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.7
            )

            # Parse the response into flashcards
            response_text = response.choices[0].message.content
            # Extract JSON array from response (handle potential text before/after JSON)
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No valid JSON array found in response")
            
            flashcards_json = response_text[json_start:json_end]
            flashcards = json.loads(flashcards_json)

            # Validate flashcard format
            for card in flashcards:
                required_fields = ["question", "answer", "difficulty", "category"]
                if not all(field in card for field in required_fields):
                    raise ValueError(f"Missing required fields in flashcard: {card}")
                if not isinstance(card["difficulty"], int) or not 1 <= card["difficulty"] <= 3:
                    card["difficulty"] = 1  # Default to easy if invalid

            return flashcards

        except Exception as e:
            print(f"Error generating flashcards: {e}")
            return []

    @commands.command(name="create_flashcards")
    async def create_flashcards(self, ctx: commands.Context, source_type: str = None, num_cards: int = 10, message_limit: int = 50):
        """Convert documents or discussion into digital flashcards for learning.
        Usage:
        - PDF: !create_flashcards pdf [num_cards] (with PDF attachment)
        - TXT: !create_flashcards txt [num_cards] (with TXT attachment)
        - Discussion: !create_flashcards discussion [num_cards] [message_limit]
        """
        if not source_type or source_type.lower() not in ["pdf", "txt", "discussion"]:
            await ctx.send("❌ Please specify the source type (pdf, txt, or discussion)!\n"
                         "Usage:\n"
                         "• `!create_flashcards pdf [num_cards]` (with PDF attachment)\n"
                         "• `!create_flashcards txt [num_cards]` (with TXT attachment)\n"
                         "• `!create_flashcards discussion [num_cards] [message_limit]`")
            return

        try:
            content = None
            source_name = None

            if source_type.lower() == "discussion":
                # Process discussion messages
                await ctx.send(f"📝 Extracting last {message_limit} messages from discussion...")
                messages = []
                async for message in ctx.channel.history(limit=message_limit):
                    if not message.author.bot:  # Skip bot messages
                        messages.append(message)
                
                if not messages:
                    await ctx.send("❌ No messages found in the discussion.")
                    return
                
                # Extract content from messages
                content = "\n".join([f"{msg.author.name}: {msg.content}" for msg in messages])
                source_name = f"Discussion in #{ctx.channel.name}"
                
            else:
                # Handle file-based sources (PDF and TXT)
                if not ctx.message.attachments:
                    await ctx.send("❌ Please attach a file!")
                    return

                file = ctx.message.attachments[0]
                
                # Validate file type
                if source_type.lower() == "pdf" and not file.filename.lower().endswith(".pdf"):
                    await ctx.send("❌ Please attach a PDF file!")
                    return
                elif source_type.lower() == "txt" and not file.filename.lower().endswith(".txt"):
                    await ctx.send("❌ Please attach a TXT file!")
                    return

                # Download and process the file
                file_bytes = await file.read()
                
                # Process content based on file type
                if source_type.lower() == "pdf":
                    content = await self.content_processor.process_pdf(file_bytes)
                else:  # txt
                    content = file_bytes.decode("utf-8")
                
                source_name = file.filename

            if not content:
                await ctx.send("❌ No content found to process.")
                return

            # Generate flashcards
            await ctx.send("📚 Generating flashcards...")
            flashcards = await self.generate_flashcards(content, num_cards)

            if not flashcards:
                await ctx.send("❌ Failed to generate flashcards. Please try again.")
                return

            # Create flashcard set
            set_id = str(ctx.message.id)
            flashcard_set = {
                "title": source_name,
                "creator": ctx.author.id,
                "created_at": ctx.message.created_at,
                "cards": flashcards,
                "current_card": 0,
                "current_message": None,
                "channel_id": ctx.channel.id,
                "stats": {
                    "correct": 0,
                    "incorrect": 0,
                    "cards_reviewed": set()
                }
            }
            
            self.active_flashcard_sets[set_id] = flashcard_set

            # Create initial embed
            embed = discord.Embed(
                title="📝 Flashcard Set Created",
                description=f"From: {source_name}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Statistics",
                value=f"• Total Cards: {len(flashcards)}\n"
                      f"• Categories: {len(set(card['category'] for card in flashcards))}\n"
                      f"• Difficulty Range: {min(card['difficulty'] for card in flashcards)}-"
                      f"{max(card['difficulty'] for card in flashcards)}",
                inline=False
            )
            embed.add_field(
                name="Controls",
                value="Use reactions to interact:\n"
                      "🔄 Show Answer\n"
                      "⏭️ Next Card\n"
                      "✅ Mark Correct\n"
                      "❌ Mark Incorrect\n"
                      "🏁 End Session",
                inline=False
            )

            await ctx.send(embed=embed)
            
            # Show first card
            await self.show_flashcard(ctx, set_id)

        except Exception as e:
            await ctx.send(f"❌ Error creating flashcards: {str(e)}")

    async def show_flashcard(self, ctx: commands.Context, set_id: str, show_answer: bool = False):
        """Display the current flashcard."""
        flashcard_set = self.active_flashcard_sets.get(set_id)
        if not flashcard_set:
            await ctx.send("❌ Flashcard set not found.")
            return

        current_card = flashcard_set["cards"][flashcard_set["current_card"]]
        
        embed = discord.Embed(
            title=f"Flashcard {flashcard_set['current_card'] + 1}/{len(flashcard_set['cards'])}",
            color=discord.Color.blue()
        )
        
        # Show question
        embed.add_field(
            name="Question",
            value=current_card["question"],
            inline=False
        )
        
        # Show answer if requested
        if show_answer:
            embed.add_field(
                name="Answer",
                value=current_card["answer"],
                inline=False
            )
        
        # Add metadata
        embed.add_field(
            name="Details",
            value=f"• Category: {current_card['category']}\n"
                  f"• Difficulty: {'🟢' if current_card['difficulty'] == 1 else '🟡' if current_card['difficulty'] == 2 else '🔴'}",
            inline=False
        )

        # Add instructions for reactions
        if not show_answer:
            embed.add_field(
                name="Controls",
                value="🔄 Show Answer | ⏭️ Next Card | ✅ Correct | ❌ Incorrect | 🏁 End Session",
                inline=False
            )
        
        # Send card and add reactions
        card_msg = await ctx.send(embed=embed)
        
        # Store message ID for reaction handling
        flashcard_set["current_message"] = card_msg.id
        
        # Add reactions for controls
        if not show_answer:
            await card_msg.add_reaction("🔄")  # Show answer
        await card_msg.add_reaction("⏭️")  # Next card
        await card_msg.add_reaction("✅")   # Mark correct
        await card_msg.add_reaction("❌")   # Mark incorrect
        await card_msg.add_reaction("🏁")   # End session

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reactions for flashcard navigation."""
        if user.bot:  # Ignore bot reactions
            return

        # Find active flashcard set for this message
        set_id = None
        flashcard_set = None
        for sid, data in self.active_flashcard_sets.items():
            if data.get("current_message") == reaction.message.id:
                set_id = sid
                flashcard_set = data
                break

        if not flashcard_set:
            return

        # Get the channel
        channel = reaction.message.channel
        
        # Handle different reactions
        emoji = str(reaction.emoji)
        if emoji == "🔄":  # Show answer
            await self.show_flashcard(channel, set_id, show_answer=True)
        elif emoji == "⏭️":  # Next card
            flashcard_set["current_card"] = (flashcard_set["current_card"] + 1) % len(flashcard_set["cards"])
            await self.show_flashcard(channel, set_id)
        elif emoji == "✅":  # Mark correct
            current_card_idx = flashcard_set["current_card"]
            flashcard_set["stats"]["correct"] += 1
            flashcard_set["stats"]["cards_reviewed"].add(current_card_idx)
            await channel.send("✅ Marked as correct!")
            # Move to next card
            flashcard_set["current_card"] = (flashcard_set["current_card"] + 1) % len(flashcard_set["cards"])
            await self.show_flashcard(channel, set_id)
        elif emoji == "❌":  # Mark incorrect
            current_card_idx = flashcard_set["current_card"]
            flashcard_set["stats"]["incorrect"] += 1
            flashcard_set["stats"]["cards_reviewed"].add(current_card_idx)
            await channel.send("❌ Marked as incorrect!")
            # Move to next card
            flashcard_set["current_card"] = (flashcard_set["current_card"] + 1) % len(flashcard_set["cards"])
            await self.show_flashcard(channel, set_id)
        elif emoji == "🏁":  # End session
            await self.end_flashcard_session(channel, set_id)

    async def end_flashcard_session(self, channel: discord.TextChannel, set_id: str):
        """End a flashcard session and show statistics."""
        try:
            flashcard_set = self.active_flashcard_sets[set_id]
            stats = flashcard_set["stats"]
            
            # Calculate statistics
            total_reviewed = len(stats["cards_reviewed"])
            accuracy = (stats["correct"] / (stats["correct"] + stats["incorrect"])) * 100 if stats["correct"] + stats["incorrect"] > 0 else 0
            
            # Create summary embed
            embed = discord.Embed(
                title="📊 Flashcard Session Summary",
                description=f"Set: {flashcard_set['title']}",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Statistics",
                value=f"• Cards Reviewed: {total_reviewed}/{len(flashcard_set['cards'])}\n"
                      f"• Correct Answers: {stats['correct']}\n"
                      f"• Incorrect Answers: {stats['incorrect']}\n"
                      f"• Accuracy: {accuracy:.1f}%",
                inline=False
            )
            
            # Add difficulty breakdown
            difficulty_reviewed = {1: 0, 2: 0, 3: 0}
            for idx in stats["cards_reviewed"]:
                card = flashcard_set["cards"][idx]
                difficulty_reviewed[card["difficulty"]] += 1
            
            embed.add_field(
                name="Difficulty Breakdown",
                value=f"• Easy (🟢): {difficulty_reviewed[1]} cards\n"
                      f"• Medium (🟡): {difficulty_reviewed[2]} cards\n"
                      f"• Hard (🔴): {difficulty_reviewed[3]} cards",
                inline=False
            )
            
            await channel.send(embed=embed)
            
            # Clean up
            del self.active_flashcard_sets[set_id]
            
        except Exception as e:
            await channel.send(f"❌ Error ending flashcard session: {str(e)}")