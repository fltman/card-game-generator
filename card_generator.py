from openai import AsyncOpenAI
import json
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io
import aiohttp
import tempfile
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph
from markdown import markdown
import re
from bs4 import BeautifulSoup
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase.pdfmetrics import registerFont, registerFontFamily
import asyncio

class CardGenerator:
    def __init__(self, api_key):
        self.client = AsyncOpenAI(api_key=api_key)
        self.cards_per_page = 9  # 3x3 grid
        self.card_width = A4[0] / 3
        self.card_height = A4[1] / 3
        
        # Register fonts
        pdfmetrics.registerFont(pdfmetrics.Font('Helvetica', 'Helvetica', 'WinAnsiEncoding'))
        pdfmetrics.registerFont(pdfmetrics.Font('Helvetica-Bold', 'Helvetica-Bold', 'WinAnsiEncoding'))
        pdfmetrics.registerFontFamily(
            'Helvetica',
            normal='Helvetica',
            bold='Helvetica-Bold',
            italic='Helvetica',  # Fallback to normal since we don't have italic
            boldItalic='Helvetica-Bold'  # Fallback to bold
        )
        
        # Define functions for GPT-4o
        self.rules_functions = [
            {
                "name": "define_game_rules",
                "description": "Define the rules and card specifications for a card game",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_title": {
                            "type": "string",
                            "description": "The title of the card game"
                        },
                        "objective": {
                            "type": "string",
                            "description": "The main objective of the game"
                        },
                        "cards": {
                            "type": "object",
                            "description": "Specification of all card types and their quantities",
                            "properties": {
                                "card_types": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "type": {
                                                "type": "string",
                                                "description": "The type of card (e.g., Action, Item)"
                                            },
                                            "quantity": {
                                                "type": "integer",
                                                "description": "Number of cards of this type"
                                            },
                                            "description": {
                                                "type": "string",
                                                "description": "Description of what this type of card does"
                                            }
                                        }
                                    }
                                },
                                "total_cards": {
                                    "type": "integer",
                                    "description": "Total number of cards in the game"
                                }
                            }
                        },
                        "setup": {
                            "type": "string",
                            "description": "How to set up the game"
                        },
                        "gameplay": {
                            "type": "string",
                            "description": "How to play the game"
                        },
                        "winning_conditions": {
                            "type": "string",
                            "description": "How to win the game"
                        }
                    },
                    "required": ["game_title", "objective", "cards", "setup", "gameplay", "winning_conditions"]
                }
            }
        ]
        
        # Define card generation functions
        self.card_functions = [
            {
                "name": "generate_card",
                "description": "Generate content for a game card",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "The title of the card"
                        },
                        "type": {
                            "type": "string",
                            "description": "The type of card (e.g., Action, Item)"
                        },
                        "description": {
                            "type": "string",
                            "description": "The card's effect or description"
                        },
                        "image_prompt": {
                            "type": "string",
                            "description": "A detailed prompt for DALL-E to generate the card's background image"
                        }
                    },
                    "required": ["title", "type", "description", "image_prompt"]
                }
            }
        ]

    async def generate_game_rules(self, game_concept):
        print("DEBUG: Preparing to call OpenAI API for rules generation")
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": """You are a professional card game designer. 
                    Create clear, concise rules for a card-only game (no board, no dice, just cards).
                    Design a balanced and engaging game with an appropriate number of cards."""},
                    {"role": "user", "content": f"Create rules for this card game concept: {game_concept}"}
                ],
                functions=self.rules_functions,
                function_call={"name": "define_game_rules"}
            )
            
            print("DEBUG: Received response from OpenAI")
            function_args = json.loads(response.choices[0].message.function_call.arguments)
            
            print(f"DEBUG: Card distribution: {json.dumps(function_args['cards'], indent=2)}")
            
            # Store card specifications for later use
            self.card_specs = function_args['cards']['card_types']
            
            # Format rules for PDF
            rules_text = self._format_rules_for_pdf(function_args)
            return rules_text, function_args['cards']['card_types']
            
        except Exception as e:
            print(f"ERROR in generate_game_rules: {str(e)}")
            print("DEBUG: Full exception:")
            import traceback
            traceback.print_exc()
            raise

    def _format_rules_for_pdf(self, rules_data):
        """Convert structured rules data to markdown format for PDF"""
        return f"""
