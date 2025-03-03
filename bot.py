import os
import discord
import logging
from discord.ext import commands
from dotenv import load_dotenv
from mistralai import Mistral
from processors.content_processor import ContentProcessor
from processors.audio_generator import AudioGenerator
from utils.storage import FileStorage
from handlers.commands import CommandHandler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord")

# Load environment variables
load_dotenv()

# Create the bot with all intents
# The message content and members intent must be enabled in the Discord Developer Portal for the bot to work.
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize components
mistral_client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
storage = FileStorage()
content_processor = ContentProcessor(mistral_client)
audio_generator = AudioGenerator()

@bot.event
async def on_ready():
    """
    Called when the client is done preparing the data received from Discord.
    Prints message on terminal when bot successfully connects to discord.

    https://discordpy.readthedocs.io/en/latest/api.html#discord.on_ready
    """
    logger.info(f"{bot.user} has connected to Discord!")
    
    # Add command handler
    command_handler = CommandHandler(bot, content_processor, audio_generator, storage)
    await bot.add_cog(command_handler)
    
    # Log available commands
    commands_list = [command.name for command in bot.commands]
    logger.info(f"Registered commands: {', '.join(commands_list)}")

@bot.event
async def on_message(message: discord.Message):
    """Called when a message is sent in any channel the bot can see."""
    # Don't delete this line! It's necessary for the bot to process commands.
    await bot.process_commands(message)

    # Ignore messages from self or other bots to prevent infinite loops,
    # or if the message starts with the command prefix
    if message.author.bot or message.content.startswith("!"):
        return

    # Only respond if the bot is mentioned or the message is a reply to the bot's message
    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author.id == bot.user.id

    if is_mentioned or is_reply_to_bot:
        try:
            # Process the message content
            response = await content_processor.summarize_content(message.content)
            await message.reply(response)
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            await message.reply("Sorry, I encountered an error while processing your message.")

# Commands

# This example command is here to show you how to add commands to the bot.
# Run !ping with any number of arguments to see the command in action.
# Feel free to delete this if your project will not need commands.
@bot.command(name="ping", help="Pings the bot.")
async def ping(ctx, *, arg=None):
    if arg is None:
        await ctx.send("Pong!")
    else:
        await ctx.send(f"Pong! Your argument was {arg}")

# Get the token from environment variables
token = os.getenv("DISCORD_TOKEN")

# Start the bot, connecting it to the gateway
bot.run(token)
