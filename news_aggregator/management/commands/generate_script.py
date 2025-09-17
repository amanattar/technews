import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
import google.generativeai as genai


class Command(BaseCommand):
    help = 'Generate a tech news script from a CSV file of articles'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the CSV file containing articles'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='tech_news_script.txt',
            help='Output file path for the generated script (default: tech_news_script.txt)'
        )
    
    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        output_file_path = options['output']
        
        # Check if CSV file exists
        if not os.path.exists(csv_file_path):
            self.stdout.write(
                self.style.ERROR(f'CSV file not found: {csv_file_path}')
            )
            return
        
        # Read articles from CSV
        articles = self.read_articles_from_csv(csv_file_path)
        
        if not articles:
            self.stdout.write(
                self.style.ERROR('No articles found in the CSV file')
            )
            return
        
        self.stdout.write(f'Processing {len(articles)} articles from {csv_file_path}')
        
        # Generate script using Gemini API
        script = self.generate_script_with_gemini(articles)
        
        if not script:
            self.stdout.write(
                self.style.ERROR('Failed to generate script')
            )
            return
        
        # Save script to file
        try:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                f.write(script)
            
            self.stdout.write(
                self.style.SUCCESS(f'Script successfully generated and saved to {output_file_path}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to save script: {str(e)}')
            )
    
    def read_articles_from_csv(self, csv_file_path):
        """Read articles from CSV file"""
        articles = []
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    articles.append({
                        'title': row.get('title', ''),
                        'url': row.get('url', ''),
                        'source': row.get('source', ''),
                        'author': row.get('author', ''),
                        'published_date': row.get('published_date', ''),
                        'description': row.get('description', ''),
                        'tags': row.get('tags', ''),
                        'is_breaking': row.get('is_breaking', 'False').lower() == 'true',
                        'is_trending': row.get('is_trending', 'False').lower() == 'true',
                        'is_featured': row.get('is_featured', 'False').lower() == 'true',
                    })
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error reading CSV file: {str(e)}')
            )
            return []
        
        return articles
    
    def generate_script_with_gemini(self, articles):
        """Generate script using Gemini API"""
        try:
            # Get API key from settings
            api_key = getattr(settings, 'GEMINI_API_KEY', None)
            if not api_key:
                self.stdout.write(
                    self.style.ERROR('GEMINI_API_KEY not found in settings')
                )
                return None
            
            # Configure Gemini
            genai.configure(api_key=api_key)
            
            # Prepare articles data for the prompt
            articles_text = ""
            for i, article in enumerate(articles, 1):
                articles_text += f"{i}. Title: {article['title']}\n"
                if article['description']:
                    articles_text += f"   Description: {article['description']}\n"
                articles_text += f"   Source: {article['source']}\n"
                if article['is_breaking']:
                    articles_text += "   Status: BREAKING NEWS\n"
                elif article['is_trending']:
                    articles_text += "   Status: TRENDING\n"
                elif article['is_featured']:
                    articles_text += "   Status: FEATURED\n"
                articles_text += "\n"
            
            # Create the prompt
            prompt = f"""Act as a tech news scriptwriter. Your task is to generate a summary script from the list of articles provided below.
The script must follow this exact format, including the section headers, placeholders, and separators:

Breaking News:
[Content for Breaking News]
-------------------------------------

Subscriber Callout

New Launches:
[Content for New Launches]
-------------------------------------

-------------------------------------

Upcoming Launches:
[Content for Upcoming Launches]
-------------------------------------

-------------------------------------

Leaks & Rumors:
[Content for Leaks & Rumors]
-------------------------------------

-------------------------------------

Deals:
[Content for Deals]
-------------------------------------

-------------------------------------

Telegram Channel Callout

WTF News:
[Content for WTF News]
-------------------------------------


Rapid Fire:
[Content for Rapid Fire]
-------------------------------------

-------------------------------------

THE END

Sources:
[List of sources used]

Instructions:
Read and Categorize: Analyze each article from the provided CSV data. Based on its title and description, categorize it into one of the following sections: Breaking News, New Launches, Upcoming Launches, Leaks & Rumors, or Rapid Fire.
Summarize and Format: Create a concise summary of each article and place it in the appropriate section.
For New Launches, clearly state the product name and any key features or specifications mentioned in the article.
For Rapid Fire, create a short, single-sentence summary for smaller news items or software updates.
Handle Empty Sections: If no articles from the CSV fit into a particular section (e.g., Deals, Leaks & Rumors), leave that section blank.
Adhere to the Source: Only use information present in the provided CSV file. Do not invent or add external information.
Maintain Placeholders: The sections Subscriber Callout and Telegram Channel Callout should remain as they are.
Cite Sources: At the end of the script, under the Sources title, list the source from the CSV for each piece of news included in the script.

Articles data:
{articles_text}

Script:"""
            
            # Initialize the model (using gemini-2.5-pro as requested)
            model = genai.GenerativeModel('models/gemini-2.5-pro')
            
            # Generate the script
            response = model.generate_content(prompt)
            
            if response.text:
                return response.text.strip()
            else:
                self.stdout.write(
                    self.style.ERROR('Gemini API returned empty response')
                )
                return None
                
        except ImportError:
            self.stdout.write(
                self.style.ERROR('google-generativeai package not installed. Install with: pip install google-generativeai')
            )
            return None
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Gemini API error: {str(e)}')
            )
            return None