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
        
        # Store active quizzes
        self.active_quizzes = {}

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
    
    @commands.command(name="create_quiz")
    async def create_quiz(self, ctx: commands.Context, source_type: str = "discussion", message_limit: int = 50, num_questions: int = 5):
        """Create an interactive quiz from a document or discussion.
        Usage:
        - With PDF: Attach a PDF and use '!create_quiz pdf [num_questions]'
        - With discussion: Use '!create_quiz discussion [message_limit] [num_questions]'
        """
        try:
            await ctx.send("📝 Starting quiz creation...")
            
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
                messages = []
                async for message in ctx.channel.history(limit=message_limit):
                    messages.append(message)
                content = await self.content_processor.extract_discussion(messages)
                await ctx.send(f"💬 Extracted {len(messages)} messages from discussion.")
                
            else:
                await ctx.send("Invalid source type. Use 'pdf' or 'discussion'.")
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