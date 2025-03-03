import discord
from discord.ext import commands
from typing import Optional, List, Tuple
from processors.content_processor import ContentProcessor
from processors.audio_generator import AudioGenerator
from utils.storage import FileStorage
import io
import asyncio
from pydub import AudioSegment
import tempfile
import os

class CommandHandler(commands.Cog):
    def __init__(self, bot: commands.Bot, content_processor: ContentProcessor, 
                 audio_generator: AudioGenerator, storage: FileStorage):
        self.bot = bot
        self.content_processor = content_processor
        self.audio_generator = audio_generator
        self.storage = storage
        # Default voices for podcast hosts - using Josh for both as fallback
        self.host1_voice = "21m00Tcm4TlvDq8ikWAM"  # Josh
        self.host2_voice = "21m00Tcm4TlvDq8ikWAM"  # Josh (fallback)
        
        # Initialize voices asynchronously
        self.bot.loop.create_task(self.initialize_voices())
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 2  # seconds between requests

    async def initialize_voices(self):
        """Initialize available voices for the podcast hosts."""
        try:
            voices = await self.audio_generator.list_voices()
            # Look for a female voice as second host
            female_voices = [v for v in voices if v.get("labels", {}).get("gender") == "female"]
            if female_voices:
                self.host2_voice = female_voices[0]["voice_id"]
            print(f"Available voices: {[v['name'] for v in voices]}")
        except Exception as e:
            print(f"Warning: Could not initialize voices, using fallback. Error: {str(e)}")

    async def generate_podcast_script(self, content: str) -> List[Tuple[str, str]]:
        """Generate a conversational podcast script from content."""
        try:
            # First, get a detailed summary of the content
            summary = await self.content_processor.summarize_content(content)
            
            # Now, create a podcast script prompt
            script_prompt = f"""You are creating a natural, engaging podcast script between two hosts discussing the following content.

            Requirements:
            1. The hosts are Alex and Rachel
            2. Format each line exactly as "Alex: [dialogue]" or "Rachel: [dialogue]"
            3. Make it conversational and engaging, with natural back-and-forth
            4. Include reactions, questions, and insights
            5. Keep it to 2-5 minutes in length (about 6-10 exchanges)
            6. Start with an introduction and end with a conclusion
            7. Break down complex topics into digestible segments

            Content to discuss:
            {summary}

            Begin the script now, using only the Alex: and Rachel: format for every line:"""
            
            # Get the script from Mistral
            messages = [
                {
                    "role": "system", 
                    "content": "You are a professional podcast script writer who creates engaging, natural dialogue between two hosts."
                },
                {
                    "role": "user", 
                    "content": script_prompt
                }
            ]
            
            response = await self.content_processor.mistral_client.chat.complete_async(
                model="mistral-large-latest",
                messages=messages,
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

    @commands.command(name="create_podcast")
    async def create_podcast(self, ctx: commands.Context, source_type: str = "discussion", message_limit: int = 50):
        """Create a podcast from a document or discussion.
        Usage: 
        - With PDF: Attach a PDF and use '!create_podcast pdf'
        - With discussion: Use '!create_podcast discussion [message_limit]'
        """
        try:
            await ctx.send("🎙️ Starting podcast creation...")
            
            # Get source content
            if source_type.lower() == "pdf":
                if not ctx.message.attachments:
                    await ctx.send("Please attach a PDF file!")
                    return
                
                attachment = ctx.message.attachments[0]
                if not attachment.filename.lower().endswith('.pdf'):
                    await ctx.send("Please attach a valid PDF file!")
                    return
                
                pdf_bytes = await attachment.read()
                pdf_file = io.BytesIO(pdf_bytes)
                content = await self.content_processor.process_pdf(pdf_file)
                await ctx.send("📄 PDF processed successfully.")
                
            elif source_type.lower() == "discussion":
                messages: List[discord.Message] = []
                async for message in ctx.channel.history(limit=message_limit):
                    messages.append(message)
                content = await self.content_processor.extract_discussion(messages)
                await ctx.send(f"💬 Extracted {len(messages)} messages from discussion.")
                
            else:
                await ctx.send("Invalid source type. Use 'pdf' or 'discussion'.")
                return
            
            await ctx.send("📝 Generating podcast script...")
            dialogue = await self.generate_podcast_script(content)
            
            if not dialogue:
                await ctx.send("❌ Error: Script generation failed. Trying one more time...")
                dialogue = await self.generate_podcast_script(content[:2000])
                
                if not dialogue:
                    await ctx.send("❌ Error: Failed to generate a valid podcast script. Please try again with different content.")
                    return
                
            await ctx.send(f"✅ Generated script with {len(dialogue)} segments.")
            
            # Send the script in chunks
            script_text = "📜 Podcast Script:\n\n"
            for speaker, text in dialogue:
                script_text += f"{speaker}: {text}\n\n"
            
            chunks = [script_text[i:i+1900] for i in range(0, len(script_text), 1900)]
            for i, chunk in enumerate(chunks):
                await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
            
            await ctx.send("🎵 Generating audio... This might take a few minutes.")
            
            # Generate audio for each line of dialogue
            audio_segments = []
            temp_files = []  # Keep track of temporary files
            
            try:
                combined_audio = AudioSegment.empty()
                retry_count = 0
                
                for i, (speaker, text) in enumerate(dialogue):
                    try:
                        await ctx.send(f"🎙️ Generating audio for segment {i+1}/{len(dialogue)} ({speaker})...")
                        
                        # Add delay between requests to avoid rate limits
                        now = asyncio.get_event_loop().time()
                        time_since_last = now - self.last_request_time
                        if time_since_last < self.min_request_interval:
                            await asyncio.sleep(self.min_request_interval - time_since_last)
                        
                        # Select voice based on speaker
                        voice_id = self.host1_voice if speaker == "Alex" else self.host2_voice
                        
                        # Generate audio with retry logic
                        max_retries = 3
                        retry_delay = 5  # seconds
                        
                        for attempt in range(max_retries):
                            try:
                                audio_data = await self.audio_generator.generate_audio(text, voice_id)
                                if audio_data:
                                    break
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    await ctx.send(f"⚠️ Retrying segment {i+1} in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                                    await asyncio.sleep(retry_delay)
                                    retry_delay *= 2  # Exponential backoff
                                else:
                                    raise e
                        
                        self.last_request_time = asyncio.get_event_loop().time()
                        
                        if not audio_data:
                            await ctx.send(f"⚠️ Warning: No audio generated for segment {i+1}")
                            continue
                        
                        # Save to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                            temp_file.write(audio_data)
                            temp_files.append(temp_file.name)
                        
                        # Add to combined audio with a short pause between segments
                        segment_audio = AudioSegment.from_mp3(temp_files[-1])
                        if len(combined_audio) > 0:
                            combined_audio += AudioSegment.silent(duration=700)  # 0.7 second pause
                        combined_audio += segment_audio
                        
                    except Exception as e:
                        await ctx.send(f"⚠️ Error generating segment {i+1}: {str(e)}")
                        retry_count += 1
                        if retry_count >= 3:
                            await ctx.send("❌ Too many errors, stopping audio generation.")
                            break
                        continue
                
                if len(combined_audio) > 0:
                    # Save the combined audio
                    output_path = self.storage.audio_dir / f"podcast_{ctx.message.id}_combined.mp3"
                    combined_audio.export(str(output_path), format="mp3")
                    
                    # Send the combined audio file
                    await ctx.send("🎙️ Here's your podcast:", file=discord.File(str(output_path)))
                    await ctx.send("✨ Podcast creation complete!")
                else:
                    await ctx.send("❌ Error: No audio segments were generated successfully.")
                
            finally:
                # Clean up temporary files
                for temp_file in temp_files:
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            
        except Exception as e:
            await ctx.send(f"❌ Error creating podcast: {str(e)}")
            import traceback
            await ctx.send(f"Detailed error:\n```{traceback.format_exc()}```")
    
    @commands.command(name="summarize_pdf")
    async def summarize_pdf(self, ctx: commands.Context, max_words: Optional[int] = None):
        """Summarize a PDF file attached to the message."""
        if not ctx.message.attachments:
            await ctx.send("Please attach a PDF file to summarize!")
            return
        
        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith('.pdf'):
            await ctx.send("Please attach a valid PDF file!")
            return
        
        try:
            # Download and process PDF
            pdf_bytes = await attachment.read()
            pdf_file = io.BytesIO(pdf_bytes)
            
            # Save PDF (synchronously)
            pdf_path = self.storage.save_pdf(pdf_bytes, attachment.filename)
            
            # Extract and summarize text
            await ctx.send("Processing PDF...")
            text = await self.content_processor.process_pdf(pdf_file)
            summary = await self.content_processor.summarize_content(text, max_words)
            
            # Split summary into chunks of 1900 characters (leaving room for formatting)
            chunks = [summary[i:i+1900] for i in range(0, len(summary), 1900)]
            
            # Send the first chunk with the file name
            await ctx.send(f"Summary of {attachment.filename} (Part 1/{len(chunks)}):\n{chunks[0]}")
            
            # Send remaining chunks if any
            for i, chunk in enumerate(chunks[1:], 2):
                await ctx.send(f"Part {i}/{len(chunks)}:\n{chunk}")
                
        except Exception as e:
            await ctx.send(f"Error processing PDF: {str(e)}")
    
    @commands.command(name="summarize_discussion")
    async def summarize_discussion(self, ctx: commands.Context, message_limit: int = 50):
        """Summarize recent discussion in the channel."""
        # Extract messages using async for
        messages: List[discord.Message] = []
        async for message in ctx.channel.history(limit=message_limit):
            messages.append(message)
        
        try:
            # Extract and summarize discussion
            await ctx.send("Processing discussion...")
            discussion = await self.content_processor.extract_discussion(messages)
            summary = await self.content_processor.summarize_content(discussion)
            
            # Split summary into chunks if needed
            chunks = [summary[i:i+1900] for i in range(0, len(summary), 1900)]
            
            # Send the first chunk
            await ctx.send(f"Discussion Summary (Part 1/{len(chunks)}):\n{chunks[0]}")
            
            # Send remaining chunks if any
            for i, chunk in enumerate(chunks[1:], 2):
                await ctx.send(f"Part {i}/{len(chunks)}:\n{chunk}")
                
        except Exception as e:
            await ctx.send(f"Error processing discussion: {str(e)}")
    
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
    
    @commands.command(name="list_voices")
    async def list_voices(self, ctx: commands.Context):
        """List available voices from Eleven Labs."""
        try:
            voices = await self.audio_generator.list_voices()
            voice_list = "\n".join([f"- {voice['name']} (ID: {voice['voice_id']})" for voice in voices])
            await ctx.send(f"Available voices:\n{voice_list}")
        except Exception as e:
            await ctx.send(f"Error fetching voices: {str(e)}")
    
    @commands.command(name="cleanup")
    @commands.has_permissions(administrator=True)
    async def cleanup(self, ctx: commands.Context, hours: int = 48):
        """Clean up old files (admin only)."""
        try:
            self.storage.cleanup_old_files(hours)
            await ctx.send(f"Cleaned up files older than {hours} hours.")
        except Exception as e:
            await ctx.send(f"Error during cleanup: {str(e)}") 