**{rules_data['game_title']}**

**Objective:**
{rules_data['objective']}

**Components:**
Total Cards: {rules_data['cards']['total_cards']}
{self._format_card_types(rules_data['cards']['card_types'])}

**Setup:**
{rules_data['setup']}

**Gameplay:**
{rules_data['gameplay']}

**Winning Conditions:**
{rules_data['winning_conditions']}
"""

    def _format_card_types(self, card_types):
        return '\n'.join([f"- {card['quantity']} {card['type']} Cards: {card['description']}" 
                         for card in card_types])

    async def generate_cards_content(self, game_concept, num_cards, card_type, max_retries=3):
        for attempt in range(max_retries):
            try:
                print(f"DEBUG: Starting card generation attempt {attempt + 1} for {card_type['type']}")
                response = await self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system", 
                            "content": f"""You are a card game designer specializing in card-only games. 
                            Generate a {card_type['type']} card that matches this description: {card_type['description']}.
                            For the image_prompt, create a family-friendly, safe-for-work image description.
                            The image should be clear, visually striking, and suitable for a card game.
                            Avoid any potentially controversial or adult themes."""
                        },
                        {"role": "user", "content": f"Generate {num_cards} card(s) for this card-only game concept: {game_concept}"}
                    ],
                    functions=self.card_functions,
                    function_call={"name": "generate_card"}
                )
                
                function_args = json.loads(response.choices[0].message.function_call.arguments)
                print(f"DEBUG: Successfully generated card content on attempt {attempt + 1}")
                return [function_args]
                
            except Exception as e:
                print(f"ERROR in generate_cards_content attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                print("Retrying card generation...")
                await asyncio.sleep(1)  # Wait a bit before retrying

    async def generate_card_background(self, prompt, max_retries=3):
        for attempt in range(max_retries):
            try:
                print(f"DEBUG: Starting background generation attempt {attempt + 1}")
                # Sanitize the prompt to avoid content policy violations
                safe_prompt = f"A family-friendly, cartoon-style illustration for a card game showing: {prompt}"
                
                response = await self.client.images.generate(
                    model="dall-e-3",
                    prompt=safe_prompt,
                    size="1024x1024",
                    quality="standard",
                    n=1
                )
                
                image_url = response.data[0].url
                print(f"DEBUG: Successfully generated image on attempt {attempt + 1}")
                
                # Download and save image
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as img_response:
                        image_data = await img_response.read()
                
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                temp_file.write(image_data)
                temp_file.close()
                return temp_file.name
                
            except Exception as e:
                print(f"ERROR in generate_card_background attempt {attempt + 1}: {str(e)}")
                if attempt == max_retries - 1:
                    # If all retries failed, use a default background
                    print("WARNING: Using fallback background after all retries failed")
                    return self._create_fallback_background()
                print("Retrying background generation...")
                await asyncio.sleep(1)

    def _create_fallback_background(self):
        """Create a simple gradient background when image generation fails"""
        img = Image.new('RGB', (1024, 1024), color='white')
        draw = ImageDraw.Draw(img)
        
        # Create a simple gradient background
        for y in range(1024):
            r = int(255 * (1 - y/1024))
            g = int(200 * (1 - y/1024))
            b = int(255 * (y/1024))
            draw.line([(0, y), (1024, y)], fill=(r, g, b))
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        img.save(temp_file.name)
        temp_file.close()
        return temp_file.name

    def _format_markdown_text(self, markdown_text):
        # Split sections by double newlines
        sections = markdown_text.split('**')
        formatted_text = []
        
        for i, section in enumerate(sections):
            if i % 2 == 0:  # Regular text
                # Handle lists
                lines = section.split('\n')
                for line in lines:
                    if line.strip().startswith('-'):
                        formatted_text.append(f"  • {line.strip()[1:].strip()}")
                    elif line.strip().startswith('1.'):
                        formatted_text.append(f"  {line.strip()}")
                    else:
                        formatted_text.append(line.strip())
            else:  # Bold text (headers)
                formatted_text.append(f"\n{section.strip()}\n")
        
        # Join all text and clean up extra whitespace
        text = '\n'.join(formatted_text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r':\n\n', ':\n', text)  # Fix spacing after colons
        text = text.strip()
        
        return text

    def create_rules_pdf(self, rules, output_file):
        # Format the text
        formatted_rules = self._format_markdown_text(rules)
        
        c = canvas.Canvas(output_file, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # Create custom styles for different text types
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Normal'],
            fontSize=16,
            leading=20,
            spaceBefore=15,
            spaceAfter=10,
            fontName='Helvetica-Bold'
        )
        
        body_style = ParagraphStyle(
            'BodyStyle',
            parent=styles['Normal'],
            fontSize=12,
            leading=14,
            spaceBefore=6,
            spaceAfter=6,
            bulletIndent=20,
            leftIndent=20
        )
        
        # Split into paragraphs and create a story
        story = []
        paragraphs = formatted_rules.split('\n\n')
        
        for para in paragraphs:
            if para.strip().isupper() or '**' in para:  # Headers
                story.append(Paragraph(para.replace('**', ''), header_style))
            else:
                story.append(Paragraph(para, body_style))
        
        # Build the PDF
        current_y = A4[1] - 50
        for element in story:
            w, h = element.wrap(A4[0] - 100, current_y)
            if current_y - h <= 50:  # Check if we need a new page
                c.showPage()
                current_y = A4[1] - 50
            element.drawOn(c, 50, current_y - h)
            current_y -= h + 10
        
        c.save()

    def create_card_pdf(self, cards_data, output_file):
        c = canvas.Canvas(output_file, pagesize=A4)
        current_card = 0
        
        for card in cards_data:
            x = (current_card % 3) * self.card_width
            y = A4[1] - ((current_card // 3) % 3 + 1) * self.card_height
            
            # Draw card border
            c.setStrokeColor(colors.black)
            c.rect(x, y, self.card_width, self.card_height)
            
            # Place background image
            c.drawImage(card['background'], x, y, self.card_width, self.card_height)
            
            # Create semi-transparent white background for title area
            c.setFillColor(colors.white.clone(alpha=0.7))  # More opaque for title
            c.rect(x + 5, y + self.card_height - 45, self.card_width - 10, 40, fill=True)
            
            # Create semi-transparent white background for description area
            c.setFillColor(colors.white.clone(alpha=0.8))  # More opaque for text
            c.rect(x + 5, y + 5, self.card_width - 10, self.card_height - 55, fill=True)
            
            # Add text
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(x + 10, y + self.card_height - 20, card['title'])
            
            # Add card type
            c.setFont("Helvetica", 10)
            c.drawString(x + 10, y + self.card_height - 35, card['type'])
            
            # Add description with text wrapping
            style = ParagraphStyle(
                'CardText',
                fontSize=10,
                leading=12,
                textColor=colors.black,
                fontName='Helvetica',
                alignment=1  # Center alignment for better look
            )
            p = Paragraph(card['description'], style)
            p.wrapOn(c, self.card_width - 20, self.card_height - 60)
            p.drawOn(c, x + 10, y + 15)  # Slightly higher position
            
            current_card += 1
            if current_card % self.cards_per_page == 0:
                c.showPage()
        
        c.save() 