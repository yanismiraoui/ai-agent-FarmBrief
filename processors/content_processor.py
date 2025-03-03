import PyPDF2
from io import BytesIO
from typing import List, Optional
from pathlib import Path
import discord
from mistralai import Mistral

class ContentProcessor:
    def __init__(self, mistral_client: Mistral):
        self.mistral_client = mistral_client
        
    async def process_pdf(self, pdf_file: BytesIO) -> str:
        """Extract text from a PDF file."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    async def extract_discussion(self, messages: List[discord.Message], limit: int = 50) -> str:
        """Extract text from a Discord discussion."""
        discussion = []
        for message in messages[:limit]:
            if not message.author.bot and not message.content.startswith('!'):  # Skip bot messages and commands
                # Format: [Timestamp] Username: Message
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M")
                discussion.append(f"[{timestamp}] {message.author.name}: {message.content}")
        
        # Reverse the list so it's in chronological order (oldest first)
        discussion.reverse()
        print(discussion)
        
        if not discussion:
            return "No messages found in the discussion."
            
        # Join with newlines and add a header
        return "Discussion History:\n\n" + "\n".join(discussion)
    
    async def summarize_content(self, content: str, max_length: Optional[int] = None) -> str:
        """Summarize content using Mistral AI."""
        prompt = f"""Please provide a clear and comprehensive summary of the following content. 
        {f'The summary should be no longer than {max_length} words.' if max_length else ''}
        
        Focus on:
        1. Key topics and themes
        2. Main points of discussion
        3. Important conclusions or decisions
        4. Relevant context and details
        
        Content to summarize:
        {content}
        """
        
        messages = [
            {
                "role": "system", 
                "content": "You are a skilled content analyst who provides clear, accurate, and well-structured summaries."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ]
        
        try:
            response = await self.mistral_client.chat.complete_async(
                model="mistral-large-latest",
                messages=messages,
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error in summarize_content: {str(e)}")
            raise 