import PyPDF2
from io import BytesIO
from typing import List, Optional, Dict, Any
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
    
    async def generate_quiz_questions(self, content: str, num_questions: int = 5) -> List[Dict[str, Any]]:
        """Generate quiz questions from content."""
        prompt = f"""Create exactly {num_questions} multiple-choice quiz questions based on the following content.
        
        Format your response EXACTLY as a JSON object with this structure:
        {{
            "questions": [
                {{
                    "question": "Question text here?",
                    "options": {{
                        "A": "First option",
                        "B": "Second option",
                        "C": "Third option",
                        "D": "Fourth option"
                    }},
                    "correct": "A",
                    "explanation": "Explanation why A is correct"
                }}
            ]
        }}

        Requirements:
        1. Response MUST be valid JSON
        2. Each question MUST have exactly 4 options (A, B, C, D)
        3. Questions should be engaging and varied in difficulty
        4. Include both factual and analytical questions
        5. Keep questions focused on the main points from the content

        Content to create questions from:
        {content}

        Remember: Your entire response must be a valid JSON object matching the format above."""

        messages = [
            {
                "role": "system",
                "content": "You are a professional quiz creator. You MUST format your response as valid JSON matching the specified structure exactly."
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
            
            response_text = response.choices[0].message.content.strip()
            
            # Try to find JSON content if it's wrapped in other text
            try:
                import json
                quiz_data = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from the response if it's not pure JSON
                import re
                json_match = re.search(r'({[\s\S]*})', response_text)
                if json_match:
                    try:
                        quiz_data = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        print(f"Failed to parse JSON from extracted content: {json_match.group(1)}")
                        raise
                else:
                    print(f"No JSON-like content found in response: {response_text}")
                    raise ValueError("Response does not contain valid JSON")

            # Validate the quiz data structure
            if not isinstance(quiz_data, dict) or "questions" not in quiz_data:
                raise ValueError("Invalid quiz data structure: missing 'questions' key")
            
            questions = quiz_data["questions"]
            if not isinstance(questions, list) or len(questions) == 0:
                raise ValueError("Invalid quiz data structure: 'questions' must be a non-empty list")
            
            # Validate each question
            for q in questions:
                required_keys = ["question", "options", "correct", "explanation"]
                if not all(key in q for key in required_keys):
                    raise ValueError(f"Question missing required keys: {required_keys}")
                if not isinstance(q["options"], dict) or len(q["options"]) != 4:
                    raise ValueError("Each question must have exactly 4 options")
                if not all(opt in q["options"] for opt in ["A", "B", "C", "D"]):
                    raise ValueError("Options must be labeled A, B, C, D")
                if q["correct"] not in ["A", "B", "C", "D"]:
                    raise ValueError("Correct answer must be A, B, C, or D")

            return questions
            
        except Exception as e:
            print(f"Error generating quiz questions: {str(e)}")
            print(f"Raw response: {response_text if 'response_text' in locals() else 'No response generated'}")
            return [] 